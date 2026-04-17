"""
Reminder / cron `message` text for TAM delivery: optional LLM rewrite + heuristic fallback.

- Does not parse dates, times, or cron — only the user-visible label.
- LLM runs at tool execution time (remind_me / cron_schedule / record_date), not in regex fallbacks.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Optional, Tuple

from loguru import logger

_LEADING_CN_FILLER = re.compile(
    r"^(?:能不能|能否|可不可以|可以|请|麻烦|帮我|记得|想请你|希望你|麻烦你|)\s*"
)
_TRAILING_QUESTION = re.compile(r"[吗嘛吧呢呀]\s*[？?]?\s*$")
_TRAILING_QMARK = re.compile(r"[？?]+\s*$")
_EN_REMIND_TO = re.compile(
    r"(?:^|\b)(?:please\s+)?(?:can you|could you|would you)\s+remind\s+me\s+to\s+(.+)$",
    re.IGNORECASE,
)
_EN_REMIND_ME_TO = re.compile(r"\bremind\s+me\s+to\s+(.+)$", re.IGNORECASE)

REMINDER_MESSAGE_REFINE_SYSTEM_PROMPT = """You format text for a personal reminder / scheduled notification system.

The input may be a full user sentence, a question, polite wrappers, or extra scheduling context mixed with the real task.

Your job: output exactly ONE short line that will be shown when the reminder fires.

Rules:
- Describe clearly WHAT to remember or do (imperative or short noun phrase). Use the same primary language as the user's substantive content (Chinese stays Chinese, English stays English, etc.).
- Remove scheduling metadata (e.g. "in 5 minutes", "tomorrow 3pm", "every morning", dates, "提前一周") — the app shows time separately; do not repeat it in the line.
- Remove conversational wrappers ("能不能", "please could you", "remind me to", question marks).
- Do not add greetings ("Hey"), quotes, markdown, bullet lists, or explanations.
- Do not invent facts not implied by the input.
- Hard limit: at most about 80 characters; never more than 120 characters in the line.

Output only that single line, with no prefix or suffix."""

REMINDER_MESSAGE_REFINE_USER_TEMPLATE = "Turn this into the single reminder line:\n\n{raw}"


def _read_reminder_message_llm_config() -> Tuple[bool, float]:
    """(enabled, timeout_seconds). Never raises."""
    try:
        from base.util import Util

        meta = Util().get_core_metadata()
        cfg = getattr(meta, "tools_config", None) or {}
    except Exception:
        cfg = {}
    try:
        enabled = bool(cfg.get("reminder_message_llm_refine", True))
    except Exception:
        enabled = True
    try:
        timeout = float(cfg.get("reminder_message_llm_refine_timeout_seconds") or 20.0)
    except (TypeError, ValueError):
        timeout = 20.0
    timeout = max(3.0, min(120.0, timeout))
    return enabled, timeout


def _skip_llm_for_message(s: str) -> bool:
    """Internal cron/reminder labels that should not hit the rewriter."""
    t = (s or "").strip()
    if not t:
        return True
    low = t.lower()
    if low.startswith("run_skill ") or low.startswith("run_plugin ") or low.startswith("run_tool "):
        return True
    if t == "Scheduled reminder":
        return True
    return False


def normalize_llm_reminder_line(s: Optional[str], *, max_chars: int) -> str:
    """Strip fences / take first line / clamp length. Never raises."""
    if not s or not isinstance(s, str):
        return ""
    t = s.strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t).strip()
    t = t.split("\n")[0].strip()
    if len(t) >= 2 and ((t[0] == t[-1] == '"') or (t[0] == t[-1] == "'")):
        t = t[1:-1].strip()
    if len(t) > max_chars:
        cut = t[:max_chars]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        if len(cut) < max_chars // 2:
            cut = t[:max_chars]
        t = cut.strip()
    return t


def refine_scheduled_message_text(text: Optional[str], *, max_chars: int = 120) -> str:
    """
    Heuristic-only: short reminder label. Used when LLM is off/unavailable or as fallback.
    Never raises. Empty input → "Reminder".
    """
    if not text or not isinstance(text, str):
        return "Reminder"
    raw = text.strip()
    if not raw:
        return "Reminder"
    original = raw
    s = re.sub(r"\s+", " ", raw)

    m = _EN_REMIND_TO.search(s)
    if m and len((m.group(1) or "").strip()) >= 2:
        s = m.group(1).strip()
    else:
        m2 = _EN_REMIND_ME_TO.search(s)
        if m2 and len((m2.group(1) or "").strip()) >= 2:
            s = m2.group(1).strip()

    if "提醒" in s:
        parts = re.split(r"提醒(?:我|一下)?\s*", s)
        if len(parts) >= 2:
            tail = parts[-1].strip()
            if tail and len(tail) <= len(s):
                s = tail

    s = _LEADING_CN_FILLER.sub("", s).strip()
    s = _TRAILING_QUESTION.sub("", s).strip()
    s = _TRAILING_QMARK.sub("", s).strip()

    s = re.sub(r"^(?:提前|提早)\s*(?:一周|一\s*个\s*星期|\d+\s*天)\s*", "", s).strip()

    if not s or len(s) < 2:
        s = original[:max_chars].strip()
    if not s:
        return "Reminder"

    if len(s) > max_chars:
        cut = s[:max_chars]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        if len(cut) < max_chars // 2:
            cut = s[:max_chars]
        s = cut.strip()

    return s or "Reminder"


async def refine_scheduled_message_for_delivery(
    core: Any,
    raw: Optional[str],
    *,
    max_chars: int = 120,
) -> str:
    """
    Produce the final `message` / remind_message string for TAM: optional LLM, else heuristic.

    - `raw` should be the tool argument as provided (may be long / question-shaped).
    - Scheduling times/cron are unchanged; this only affects stored/display text.
    """
    if not raw or not isinstance(raw, str):
        return "Reminder"
    raw_stripped = raw.strip()
    if not raw_stripped:
        return "Reminder"

    fallback = refine_scheduled_message_text(raw_stripped, max_chars=max_chars)

    enabled, timeout = _read_reminder_message_llm_config()
    if not enabled or _skip_llm_for_message(raw_stripped):
        return fallback

    if core is None or not callable(getattr(core, "openai_chat_completion", None)):
        return fallback

    messages = [
        {"role": "system", "content": REMINDER_MESSAGE_REFINE_SYSTEM_PROMPT},
        {"role": "user", "content": REMINDER_MESSAGE_REFINE_USER_TEMPLATE.format(raw=raw_stripped)},
    ]
    try:
        out = await asyncio.wait_for(core.openai_chat_completion(messages), timeout=timeout)
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug("reminder_message LLM refine skipped/fallback: {}", e)
        return fallback

    if not out or not isinstance(out, str):
        return fallback

    line = normalize_llm_reminder_line(out, max_chars=max_chars)
    if not line or len(line) < 1:
        return fallback

    return line
