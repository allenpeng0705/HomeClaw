"""Accumulate OpenAI-style usage dicts onto the active PromptRequest for Claw-Code turns.

Set via contextvar while `answer_from_memory` runs with `request_metadata.clawcode_session_id`;
`base.util` completion paths call `note_completion_usage` so totals can be merged into the session file.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, List, Optional

_cv_prompt_request: ContextVar[Any] = ContextVar("llm_usage_prompt_request", default=None)


def attach_prompt_request_for_usage(request: Any) -> None:
    _cv_prompt_request.set(request)


def detach_prompt_request_for_usage() -> None:
    _cv_prompt_request.set(None)


def note_completion_usage(usage: Any) -> None:
    if not isinstance(usage, dict) or not usage:
        return
    req = _cv_prompt_request.get()
    if req is None:
        return
    md = getattr(req, "request_metadata", None)
    if not isinstance(md, dict):
        return
    if not str(md.get("clawcode_session_id") or "").strip():
        return
    slim: Dict[str, int] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if k not in usage or usage[k] is None:
            continue
        try:
            slim[k] = int(usage[k])
        except (TypeError, ValueError):
            continue
    if not slim:
        return
    parts = md.get("_clawcode_completion_usage")
    if not isinstance(parts, list):
        parts = []
        md["_clawcode_completion_usage"] = parts
    parts.append(slim)


def merge_usage_parts(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    sp, sc, st = 0, 0, 0
    for p in parts:
        if not isinstance(p, dict):
            continue
        try:
            sp += int(p.get("prompt_tokens") or 0)
        except (TypeError, ValueError):
            pass
        try:
            sc += int(p.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            pass
        try:
            st += int(p.get("total_tokens") or 0)
        except (TypeError, ValueError):
            pass
    if st == 0 and (sp or sc):
        st = sp + sc
    return {
        "prompt_tokens": sp,
        "completion_tokens": sc,
        "total_tokens": st,
        "rounds": len(parts),
    }


def pop_clawcode_accumulated_usage(request: Any) -> Optional[Dict[str, Any]]:
    if request is None:
        return None
    md = getattr(request, "request_metadata", None)
    if not isinstance(md, dict):
        return None
    parts = md.pop("_clawcode_completion_usage", None)
    if not isinstance(parts, list) or not parts:
        return None
    return merge_usage_parts(parts)


def fallback_clawcode_usage_from_request(request: Any) -> Optional[Dict[str, Any]]:
    """
    When the LLM proxy returns no usage blocks, store a rough total from user + assistant text
    (~4 chars/token). Mark estimated=True so UIs can distinguish from provider-reported usage.
    """
    if request is None:
        return None
    md = getattr(request, "request_metadata", None)
    if not isinstance(md, dict):
        return None
    if not str(md.get("clawcode_session_id") or "").strip():
        return None
    u = str(md.pop("_clawcode_last_user_text", None) or getattr(request, "text", None) or "")
    a = str(md.pop("_clawcode_last_assistant_text", None) or "")
    if not u.strip() and not a.strip():
        return None
    from base.token_estimate import estimate_messages_token_budget

    msgs = []
    if u.strip():
        msgs.append({"role": "user", "content": u})
    if a.strip():
        msgs.append({"role": "assistant", "content": a})
    est = estimate_messages_token_budget(msgs)
    if est <= 0:
        return None
    # Rough split for dashboards that expect prompt vs completion columns.
    prompt_guess = max(1, int(est * 0.55))
    completion_guess = max(1, est - prompt_guess)
    return {
        "prompt_tokens": prompt_guess,
        "completion_tokens": completion_guess,
        "total_tokens": est,
        "rounds": 1,
        "estimated": True,
    }
