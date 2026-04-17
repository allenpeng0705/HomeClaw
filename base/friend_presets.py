"""
Friend presets: load preset config from YAML and resolve tool lists per preset.
See docs_design/FriendConfigFrameworkImplementation.md.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

# Tool names per preset. Must match names registered in the tool registry (e.g. tools/builtin.py).
# Reminder: cron/reminder/scheduling only. Include time so the LLM can use current date when scheduling (e.g. "tomorrow at 9am").
TOOL_PRESETS: Dict[str, List[str]] = {
    "reminder": [
        "time",
        "remind_me",
        "record_date",
        "recorded_events_list",
        "cron_schedule",
        "cron_list",
        "cron_remove",
        "cron_update",
        "cron_run",
        "cron_status",
        "route_to_tam",
    ],
    # Finder: search/list → read, view, edit; save_result_page (e.g. HTML slides); run_skill (e.g. ppt-generation, html-slides); web_search.
    "finder": [
        "file_find",
        "folder_list",
        "document_read",
        "file_read",
        "file_write",
        "save_result_page",
        "get_file_view_link",
        "run_skill",
        "web_search",
    ],
    # Knowledge: KB tools only (+ time). Companion friend for direct search/add/remove/list on the indexed knowledge base.
    "knowledge": [
        "time",
        "knowledge_base_search",
        "knowledge_base_add",
        "knowledge_base_remove",
        "knowledge_base_list",
    ],
    # Tutor / academic friend: time + optional spawn and web; pair with friend_presets llm_ref for a dedicated GGUF.
    "tutor": [
        "time",
        "sessions_spawn",
        "models_list",
        "web_search",
    ],
    # Cursor: same as "bridge"; kept for backward compat. Prefer "bridge" for new bridge-style friends.
    "cursor": [
        "time",
        "route_to_plugin",
        "folder_list",
        "file_find",
    ],
    # Bridge: shared preset for all dev-bridge friends (Cursor, ClaudeCode, Trae). Only route_to_plugin + path discovery; no LLM tool loop for normal messages (pattern-routed in llm_loop).
    "bridge": [
        "time",
        "route_to_plugin",
        "folder_list",
        "file_find",
    ],
}


def load_friend_presets(config_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Load friend presets from YAML. Returns dict preset_name -> config (tools_preset, skills, plugins, etc.).
    If file missing or invalid, returns {}. Never raises.
    """
    if not config_path or not (config_path or "").strip():
        try:
            root = Path(__file__).resolve().parent.parent
            config_path = str(root / "config" / "friend_presets.yml")
        except Exception:
            return {}
    path = Path(config_path)
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    presets = data.get("presets")
    if not isinstance(presets, dict):
        return {}
    return dict(presets)


def format_preset_display_name(preset_id: str, preset_config: Optional[Dict[str, Any]] = None) -> str:
    """
    Human-readable label for Portal/Companion and the default friend name when creating users from preset checkboxes.
    Uses YAML ``display_name`` (or ``friend_display_name``) when set; otherwise capitalizes the preset id
    (e.g. knowledge -> Knowledge).
    """
    if isinstance(preset_config, dict):
        dn = (preset_config.get("display_name") or preset_config.get("friend_display_name") or "").strip()
        if dn:
            return dn
    k = (preset_id or "").strip().lower()
    if not k:
        return ""
    return k[0].upper() + k[1:] if len(k) > 1 else k.upper()


# When intent_router.skip_for_friend_presets is omitted, skip the router for these presets (dedicated Reminder / Finder / Knowledge chats).
_DEFAULT_SKIP_INTENT_ROUTER_PRESETS = frozenset({"reminder", "finder", "knowledge"})


def should_skip_intent_router_for_friend(
    preset_name: Optional[str],
    intent_router_config: Optional[Dict[str, Any]],
) -> bool:
    """
    If True, Core does not call the intent-router LLM for this turn: categories stay empty and tools/skills
    come from config profile intersected with the friend preset only. See docs_design/PresetFriendsAndIntentRouterDAG.md.
    """
    pn = (preset_name or "").strip().lower()
    if not pn:
        return False
    cfg = intent_router_config if isinstance(intent_router_config, dict) else {}
    raw = cfg.get("skip_for_friend_presets")
    if raw is None:
        allowed = _DEFAULT_SKIP_INTENT_ROUTER_PRESETS
    elif isinstance(raw, str):
        # Single preset or comma-separated (e.g. "reminder, finder, knowledge")
        parts = [p.strip().lower() for p in raw.replace("\n", ",").split(",")]
        allowed = {p for p in parts if p}
        if not allowed:
            return False
    elif isinstance(raw, (list, tuple)):
        if len(raw) == 0:
            return False
        allowed = {str(x).strip().lower() for x in raw if x is not None and str(x).strip()}
        # List of only blanks / whitespace must not skip the router for every preset
        if not allowed:
            return False
    else:
        return False
    if pn not in allowed:
        return False
    pc = get_friend_preset_config(pn)
    if not isinstance(pc, dict):
        return False
    return pc.get("tools_preset") is not None


def get_tool_names_for_preset(preset_name: str) -> Optional[List[str]]:
    """
    Return the list of tool names for the given preset (e.g. 'reminder', 'knowledge', 'finder').
    Returns None if preset unknown or has no tools_preset; otherwise list of tool names.
    """
    if not preset_name or not isinstance(preset_name, str):
        return None
    key = (preset_name or "").strip().lower()
    if not key:
        return None
    return list(TOOL_PRESETS[key]) if key in TOOL_PRESETS else None


def get_tool_names_for_preset_value(tools_preset_value: Union[str, List[str]]) -> Optional[List[str]]:
    """
    Resolve tools from tools_preset config value: string (single preset) or array of preset names (union).
    Returns combined list of tool names, or None if none resolved. Order: first preset's tools, then any new from others (no duplicates).
    """
    if tools_preset_value is None:
        return None
    if isinstance(tools_preset_value, str):
        return get_tool_names_for_preset(tools_preset_value)
    if isinstance(tools_preset_value, (list, tuple)):
        seen = set()
        result = []
        for name in tools_preset_value:
            if not isinstance(name, str) or not (name or "").strip():
                continue
            names = get_tool_names_for_preset(name.strip())
            if names:
                for t in names:
                    if t and t not in seen:
                        seen.add(t)
                        result.append(t)
        return result if result else None
    return None


def get_friend_preset_config(preset_name: str, config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Return the full preset config dict for preset_name (from YAML), or None if not found.
    """
    if not preset_name or not isinstance(preset_name, str):
        return None
    key = (preset_name or "").strip().lower()
    if not key:
        return None
    presets = load_friend_presets(config_path)
    return presets.get(key)


def trim_messages_to_last_n_turns(messages: List[Dict], n: int) -> List[Dict]:
    """
    Keep only the last n turns. One turn = one user message + following assistant/tool messages until next user.
    Used when preset has history: N (integer) to save context tokens.
    Never raises; skips non-dict entries when scanning for user messages.
    """
    if not isinstance(messages, list) or n <= 0:
        return messages
    user_indices = [
        i for i, m in enumerate(messages)
        if isinstance(m, dict) and (str(m.get("role") or "").strip().lower() == "user")
    ]
    if len(user_indices) <= n:
        return messages
    start = user_indices[-n]
    return messages[start:]
