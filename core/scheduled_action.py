"""
Execute a scheduled action (confirm-now-run-later). Dispatches by action_type: send_email, run_skill, etc.
Called by TAM when a one-shot reminder fires with message __ACTION:action_id__.
"""
from typing import Any, Dict, Optional

from loguru import logger

from base.tools import ToolContext, get_tool_registry


async def execute_scheduled_action(
    core: Any,
    action_type: str,
    action_payload: Dict[str, Any],
    user_id: str,
    friend_id: Optional[str] = None,
    channel_key: Optional[str] = None,
) -> str:
    """
    Run a stored action (e.g. send_email, run_skill). Returns result string for the user. Never raises (returns error message on failure).
    """
    if not action_type or not isinstance(action_type, str):
        return "Error: invalid action (missing type)."
    action_type = action_type.strip() or "run_skill"
    if not isinstance(action_payload, dict):
        return "Error: invalid action (payload must be a dict)."
    registry = get_tool_registry()
    if not registry:
        return "Error: tool registry not available."
    try:
        try:
            _fid = (str(friend_id).strip() or "HomeClaw") if friend_id is not None else "HomeClaw"
        except (TypeError, AttributeError):
            _fid = "HomeClaw"
        ctx = ToolContext(
            core=core,
            user_id=(user_id or "companion").strip() or "companion",
            system_user_id=(user_id or "companion").strip() or "companion",
            friend_id=_fid,
            request=None,
        )
        if action_type == "send_email":
            to_addr = (action_payload.get("to") or "").strip()
            subject = (action_payload.get("subject") or "").strip()
            body = (action_payload.get("body") or "").strip()
            args = {
                "skill_name": "imap-smtp-email",
                "script": "smtp.js",
                "args": ["send", "--to", to_addr, "--subject", subject or "(no subject)", "--body", body],
            }
            result = await registry.execute_async("run_skill", args, ctx)
            return result if isinstance(result, str) else str(result)
        if action_type == "run_skill":
            args = dict(action_payload) if action_payload else {}
            result = await registry.execute_async("run_skill", args, ctx)
            return result if isinstance(result, str) else str(result)
        return f"Error: unknown action_type {action_type!r}. Supported: send_email, run_skill."
    except Exception as e:
        logger.exception("execute_scheduled_action failed: action_type={} {}", action_type, e)
        return f"Error: scheduled action failed: {e!s}"
