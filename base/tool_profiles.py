"""
Tool profiles (OpenClaw-style): reduce the tool set per request so the LLM sees fewer tools.

When tools.profile or tools.profiles is set in config, only tools in the selected profile(s)
are passed to the LLM. "full" = no filter (all tools). Unlisted tools are included only when
profile is "full".

Profiles:
- full: all tools (no filtering)
- minimal: very small set (web_search, folder_list, run_skill, remind_me, time, route_to_plugin)
- messaging: typical chat assistant (search, files, document, skills, save page, cron, memory, sessions, route_to_plugin)
- coding: dev/shell (exec, file ops, edit, apply_patch, process_*, folder_list, document_read, etc.)
"""

from typing import Any, Dict, List, Optional

from base.tools import ToolDefinition

# Tool name -> list of profile ids that include this tool. "full" is never listed; when selected we skip filtering.
TOOL_PROFILES: Dict[str, List[str]] = {
    # minimal
    "web_search": ["minimal", "messaging"],
    "folder_list": ["minimal", "messaging", "coding"],
    "run_skill": ["minimal", "messaging"],
    "remind_me": ["minimal", "messaging"],
    "time": ["minimal", "messaging"],
    # echo: testing only; not in any default profile so LLM responds in content (no tool for simple replies)
    "echo": [],
    "route_to_plugin": ["minimal", "messaging"],
    # messaging (documents, save, cron, memory, sessions)
    "document_read": ["messaging", "coding"],
    "file_read": ["messaging", "coding"],
    "file_find": ["messaging", "coding"],
    "save_result_page": ["messaging"],
    "get_file_view_link": ["messaging"],
    "file_write": ["messaging", "coding"],
    "file_edit": ["coding"],
    "apply_patch": ["coding"],
    "memory_search": ["messaging"],
    "memory_get": ["messaging"],
    "agent_memory_search": ["messaging"],
    "agent_memory_get": ["messaging"],
    "append_agent_memory": ["messaging"],
    "append_daily_memory": ["messaging"],
    "cron_schedule": ["messaging"],
    "cron_list": ["messaging"],
    "cron_remove": ["messaging"],
    "cron_update": ["messaging"],
    "cron_run": ["messaging"],
    "cron_status": ["messaging"],
    "record_date": ["messaging"],
    "recorded_events_list": ["messaging"],
    "sessions_list": ["messaging"],
    "sessions_send": ["messaging"],
    "sessions_spawn": ["messaging"],
    "peer_call": ["messaging", "coding"],
    "sessions_transcript": ["messaging"],
    "route_to_tam": ["messaging"],
    "fetch_url": ["messaging"],
    "tavily_extract": ["messaging"],
    "tavily_crawl": ["messaging"],
    "tavily_research": ["messaging"],
    "web_extract": ["messaging"],
    "web_crawl": ["messaging"],
    "knowledge_base_search": ["messaging"],
    "knowledge_base_add": ["messaging"],
    "knowledge_base_remove": ["messaging"],
    "knowledge_base_list": ["messaging"],
    "image": ["messaging"],
    # coding / runtime
    "exec": ["coding"],
    "process_list": ["coding"],
    "process_poll": ["coding"],
    "process_kill": ["coding"],
    "file_understand": ["messaging", "coding"],
    # browser (when not using plugin)
    "browser_navigate": ["messaging"],
    "browser_snapshot": ["messaging"],
    "browser_click": ["messaging"],
    "browser_type": ["messaging"],
    "web_search_browser": ["messaging"],
    # other
    "profile_get": ["messaging"],
    "profile_list": ["messaging"],
    "profile_update": ["messaging"],
    "session_status": ["messaging"],
    "channel_send": ["messaging"],
    "usage_report": ["messaging"],
    "models_list": ["messaging"],
    "agents_list": ["messaging"],
    "platform_info": ["messaging"],
    "cwd": ["messaging", "coding"],
    "env": ["messaging", "coding"],
    "http_request": ["coding"],
    "webhook_trigger": ["messaging"],
    # MCP: when tools.mcp.enabled and servers configured, LLM can call external MCP servers (e.g. claude-code via claude mcp serve).
    "mcp_list_tools": ["coding", "messaging"],
    "mcp_call": ["coding", "messaging"],
}

VALID_PROFILES = frozenset({"full", "minimal", "messaging", "coding"})


def get_tool_names_for_profile(
    profile: str,
    tool_profiles_map: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """
    Return tool names that belong to the given profile (e.g. "minimal", "coding").
    Used when merging multiple intent-router categories: resolve profile to names and union.
    "full" returns empty list (caller should treat as no filter / all tools).
    """
    if not profile or not isinstance(profile, str):
        return []
    p = profile.strip().lower()
    if p == "full":
        return []
    m = tool_profiles_map if tool_profiles_map is not None else TOOL_PROFILES
    if not isinstance(m, dict):
        return []
    out = []
    for tool_name, profiles_list in m.items():
        if profiles_list and p in [str(x).strip().lower() for x in profiles_list if x]:
            out.append(tool_name)
    return out


def _resolve_selected_profiles(tools_config: Optional[Dict[str, Any]]) -> Optional[List[str]]:
    """Return list of profile ids from config, or None if not set (no filtering)."""
    if not tools_config or not isinstance(tools_config, dict):
        return None
    profile = tools_config.get("profile")
    profiles = tools_config.get("profiles")
    if profiles is not None and isinstance(profiles, list):
        out = [str(p).strip().lower() for p in profiles if p and str(p).strip()]
        return out if out else None
    if profile and str(profile).strip():
        return [str(profile).strip().lower()]
    return None


def filter_tools_by_profile(
    tools: List[ToolDefinition],
    selected_profiles: List[str],
    tool_profiles_map: Optional[Dict[str, List[str]]] = None,
) -> List[ToolDefinition]:
    """
    Return only tools that belong to at least one of the selected profiles.
    When "full" is in selected_profiles, return all tools (no filtering).
    Tools not in the map are included only when "full" is selected.
    """
    if not selected_profiles:
        return tools
    normalized = [p.strip().lower() for p in selected_profiles if p and str(p).strip()]
    if not normalized:
        return tools
    m = tool_profiles_map if tool_profiles_map is not None else TOOL_PROFILES
    if "full" in normalized:
        # Still exclude tools with an empty profile list (e.g. echo = testing only) so LLM responds in content.
        excluded_when_full = {k for k, v in m.items() if v is not None and len(v) == 0}
        if excluded_when_full:
            return [t for t in tools if (getattr(t, "name", None) or "") not in excluded_when_full]
        return tools
    profile_set = set(normalized)
    out = []
    for t in tools:
        name = getattr(t, "name", None) or ""
        if not name:
            continue
        tool_profiles = m.get(name)
        if tool_profiles and profile_set.intersection(tool_profiles):
            out.append(t)
    return out


def get_tools_for_llm(
    all_tools: List[ToolDefinition],
    tools_config: Optional[Dict[str, Any]],
    tool_profiles_map: Optional[Dict[str, List[str]]] = None,
) -> List[ToolDefinition]:
    """
    Apply profile filter from tools_config to the list of tools.
    If no profile/profiles in config, return all_tools unchanged.
    """
    selected = _resolve_selected_profiles(tools_config)
    if not selected:
        return all_tools
    return filter_tools_by_profile(all_tools, selected, tool_profiles_map)
