"""Tool permission evaluation (config-driven). Default: allow all."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# Modes understood by evaluate_tool_permission
ALLOW_ALL = "allow_all"
ALLOW_READ_RESTRICT_WRITE = "allow_read_restrict_write"


@dataclass(frozen=True)
class ToolPermissionContext:
    """Per-request policy context for tool execution."""

    mode: str = ALLOW_ALL
    user_id: Optional[str] = None
    channel_type: Optional[str] = None
    friend_id: Optional[str] = None
    # When True, treat as allow_read_restrict_write even if global tool_policy is allow_all (Claw-Code session mode=plan).
    clawcode_plan_mode: bool = False


@dataclass(frozen=True)
class PermissionResult:
    allowed: bool
    reason_code: str = ""
    message: str = ""


def tool_permission_context_from_meta(meta: Any, request: Any = None) -> ToolPermissionContext:
    """Build context from CoreMetadata.tool_policy and optional PromptRequest."""
    tp: Dict[str, Any] = {}
    try:
        raw = getattr(meta, "tool_policy", None) if meta is not None else None
        if isinstance(raw, dict):
            tp = raw
    except Exception:
        tp = {}
    mode = (tp.get("default_mode") or ALLOW_ALL).strip().lower()
    if mode not in (ALLOW_ALL, ALLOW_READ_RESTRICT_WRITE):
        mode = ALLOW_ALL
    user_id = None
    channel_type = None
    friend_id = None
    cc_plan = False
    if request is not None:
        try:
            user_id = getattr(request, "user_id", None) or getattr(request, "system_user_id", None)
            friend_id = getattr(request, "friend_id", None)
            ct = getattr(request, "channelType", None)
            if ct is not None:
                channel_type = str(ct).split(".")[-1]
            md = getattr(request, "request_metadata", None) or {}
            if isinstance(md, dict):
                csid = str(md.get("clawcode_session_id") or "").strip()
                if csid:
                    try:
                        from core.clawcode_store import clawcode_feature_enabled, get_session, session_mode_value

                        if clawcode_feature_enabled():
                            s = get_session(csid)
                            cc_plan = session_mode_value(s) == "plan"
                    except Exception:
                        pass
        except Exception:
            pass
    return ToolPermissionContext(
        mode=mode,
        user_id=str(user_id).strip() if user_id else None,
        channel_type=str(channel_type).strip() if channel_type else None,
        friend_id=str(friend_id).strip() if friend_id else None,
        clawcode_plan_mode=cc_plan,
    )


def _effective_risk_tier(tool: Any) -> str:
    """Map ToolDefinition.risk_tier; None or empty → read (conservative for restrictive mode)."""
    tier = getattr(tool, "risk_tier", None)
    if isinstance(tier, str) and tier.strip():
        return tier.strip().lower()
    return "read"


def evaluate_tool_permission(tool: Any, arguments: Dict[str, Any], ctx: Optional[ToolPermissionContext]) -> PermissionResult:
    """
    Returns PermissionResult(allowed=False) before executor runs when policy denies.
    arguments reserved for future per-arg rules.
    """
    _ = arguments
    eff_mode = ctx.mode if ctx is not None else ALLOW_ALL
    if ctx is not None and ctx.clawcode_plan_mode:
        eff_mode = ALLOW_READ_RESTRICT_WRITE
    if ctx is None or eff_mode == ALLOW_ALL:
        return PermissionResult(True, "", "")
    if eff_mode == ALLOW_READ_RESTRICT_WRITE:
        name = getattr(tool, "name", "?")
        if bool(getattr(tool, "requires_confirmation", False)):
            return PermissionResult(
                False,
                "requires_confirmation",
                f"Tool {name} is blocked by tool_policy.default_mode=allow_read_restrict_write (requires_confirmation=true).",
            )
        tier = _effective_risk_tier(tool)
        if tier in ("write", "exec", "network", "user_data"):
            return PermissionResult(
                False,
                "policy_tier_blocked",
                f"Tool {name} is blocked by tool_policy.default_mode=allow_read_restrict_write (risk_tier={tier}).",
            )
    return PermissionResult(True, "", "")
