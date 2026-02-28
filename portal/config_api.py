"""
Portal config API: load and update the six config files with redaction and backup.
Used by GET/PATCH /api/config/<name>. Never raises; returns None or False on error.
"""
import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from portal import config_backup
from portal.config import get_config_dir
from portal import yaml_config

_log = logging.getLogger(__name__)

# Top-level keys Portal is allowed to merge for core.yml (subset of keys; secrets redacted on GET).
WHITELIST_CORE = frozenset({
    "name", "host", "port", "mode", "model_path", "silent", "log_to_console",
    "memory_kb_config_file", "use_workspace_bootstrap", "workspace_dir", "homeclaw_root",
    "notify_unknown_request", "outbound_markdown_format",
    "llm_max_concurrent_local", "llm_max_concurrent_cloud", "compaction",
    "skills_dir", "skills_extra_dirs", "skills_disabled", "skills_and_plugins_config_file",
    "use_prompt_manager", "prompts_dir", "prompt_default_language", "prompt_cache_ttl_seconds",
    "auth_enabled", "auth_api_key", "core_public_url", "file_link_style", "file_static_prefix",
    "file_view_link_expiry_sec", "inbound_request_timeout_seconds",
    "pinggy", "push_notifications", "file_understanding", "llama_cpp", "completion",
    "llm_config_file", "endpoints",
})


def _config_dir() -> Path:
    return Path(get_config_dir())


def get_config_path(name: str) -> Path:
    """Path to current config file. Use CONFIG_NAMES from config_backup for valid names."""
    return _config_dir() / f"{name}.yml"


def _redact_core(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with secrets replaced by placeholder. Never mutates input."""
    out = copy.deepcopy(data)
    if isinstance(out.get("auth_api_key"), str) and out["auth_api_key"]:
        out["auth_api_key"] = "***"
    pinggy = out.get("pinggy")
    if isinstance(pinggy, dict) and isinstance(pinggy.get("token"), str) and pinggy["token"]:
        out["pinggy"] = copy.deepcopy(pinggy)
        out["pinggy"]["token"] = "***"
    return out


def _redact_llm(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact api_key / api_key_name in cloud_models and local_models entries."""
    out = copy.deepcopy(data)
    for key in ("cloud_models", "local_models"):
        models = out.get(key)
        if not isinstance(models, dict):
            continue
        for model_name, entry in models.items():
            if isinstance(entry, dict):
                if entry.get("api_key"):
                    entry["api_key"] = "***"
                if entry.get("api_key_name"):
                    entry["api_key_name"] = "***"
    return out


def _redact_users(users: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return copy of user list with password fields redacted."""
    out = []
    for u in users:
        u_copy = copy.deepcopy(u)
        if isinstance(u_copy.get("password"), str) and u_copy["password"]:
            u_copy["password"] = "***"
        out.append(u_copy)
    return out


def load_config(name: str) -> Optional[Dict[str, Any]]:
    """Load config file; return dict (or None on error). No redaction. Never raises."""
    if name not in config_backup.CONFIG_NAMES:
        return None
    path = get_config_path(name)
    data = yaml_config.load_yml_preserving(str(path))
    if data is None:
        return None
    return data if isinstance(data, dict) else {}


def load_config_for_api(name: str) -> Optional[Dict[str, Any]]:
    """Load config and return dict suitable for API (redacted). Never raises."""
    data = load_config(name)
    if data is None:
        if name == "user":
            return {"users": []}
        return None
    if name == "core":
        # Return only whitelisted keys, redacted
        filtered = {k: v for k, v in data.items() if k in WHITELIST_CORE}
        return _redact_core(filtered)
    if name == "llm":
        return _redact_llm(data)
    if name == "user":
        users = data.get("users")
        if not isinstance(users, list):
            return {"users": []}
        return {"users": _redact_users(users)}
    return data


def update_config(name: str, body: Dict[str, Any]) -> bool:
    """Backup current, then merge body into config. Only whitelisted keys applied. Never raises."""
    if name not in config_backup.CONFIG_NAMES:
        return False
    config_backup.prepare_for_update(name)
    path = str(get_config_path(name))
    if name == "core":
        return yaml_config.update_yml_preserving(path, body, whitelist=WHITELIST_CORE)
    if name == "llm":
        return yaml_config.update_yml_preserving(path, body, whitelist=yaml_config.WHITELIST_LLM)
    if name == "memory_kb":
        return yaml_config.update_yml_preserving(path, body, whitelist=yaml_config.WHITELIST_MEMORY_KB)
    if name == "skills_and_plugins":
        return yaml_config.update_yml_preserving(path, body, whitelist=yaml_config.WHITELIST_SKILLS_PLUGINS)
    if name == "friend_presets":
        return yaml_config.update_yml_preserving(path, body, whitelist=yaml_config.WHITELIST_FRIEND_PRESETS)
    if name == "user":
        # Only allow merging top-level "users" key (full list replace)
        if "users" in body and isinstance(body["users"], list):
            return yaml_config.update_yml_preserving(path, {"users": body["users"]}, whitelist=frozenset({"users"}))
        return False
    return False
