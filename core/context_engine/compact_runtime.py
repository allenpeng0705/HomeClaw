"""
Compact runtime: session rotation and summary generation during compaction.

When compaction fires and messages must be trimmed, this module:
  1. Generates a compaction summary for the trimmed prefix
  2. Optionally rotates to a new session (new session_id)
  3. Returns rotation metadata for the engine to include in CompactResult

Session rotation preserves the old session for audit/debug while giving
the LLM a clean context anchor in the new session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


def generate_compaction_summary(
    trimmed_messages: List[Dict[str, Any]],
    max_summary_chars: int = 500,
) -> str:
    """
    Generate a human-readable summary of compacted context.

    For now this is a heuristic summary (user/assistant turn counts).
    In a future phase, an LLM-based summarization can be plugged in here.

    Returns a string suitable for prepending as a system message.
    """
    if not trimmed_messages:
        return ""

    user_turns = sum(1 for m in trimmed_messages if m.get("role") == "user")
    assistant_turns = sum(1 for m in trimmed_messages if m.get("role") == "assistant")
    tool_turns = sum(1 for m in trimmed_messages if m.get("role") == "tool")

    # Collect first few user message snippets to hint at topics
    user_snippets: List[str] = []
    for m in trimmed_messages:
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                snippet = content.strip()[:80]
                user_snippets.append(snippet)
            if len(user_snippets) >= 3:
                break

    parts = [
        f"[Previous conversation compacted at {datetime.now().isoformat(timespec='seconds')}]",
        f"Compacted {len(trimmed_messages)} messages "
        f"({user_turns} user, {assistant_turns} assistant, {tool_turns} tool).",
    ]

    if user_snippets:
        topics = "; ".join(user_snippets)
        parts.append(f"Topics included: {topics}")

    summary = "\n".join(parts)
    if len(summary) > max_summary_chars:
        summary = summary[: max_summary_chars - 3] + "..."

    return summary


async def generate_llm_compaction_summary(
    trimmed_messages: List[Dict[str, Any]],
    core: Any = None,
    max_summary_chars: int = 500,
) -> str:
    """
    Generate a compaction summary using the LLM.

    When core is provided and the LLM is reachable, this produces a more
    meaningful summary than the heuristic version. Falls back to the
    heuristic summary on any error.
    """
    if not trimmed_messages:
        return ""

    # Try LLM-based summary first
    if core is not None:
        try:
            from base.util import Util
            # Build a minimal prompt: give the LLM the trimmed messages and ask for a summary
            msgs_text = "\n".join(
                f"[{m.get('role', '?')}] {str(m.get('content', ''))[:200]}"
                for m in trimmed_messages[-20:]  # last 20 messages max
            )
            prompt = (
                "Summarize this conversation prefix in 2-3 sentences. "
                "Focus on key topics, decisions, and user preferences. "
                "Be concise — this will be used as a compaction anchor.\n\n"
                f"{msgs_text}"
            )
            messages = [
                {"role": "system", "content": "You are a concise summarizer."},
                {"role": "user", "content": prompt},
            ]
            raw = await Util().openai_chat_completion(messages, llm_name=None)
            if isinstance(raw, str) and raw.strip():
                summary = f"[Compacted at {datetime.now().isoformat(timespec='seconds')}]\n{raw.strip()}"
                if len(summary) > max_summary_chars:
                    summary = summary[: max_summary_chars - 3] + "..."
                return summary
        except Exception:
            pass

    # Fall back to heuristic summary
    return generate_compaction_summary(trimmed_messages, max_summary_chars)


def create_compaction_system_message(summary: str) -> Dict[str, str]:
    """
    Create a system message from a compaction summary.
    Prepended to the new session's message list.
    """
    return {"role": "system", "content": summary}


def rotate_session_id(existing_session_id: str) -> str:
    """
    Generate a new session id derived from the existing one.

    Appends a compaction suffix so it's clear this is a rotated session.
    Example: "abc123" → "abc123-c1"
    """
    # Strip any existing compaction suffix
    base = existing_session_id.rsplit("-c", 1)[0] if "-c" in existing_session_id else existing_session_id
    # Count existing compactions (increment suffix)
    suffix = "c1"
    if "-c" in existing_session_id:
        try:
            n = int(existing_session_id.rsplit("-c", 1)[1]) + 1
            suffix = f"c{n}"
        except (ValueError, IndexError):
            pass
    return f"{base}-{suffix}"


async def rotate_session(
    core: Any,
    session_id: str,
    session_file: Optional[str],
    trimmed_messages: List[Dict[str, Any]],
) -> Tuple[str, Optional[str], str]:
    """
    Rotate to a new session after compaction.

    Returns (new_session_id, new_session_file, compaction_summary).

    The caller should:
      1. Use new_session_id for subsequent messages
      2. Prepend the compaction summary as the first message
      3. Keep the old session_file for audit (don't delete)
    """
    summary = await generate_llm_compaction_summary(trimmed_messages, core=core)
    new_session_id = rotate_session_id(session_id)

    # Generate a new session file path if the old one was provided
    new_session_file: Optional[str] = None
    if session_file:
        # Same directory, new filename with rotation suffix
        from pathlib import Path
        sf = Path(session_file)
        stem = sf.stem
        # Strip existing rotation suffix from stem
        if "-c" in stem:
            base_stem = stem.rsplit("-c", 1)[0]
        else:
            base_stem = stem
        # Find next rotation number
        rotation_n = 1
        for part in stem.rsplit("-c", 1):
            if part != stem:
                try:
                    rotation_n = int(part) + 1
                except ValueError:
                    pass
        new_stem = f"{base_stem}-c{rotation_n}"
        new_session_file = str(sf.with_name(f"{new_stem}{sf.suffix}"))

    logger.info(
        "Session rotated: {} → {} (compacted {} messages)",
        session_id, new_session_id, len(trimmed_messages),
    )

    return new_session_id, new_session_file, summary
