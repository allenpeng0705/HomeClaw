"""
Config API routes: GET/PATCH /api/config/core, GET/POST/PATCH/DELETE /api/config/users.
Same auth as /inbound (auth.verify_inbound_auth).
"""
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from base.util import Util
from base.base import User, Friend
from base.workspace import ensure_user_sandbox_folders

# All top-level keys in core.yml that are safe to read/write via API (nested sections merged on PATCH).
CONFIG_CORE_WHITELIST = frozenset({
    "name", "host", "port", "mode", "model_path", "silent", "use_memory", "memory_backend", "memory_check_before_add", "default_location",
    "profile", "workspace_dir", "use_workspace_bootstrap", "use_agent_memory_file", "agent_memory_path",
    "agent_memory_max_chars", "use_agent_memory_search", "agent_memory_vector_collection",
    "agent_memory_bootstrap_max_chars", "agent_memory_bootstrap_max_chars_local",
    "use_daily_memory", "daily_memory_dir", "session", "notify_unknown_request", "outbound_markdown_format",
    "llm_max_concurrent_local", "llm_max_concurrent_cloud", "compaction", "use_tools", "use_skills", "skills_dir",
    "skills_max_in_prompt", "plugins_max_in_prompt",
    "plugins_description_max_chars", "skills_use_vector_search", "skills_vector_collection",
    "skills_max_retrieved", "skills_similarity_threshold", "skills_refresh_on_startup", "skills_test_dir",
    "skills_incremental_sync", "plugins_use_vector_search", "plugins_vector_collection",
    "plugins_max_retrieved", "plugins_similarity_threshold", "plugins_refresh_on_startup",
    "system_plugins_auto_start", "system_plugins", "system_plugins_env", "orchestrator_unified_with_tools",
    "orchestrator_timeout_seconds", "inbound_request_timeout_seconds", "use_prompt_manager", "prompts_dir", "prompt_default_language",
    "prompt_cache_ttl_seconds", "auth_enabled", "auth_api_key", "core_public_url", "tools", "result_viewer", "knowledge_base",
    "file_understanding", "llama_cpp", "completion", "local_models", "cloud_models", "main_llm",
    "embedding_llm", "main_llm_language", "embedding_host", "embedding_port", "main_llm_host", "main_llm_port",
    "database", "vectorDB", "graphDB", "cognee", "memory_summarization",
})
CONFIG_CORE_BOOL_KEYS = frozenset({
    "silent", "use_memory", "auth_enabled", "use_tools", "use_skills",
    "use_workspace_bootstrap", "use_agent_memory_file", "use_agent_memory_search", "use_daily_memory", "memory_check_before_add",
    "use_prompt_manager", "system_plugins_auto_start", "skills_use_vector_search", "skills_refresh_on_startup",
    "skills_incremental_sync", "plugins_use_vector_search", "plugins_refresh_on_startup",
    "orchestrator_unified_with_tools",
})


