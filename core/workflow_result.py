"""
Standardized workflow result envelope for tools that need multi-step input or confirmation.

Tools can return a JSON string with workflow_status: need_input | need_confirmation | done.
Core stores need_input/need_confirmation and resumes when the user replies.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

# Prefix that marks a tool result as a workflow envelope (optional; we also accept raw JSON).
WORKFLOW_PREFIX = "WORKFLOW_RESULT:"

STATUS_NEED_INPUT = "need_input"
STATUS_NEED_CONFIRMATION = "need_confirmation"
STATUS_DONE = "done"


def parse_workflow_result(tool_result: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    If tool_result is a workflow envelope, return (workflow_status, parsed_dict).
    Otherwise return (None, None). Never raises.
    """
    if not tool_result or not isinstance(tool_result, str):
        return None, None
    s = tool_result.strip()
    if s.startswith(WORKFLOW_PREFIX):
        s = s[len(WORKFLOW_PREFIX) :].strip()
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            return None, None
        status = (obj.get("workflow_status") or "").strip().lower()
        if status in (STATUS_NEED_INPUT, STATUS_NEED_CONFIRMATION, STATUS_DONE):
            return status, obj
        return None, None
    except (json.JSONDecodeError, TypeError):
        return None, None


def is_confirm_reply(text: str) -> bool:
    """True if the user message is a confirmation (e.g. confirm, 确认, send, yes)."""
    if not text or not isinstance(text, str):
        return False
    t = text.strip().lower()
    if not t:
        return False
    confirm_words = ("confirm", "confirmed", "yes", "send", "ok", "okay", "确认", "好的", "发送", "是")
    return t in confirm_words or t in ("y", "✓", "✔")


def build_need_input(
    message: str,
    resume_tool: str,
    resume_args: Dict[str, Any],
    missing_fields: Optional[list] = None,
) -> str:
    """Build a need_input envelope string for a tool to return."""
    payload = {
        "workflow_status": STATUS_NEED_INPUT,
        "message": message,
        "resume_tool": resume_tool,
        "resume_args": resume_args,
        "missing_fields": missing_fields or [],
    }
    return json.dumps(payload, ensure_ascii=False)


def build_need_confirmation(
    message: str,
    confirm_tool: str,
    confirm_args: Dict[str, Any],
) -> str:
    """Build a need_confirmation envelope string for a tool to return."""
    payload = {
        "workflow_status": STATUS_NEED_CONFIRMATION,
        "message": message,
        "confirm_tool": confirm_tool,
        "confirm_args": confirm_args,
    }
    return json.dumps(payload, ensure_ascii=False)


def build_done(result_text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    """Build a done envelope (optional; plain result_text is also treated as done)."""
    payload = {"workflow_status": STATUS_DONE, "message": result_text, **(metadata or {})}
    return json.dumps(payload, ensure_ascii=False)
