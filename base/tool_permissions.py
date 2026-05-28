"""Tool permission evaluation (config-driven). Default: allow all.

Risk tiers (inspired by OpenClaw):
- read: Read-only operations (file_read, memory_search, knowledge_base_search)
- write: Write operations (file_write, append_agent_memory, knowledge_base_add)
- exec: Code execution (exec, process_kill, mcp_call)
- network: Network access (web_search, http_request, fetch_url)
- user_data: Access to user-specific data (profile_get, sessions_list)
- admin: Administrative operations (system config, plugin management)
- sensitive: Highly sensitive operations (auth, encryption keys)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# Modes understood by evaluate_tool_permission
ALLOW_ALL = "allow_all"
ALLOW_READ_RESTRICT_WRITE = "allow_read_restrict_write"
ALLOW_READ_ONLY = "allow_read_only"

# Valid risk tiers
VALID_RISK_TIERS = frozenset({
    "read",
    "write",
    "exec",
    "network",
    "user_data",
    "admin",
    "sensitive",
})

# Default risk tiers for common tools (can be overridden by ToolDefinition.risk_tier)
DEFAULT_TOOL_RISK_TIERS: Dict[str, str] = {
    # Read-only tools
    "file_read": "read",
    "file_find": "read",
    "folder_list": "read",
    "memory_search": "read",
    "memory_get": "read",
    "agent_memory_search": "read",
    "agent_memory_get": "read",
    "knowledge_base_search": "read",
    "knowledge_base_list": "read",
    "list_available_tools": "read",
    "search_available_tools": "read",
    "session_status": "read",
    "platform_info": "read",
    "models_list": "read",
    "agents_list": "read",
    "cwd": "read",
    "env": "read",
    "time": "read",
    "profile_get": "read",
    "profile_list": "read",
    
    # Write tools
    "file_write": "write",
    "file_edit": "write",
    "apply_patch": "write",
    "append_agent_memory": "write",
    "append_daily_memory": "write",
    "knowledge_base_add": "write",
    "knowledge_base_remove": "write",
    "profile_update": "write",
    "save_result_page": "write",
    
    # Exec tools
    "exec": "exec",
    "process_list": "exec",
    "process_poll": "exec",
    "process_kill": "exec",
    "mcp_call": "exec",
    
    # Network tools
    "web_search": "network",
    "fetch_url": "network",
    "http_request": "network",
    "tavily_extract": "network",
    "tavily_crawl": "network",
    "tavily_research": "network",
    "web_extract": "network",
    "web_crawl": "network",
    "web_search_browser": "network",
    "browser_navigate": "network",
    "browser_snapshot": "network",
    "browser_click": "network",
    "browser_type": "network",
    
    # User data tools
    "sessions_list": "user_data",
    "sessions_send": "user_data",
    "sessions_spawn": "user_data",
    "sessions_transcript": "user_data",
    "record_date": "user_data",
    "recorded_events_list": "user_data",
    "peer_call": "user_data",
    "channel_send": "user_data",
    "usage_report": "user_data",
    
    # Admin tools
    "cron_schedule": "admin",
    "cron_list": "admin",
    "cron_remove": "admin",
    "cron_update": "admin",
    "cron_run": "admin",
    "cron_status": "admin",
    "route_to_plugin": "admin",
    "route_to_tam": "admin",
    "remind_me": "admin",
    "webhook_trigger": "admin",
}


@dataclass(frozen=True)
class ToolPermissionContext:
    """Per-request policy context for tool execution."""

    mode: str = ALLOW_ALL
    user_id: Optional[str] = None
    channel_type: Optional[str] = None
    friend_id: Optional[str] = None
    # When True, treat as allow_read_restrict_write even if global tool_policy is allow_all (Claw-Code session mode=plan).
    clawcode_plan_mode: bool = False
    # Allowed risk tiers (if set, only tools with these tiers are allowed)
    allowed_tiers: Optional[Set[str]] = None
    # Denied risk tiers (if set, tools with these tiers are blocked)
    denied_tiers: Optional[Set[str]] = None


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
    """
    Map ToolDefinition.risk_tier; None or empty → check DEFAULT_TOOL_RISK_TIERS → read.
    Priority: 1. ToolDefinition.risk_tier  2. DEFAULT_TOOL_RISK_TIERS[tool_name]  3. "read"
    """
    # First check tool's own risk_tier attribute
    tier = getattr(tool, "risk_tier", None)
    if isinstance(tier, str) and tier.strip():
        normalized = tier.strip().lower()
        if normalized in VALID_RISK_TIERS:
            return normalized
    
    # Fall back to default risk tiers based on tool name
    tool_name = getattr(tool, "name", None)
    if isinstance(tool_name, str) and tool_name.strip():
        default_tier = DEFAULT_TOOL_RISK_TIERS.get(tool_name.strip())
        if default_tier:
            return default_tier
    
    # Default to "read" for safety
    return "read"


def evaluate_tool_permission(tool: Any, arguments: Dict[str, Any], ctx: Optional[ToolPermissionContext]) -> PermissionResult:
    """
    Returns PermissionResult(allowed=False) before executor runs when policy denies.
    arguments reserved for future per-arg rules.
    """
    _ = arguments
    name = getattr(tool, "name", "?")
    
    # If no context, allow all
    if ctx is None:
        return PermissionResult(True, "", "")
    
    # Determine effective mode
    eff_mode = ctx.mode
    if ctx.clawcode_plan_mode:
        eff_mode = ALLOW_READ_RESTRICT_WRITE
    
    # Allow all mode
    if eff_mode == ALLOW_ALL:
        return PermissionResult(True, "", "")
    
    # Check requires_confirmation first (highest priority)
    if bool(getattr(tool, "requires_confirmation", False)):
        return PermissionResult(
            False,
            "requires_confirmation",
            f"Tool {name} is blocked (requires_confirmation=true).",
        )
    
    # Get effective risk tier
    tier = _effective_risk_tier(tool)
    
    # Check denied tiers from context
    if ctx.denied_tiers and tier in ctx.denied_tiers:
        return PermissionResult(
            False,
            "denied_tier",
            f"Tool {name} is blocked (risk_tier={tier} is in denied_tiers).",
        )
    
    # Check allowed tiers from context
    if ctx.allowed_tiers and tier not in ctx.allowed_tiers:
        return PermissionResult(
            False,
            "not_in_allowed_tiers",
            f"Tool {name} is blocked (risk_tier={tier} not in allowed_tiers).",
        )
    
    # Mode-specific restrictions
    if eff_mode == ALLOW_READ_RESTRICT_WRITE:
        # Block write, exec, network, user_data, admin, and sensitive tiers
        restricted_tiers = {"write", "exec", "network", "user_data", "admin", "sensitive"}
        if tier in restricted_tiers:
            return PermissionResult(
                False,
                "policy_tier_blocked",
                f"Tool {name} is blocked by tool_policy.default_mode=allow_read_restrict_write (risk_tier={tier}).",
            )
    
    elif eff_mode == ALLOW_READ_ONLY:
        # Only allow read tier
        if tier != "read":
            return PermissionResult(
                False,
                "read_only_mode",
                f"Tool {name} is blocked by tool_policy.default_mode=allow_read_only (risk_tier={tier}).",
            )
    
    # All checks passed
    return PermissionResult(True, "", "")