def _deep_merge(target: dict, source: dict) -> None:
    """Merge source into target in-place. Nested dicts are merged; lists and other values replace."""
    for k, v in source.items():
        if k in target and isinstance(target[k], dict) and isinstance(v, dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v


def _merge_models_list(existing: list, incoming: list) -> list:
    """Merge list of model dicts by 'id'. Preserve order and existing api_key when incoming has '***' or empty."""
    incoming_by_id = {str(m.get("id")): m for m in (incoming or []) if isinstance(m, dict) and m.get("id")}
    result = []
    for m in (existing or []):
        if not isinstance(m, dict):
            result.append(m)
            continue
        copy = dict(m)
        eid = str(copy.get("id")) if copy.get("id") else None
        if eid and eid in incoming_by_id:
            for key, val in incoming_by_id[eid].items():
                if key == "api_key" and (val is None or val == "***" or (isinstance(val, str) and val.strip() == "")):
                    continue
                copy[key] = val
        result.append(copy)
    return result


def _redact_config(obj, redact_keys: frozenset = frozenset({"auth_api_key", "api_key"})):
    """Return a copy of obj with sensitive keys replaced by '***'. Recurses into dicts and lists of dicts."""
    if isinstance(obj, dict):
        return {k: ("***" if k in redact_keys else _redact_config(v, redact_keys)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_config(item, redact_keys) for item in obj]
    return obj


def get_api_config_core_get_handler(core):  # noqa: ARG001
    """Return handler for GET /api/config/core."""
    async def api_config_core_get():
        """Return current core config (whitelisted keys only). auth_api_key and nested api_key redacted as '***'."""
        try:
            path = Path(Util().config_path()) / "core.yml"
            if not path.exists():
                return JSONResponse(status_code=404, content={"detail": "core.yml not found"})
            data = Util().load_yml_config(str(path)) or {}
            out = {k: _redact_config(v) for k, v in data.items() if k in CONFIG_CORE_WHITELIST}
            return JSONResponse(content=out)
        except Exception as e:
            logger.exception("Config core get failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_config_core_get


def get_api_config_core_patch_handler(core):  # noqa: ARG001
    """Return handler for PATCH /api/config/core."""
    async def api_config_core_patch(request: Request):
        """Update whitelisted keys in core.yml. Nested dicts are deep-merged; lists and scalars replace. Never overwrites if core.yml could not be loaded (avoids corrupting the file)."""
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return JSONResponse(status_code=400, content={"detail": "JSON object required"})
            path = Path(Util().config_path()) / "core.yml"
            if not path.exists():
                return JSONResponse(status_code=404, content={"detail": "core.yml not found"})
            data = Util().load_yml_config(str(path)) or {}
            try:
                if not data and path.stat().st_size > 0:
                    return JSONResponse(status_code=400, content={"detail": "core.yml could not be loaded (parse error?). Fix the file manually; do not overwrite."})
            except OSError:
                pass
            for k, v in body.items():
                if k not in CONFIG_CORE_WHITELIST:
                    continue
                if k == "auth_api_key" and (v == "***" or v is None or v == ""):
                    continue
                if k == "port":
                    data[k] = int(v) if v is not None else 9000
                elif k in CONFIG_CORE_BOOL_KEYS:
                    data[k] = bool(v) if v is not None else False
                elif k in ("cloud_models", "local_models") and isinstance(v, list) and isinstance(data.get(k), list):
                    data[k] = _merge_models_list(data[k], v)
                elif isinstance(v, dict) and isinstance(data.get(k), dict):
                    _deep_merge(data[k], v)
                else:
                    data[k] = v
            Util().update_yaml_preserving_comments(str(path), data)
            return JSONResponse(content={"result": "ok"})
        except Exception as e:
            logger.exception("Config core patch failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_config_core_patch


def get_api_config_users_get_handler(core):  # noqa: ARG001
    """Return handler for GET /api/config/users."""
    async def api_config_users_get():
        """Return list of users from user.yml. Companion app / WebChat / control UI list all users and chat with each separately. Response: { \"users\": [ { \"id\", \"name\", \"type\", \"who\", \"email\", \"im\", \"phone\", \"permissions\" }, ... ] }."""
        try:
            users = Util().get_users() or []
            out = []
            for u in users:
                entry = {
                    "id": getattr(u, "id", None) or u.name,
                    "name": u.name,
                    "type": str(getattr(u, "type", None) or "normal").strip().lower() or "normal",
                    "email": list(getattr(u, "email", []) or []),
                    "im": list(getattr(u, "im", []) or []),
                    "phone": list(getattr(u, "phone", []) or []),
                    "permissions": list(getattr(u, "permissions", []) or []),
                }
                if getattr(u, "username", None) and str(u.username).strip():
                    entry["username"] = str(u.username).strip()
                who = getattr(u, "who", None)
                if isinstance(who, dict) and who:
                    entry["who"] = who
                friends = getattr(u, "friends", None)
                if isinstance(friends, list) and friends:
                    entry["friends"] = [
                        {"name": getattr(f, "name", ""), "relation": getattr(f, "relation", None), "who": getattr(f, "who", None), "identity": getattr(f, "identity", None)}
                        for f in friends if hasattr(f, "name")
                    ]
                out.append(entry)
            return JSONResponse(content={"users": out})
        except Exception as e:
            logger.exception("Config users get failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_config_users_get


def get_api_config_users_post_handler(core):  # noqa: ARG001
    """Return handler for POST /api/config/users."""
    async def api_config_users_post(request: Request):
        """Add a user to user.yml."""
        try:
            body = await request.json()
            if not isinstance(body, dict) or not body.get("name"):
                return JSONResponse(status_code=400, content={"detail": "name required"})
            name = str(body["name"]).strip()
            uid = (body.get("id") or name).strip() or name
            email = list(body.get("email") or []) if isinstance(body.get("email"), list) else []
            im = list(body.get("im") or []) if isinstance(body.get("im"), list) else []
            phone = list(body.get("phone") or []) if isinstance(body.get("phone"), list) else []
            permissions = list(body.get("permissions") or []) if isinstance(body.get("permissions"), list) else []
            skill_api_keys = None
            try:
                if isinstance(body.get("skill_api_keys"), dict):
                    skill_api_keys = {str(k): str(v).strip() for k, v in body["skill_api_keys"].items() if k and v and str(v).strip()}
            except Exception:
                skill_api_keys = None
            user_type = str(body.get("type") or "normal").strip().lower() or "normal"
            if user_type not in ("normal", "companion"):
                user_type = "normal"
            who = body.get("who")
            if not isinstance(who, dict):
                who = None
            username = (body.get("username") or "").strip() or None
            password = body.get("password")
            if password is not None and not isinstance(password, str):
                password = str(password) if password else None
            if password is not None and not (password or "").strip():
                password = None
            friends = User._parse_friends(body.get("friends")) if "friends" in body else None
            if friends is None:
                friends = [Friend(name="HomeClaw", relation=None, who=None, identity=None)]
            user = User(
                name=name, id=uid, email=email, im=im, phone=phone, permissions=permissions,
                username=username, password=password, skill_api_keys=skill_api_keys, type=user_type, who=who, friends=friends,
            )
            Util().add_user(user)
            root_str = (getattr(Util().get_core_metadata(), "homeclaw_root", None) or "").strip()
            if root_str and uid:
                try:
                    ensure_user_sandbox_folders(root_str, [uid])
                    from tools.builtin import build_and_save_sandbox_paths_json
                    build_and_save_sandbox_paths_json()
                except Exception:
                    pass
            return JSONResponse(content={"result": "ok", "name": name})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": str(e)})
        except Exception as e:
            logger.exception("Config users post failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_config_users_post


def get_api_config_users_patch_handler(core):  # noqa: ARG001
    """Return handler for PATCH /api/config/users/{user_name}."""
    async def api_config_users_patch(user_name: str, request: Request):
        """Update a user in user.yml by name. Body: name, id, email, im, phone, permissions."""
        try:
            body = await request.json()
            if not isinstance(body, dict):
                return JSONResponse(status_code=400, content={"detail": "JSON object required"})
            users = Util().get_users() or []
            found = next((u for u in users if u.name == user_name), None)
            if not found:
                return JSONResponse(status_code=404, content={"detail": f"User '{user_name}' not found"})
            name = (body.get("name") or found.name or "").strip() or found.name
            uid = (body.get("id") or name).strip() or name
            def _list(bkey, attr):
                if bkey not in body:
                    return list(getattr(found, attr, []) or [])
                v = body[bkey]
                return list(v) if isinstance(v, list) else []
            email = _list("email", "email")
            im = _list("im", "im")
            phone = _list("phone", "phone")
            permissions = _list("permissions", "permissions")
            skill_api_keys = getattr(found, "skill_api_keys", None) if found else None
            try:
                if "skill_api_keys" in body and isinstance(body.get("skill_api_keys"), dict):
                    skill_api_keys = {str(k): str(v).strip() for k, v in body["skill_api_keys"].items() if k and v and str(v).strip()}
            except Exception:
                skill_api_keys = getattr(found, "skill_api_keys", None) if found else None
            user_type = str(body.get("type") or getattr(found, "type", None) or "normal").strip().lower() or "normal"
            if user_type not in ("normal", "companion"):
                user_type = "normal"
            who = body.get("who") if "who" in body else getattr(found, "who", None)
            if not isinstance(who, dict):
                who = None
            username = (body.get("username") or "").strip() if "username" in body else getattr(found, "username", None)
            if username is not None and not str(username).strip():
                username = None
            else:
                username = str(username).strip() if username else None
            password = body.get("password") if "password" in body else getattr(found, "password", None)
            if password is not None and not isinstance(password, str):
                password = str(password) if password else None
            if password is not None and not (password or "").strip():
                password = None
            friends = User._parse_friends(body.get("friends")) if "friends" in body else getattr(found, "friends", None)
            if friends is None:
                friends = [Friend(name="HomeClaw", relation=None, who=None, identity=None)]
            updated = User(
                name=name, id=uid, email=email, im=im, phone=phone, permissions=permissions,
                username=username, password=password, skill_api_keys=skill_api_keys, type=user_type, who=who, friends=friends,
            )
            idx = users.index(found)
            users[idx] = updated
            User.validate_no_overlapping_channel_ids(users)
            Util().save_users(users)
            return JSONResponse(content={"result": "ok", "name": name})
        except ValueError as e:
            return JSONResponse(status_code=400, content={"detail": str(e)})
        except Exception as e:
            logger.exception("Config users patch failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_config_users_patch


def get_api_config_users_delete_handler(core):  # noqa: ARG001
    """Return handler for DELETE /api/config/users/{user_name}."""
    async def api_config_users_delete(user_name: str):
        """Remove a user from user.yml by name."""
        try:
            users = Util().get_users() or []
            for u in users:
                if u.name == user_name:
                    Util().remove_user(u)
                    return JSONResponse(content={"result": "ok", "name": user_name})
            return JSONResponse(status_code=404, content={"detail": f"User '{user_name}' not found"})
        except Exception as e:
            logger.exception("Config users delete failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e)})
    return api_config_users_delete
