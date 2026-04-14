"""Rough token estimates for agent budget guards (no tokenizer dependency)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _text_len(obj: Any) -> int:
    if obj is None:
        return 0
    if isinstance(obj, str):
        return len(obj)
    if isinstance(obj, (list, tuple)):
        return sum(_text_len(x) for x in obj)
    if isinstance(obj, dict):
        return sum(_text_len(v) for v in obj.values())
    return len(str(obj))


def estimate_messages_token_budget(messages: Optional[List[Dict[str, Any]]]) -> int:
    """
    Heuristic: ~4 chars per token for Latin/CJK mix. Sums assistant/user/system/tool content
    and tool_calls JSON-ish payload length.
    """
    if not messages:
        return 0
    total_chars = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        total_chars += _text_len(m.get("content"))
        tcs = m.get("tool_calls")
        if isinstance(tcs, list):
            total_chars += _text_len(tcs)
    return max(1, total_chars // 4)
