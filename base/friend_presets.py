"""
Friend presets: load preset config from YAML and resolve tool lists per preset.
See docs_design/FriendConfigFrameworkImplementation.md.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

# Tool names per preset. Must match names registered in the tool registry (e.g. tools/builtin.py).
# Reminder: cron/reminder/scheduling only.
TOOL_PRESETS: Dict[str, List[str]] = {
    "reminder": [
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
    # Note uses only Cognee for memory (memory_sources: [cognee]); no append_agent_memory/append_daily_memory.
    "note": [
        "document_read",
        "file_read",
        "file_write",
        "folder_list",
        "file_find",
        "save_result_page",
        "get_file_view_link",
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


def get_tool_names_for_preset(preset_name: str) -> Optional[List[str]]:
    """
    Return the list of tool names for the given preset (e.g. 'reminder', 'note', 'finder').
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
