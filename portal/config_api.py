"""
Portal config API: load and update the six config files with redaction and backup.
Used by GET/PATCH /api/config/<name>. Never raises; returns None or False on error.
"""
import copy
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    "skills_dir", "external_skills_dir", "skills_extra_dirs", "skills_disabled", "skills_and_plugins_config_file",
    "use_prompt_manager", "prompts_dir", "prompt_default_language", "prompt_cache_ttl_seconds",
    "auth_enabled", "auth_api_key", "core_public_url", "file_link_style", "file_static_prefix",
    "file_view_link_expiry_sec", "inbound_request_timeout_seconds",
    "pinggy", "push_notifications", "file_understanding",
    "llm_config_file", "endpoints",
    "portal_url", "portal_secret",  # optional; Portal is in-process on Core or standalone (no proxy)
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
    if isinstance(out.get("portal_secret"), str) and out["portal_secret"]:
        out["portal_secret"] = "***"
    pinggy = out.get("pinggy")
    if isinstance(pinggy, dict) and isinstance(pinggy.get("token"), str) and pinggy["token"]:
        out["pinggy"] = copy.deepcopy(pinggy)
        out["pinggy"]["token"] = "***"
    return out


def _redact_llm(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact api_key / api_key_name in cloud_models and local_models (list or dict)."""
    out = copy.deepcopy(data)
    for key in ("cloud_models", "local_models"):
        models = out.get(key)
        if isinstance(models, list):
            for entry in models:
                if isinstance(entry, dict):
                    if entry.get("api_key"):
                        entry["api_key"] = "***"
                    if entry.get("api_key_name"):
                        entry["api_key_name"] = "***"
        elif isinstance(models, dict):
            for _model_name, entry in models.items():
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


# Default password when creating a user without one (Portal user CRUD).
DEFAULT_NEW_USER_PASSWORD = "changeme"


def _friends_dicts_from_preset_names(preset_names: List[str]) -> List[Dict[str, Any]]:
    """Build friends list of dicts for user.yml: HomeClaw first, then one entry per preset. Never raises."""
    result: List[Dict[str, Any]] = [{"name": "HomeClaw", "type": "ai"}]
    if not isinstance(preset_names, list):
        return result
    try:
        path = str(get_config_path("friend_presets"))
        data = yaml_config.load_yml_preserving(path)
        presets = (data or {}).get("presets") if isinstance(data, dict) else None
        if not isinstance(presets, dict):
            return result
        for key in preset_names:
            k = (str(key) if key is not None else "").strip().lower()
            if not k or k == "homeclaw":
                continue
            if k in presets:
                display = k[0].upper() + k[1:] if len(k) > 1 else k.upper()
                result.append({"name": display, "preset": k, "type": "ai"})
    except Exception:
        pass
    return result


def add_user(body: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Add a user to user.yml. Returns (True, None) on success, (False, error_detail) on failure. Never raises."""
    if not isinstance(body, dict) or not (body.get("name") or "").strip():
        return False, "name required"
    name = str(body["name"]).strip()
    uid = (body.get("id") or name).strip() or name
    email = list(body.get("email") or []) if isinstance(body.get("email"), list) else []
    im = list(body.get("im") or []) if isinstance(body.get("im"), list) else []
    phone = list(body.get("phone") or []) if isinstance(body.get("phone"), list) else []
    permissions = list(body.get("permissions") or []) if isinstance(body.get("permissions"), list) else []
    user_type = str(body.get("type") or "normal").strip().lower() or "normal"
    if user_type not in ("normal", "companion"):
        user_type = "normal"
    username = (body.get("username") or "").strip() or None
    password = body.get("password")
    if password is not None and not isinstance(password, str):
        password = str(password) if password else None
    if password is not None and not (password or "").strip():
        password = None
    if password is None:
        password = DEFAULT_NEW_USER_PASSWORD
    if "friend_preset_names" in body and isinstance(body["friend_preset_names"], list):
        friends = _friends_dicts_from_preset_names(body["friend_preset_names"])
    else:
        friends = _friends_dicts_from_preset_names([])
    user_entry: Dict[str, Any] = {
        "id": uid,
        "name": name,
        "username": username,
        "password": password,
        "email": email,
        "im": im,
        "phone": phone,
        "permissions": permissions,
        "type": user_type,
        "friends": friends,
    }
    if not username:
        user_entry.pop("username", None)
    data = load_config("user")
    if data is None:
        data = {}
    users = list(data.get("users") or [])
    if not isinstance(users, list):
        users = []
    for u in users:
        if isinstance(u, dict) and ((u.get("name") or "").strip() == name or (u.get("id") or "").strip() == uid):
            return False, "User with same name or id already exists"
    users.append(user_entry)
    if not update_config("user", {"users": users}):
        return False, "Failed to save config"
    return True, None


def update_user(user_name: str, body: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Update a user in user.yml by name. Returns (True, None) on success, (False, error_detail) on failure."""
    if not isinstance(body, dict):
        return False, "JSON object required"
    data = load_config("user")
    if data is None:
        return False, "Config not found"
    users = list(data.get("users") or [])
    if not isinstance(users, list):
        return False, "Invalid users list"
    found_idx = None
    for i, u in enumerate(users):
        if isinstance(u, dict) and (u.get("name") or "").strip() == user_name:
            found_idx = i
            break
    if found_idx is None:
        return False, f"User '{user_name}' not found"
    found = dict(users[found_idx])
    name = (body.get("name") or found.get("name") or "").strip() or found.get("name")
    uid = (body.get("id") or name).strip() or name
    email = body["email"] if "email" in body else list(found.get("email") or [])
    if not isinstance(email, list):
        email = []
    im = body["im"] if "im" in body else list(found.get("im") or [])
    if not isinstance(im, list):
        im = []
    phone = body["phone"] if "phone" in body else list(found.get("phone") or [])
    if not isinstance(phone, list):
        phone = []
    permissions = body["permissions"] if "permissions" in body else list(found.get("permissions") or [])
    if not isinstance(permissions, list):
        permissions = []
    user_type = str(body.get("type") or found.get("type") or "normal").strip().lower() or "normal"
    if user_type not in ("normal", "companion"):
        user_type = "normal"
    username = body.get("username") if "username" in body else found.get("username")
    if username is not None and not str(username).strip():
        username = None
    else:
        username = str(username).strip() if username else None
    password = found.get("password")
    if "password" in body and body["password"] and str(body["password"]).strip() and str(body["password"]).strip() != "***":
        password = str(body["password"]).strip()
    if body.get("reset_password") and str(body["reset_password"]).strip() and len(str(body["reset_password"]).strip()) <= 512:
        password = str(body["reset_password"]).strip()
    if "friend_preset_names" in body and isinstance(body["friend_preset_names"], list):
        friends = _friends_dicts_from_preset_names(body["friend_preset_names"])
    elif "friends" in body:
        friends = list(body["friends"]) if isinstance(body["friends"], list) else list(found.get("friends") or [])
    else:
        friends = list(found.get("friends") or [])
    updated = {
        "id": uid,
        "name": name,
        "email": email,
        "im": im,
        "phone": phone,
        "permissions": permissions,
        "type": user_type,
        "friends": friends,
    }
    if username is not None:
        updated["username"] = username
    if password is not None:
        updated["password"] = password
    users[found_idx] = updated
    if not update_config("user", {"users": users}):
        return False, "Failed to save config"
    return True, None


def delete_user(user_name: str) -> Tuple[bool, Optional[str]]:
    """Remove a user from user.yml by name. Returns (True, None) on success, (False, error_detail) on failure."""
    data = load_config("user")
    if data is None:
        return False, "Config not found"
    users = list(data.get("users") or [])
    if not isinstance(users, list):
        return False, "Invalid users list"
    new_users = [u for u in users if isinstance(u, dict) and (u.get("name") or "").strip() != user_name]
    if len(new_users) == len(users):
        return False, f"User '{user_name}' not found"
    if not update_config("user", {"users": new_users}):
        return False, "Failed to save config"
    return True, None


def update_user_password(user_name: str, new_password: str) -> Tuple[bool, Optional[str]]:
    """Set a user's password. Returns (True, None) on success, (False, error_detail) on failure."""
    if not new_password or not isinstance(new_password, str) or len(new_password.strip()) > 512:
        return False, "password required (max 512 chars)"
    new_password = new_password.strip()
    data = load_config("user")
    if data is None:
        return False, "Config not found"
    users = list(data.get("users") or [])
    if not isinstance(users, list):
        return False, "Invalid users list"
    for i, u in enumerate(users):
        if isinstance(u, dict) and (u.get("name") or "").strip() == user_name:
            users[i] = {**u, "password": new_password}
            if not update_config("user", {"users": users}):
                return False, "Failed to save config"
            return True, None
    return False, f"User '{user_name}' not found"
