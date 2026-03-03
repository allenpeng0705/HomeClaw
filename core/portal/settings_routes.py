"""
Server-rendered settings pages. No JavaScript required.
Each section (Core, Advanced, LLM, etc.) is a separate URL; forms POST back to the server.
"""
import json
import html as html_module
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.portal import auth
from core.portal import config_api
from core.portal import config_backup
from core.portal import yaml_config
from core.portal.app import (
    _logged_in_page,
    _render_advanced_form,
    _render_core_form_html,
    _render_generic_form,
    _render_llm_form,
    _render_user_form,
    _render_user_list_and_actions,
    _render_user_create_form,
    _render_user_edit_form,
    _get_portal_users_list,
    _get_portal_friend_presets,
    _settings_nav_html,
    _settings_page_html,
    _form_body_from_data,
    SETTINGS_PAGES,
    _CORE_ADVANCED_KEYS,
    _FRIEND_PRESETS_KEYS,
)

router = APIRouter()


def _get_session_username(request: Request) -> Optional[str]:
    """Session check; import from app to avoid circular import at load."""
    from core.portal.app import _get_session_username as _get
    return _get(request)


def _get_settings_page_content(page: str, saved: bool = False, error: bool = False) -> str:
    """Load config(s), render form, return HTML content for this settings page."""
    if page == "core":
        data = config_api.load_config_for_api("core")
        form_html = _render_core_form_html(data)
    elif page == "advanced":
        data_core = config_api.load_config_for_api("core")
        data_llm = config_api.load_config_for_api("llm")
        data_friend = config_api.load_config_for_api("friend_presets")
        data_memory_kb = config_api.load_config_for_api("memory_kb")
        data_skills_and_plugins = config_api.load_config_for_api("skills_and_plugins")
        form_html = _render_advanced_form(
            data_core, data_llm, data_friend, data_memory_kb, data_skills_and_plugins
        )
    elif page == "llm":
        data = config_api.load_config_for_api("llm")
        form_html = _render_llm_form(data)
    elif page == "user":
        data = config_api.load_config_for_api("user")
        users = (data.get("users") or []) if isinstance(data, dict) else []
        form_html = _render_user_list_and_actions(users)
    else:
        form_html = "<p class=\"error\">Unknown page.</p>"
    return _settings_page_html(page, form_html, saved=saved, error=error)


def _get_user_by_name(name: str):
    """Load full user dict by name from user config (includes friends for preset pre-check)."""
    data = config_api.load_config("user")
    if not data or not isinstance(data.get("users"), list):
        return None
    for u in data["users"]:
        if isinstance(u, dict) and (u.get("name") or u.get("id") or "").strip() == name.strip():
            return u
    return None


def _portal_friends_from_preset_names(preset_names):
    """Build friends list: HomeClaw first, then one Friend per preset. Never raises."""
    try:
        from base.base import Friend
        from base.friend_presets import load_friend_presets
        from core.portal import config as portal_config
        result = [Friend(name="HomeClaw", relation=None, who=None, identity=None, preset=None, type="ai", user_id=None)]
        if not isinstance(preset_names, list):
            return result
        config_path = str(portal_config.get_config_dir() / "friend_presets.yml")
        presets = load_friend_presets(config_path) or {}
        if not isinstance(presets, dict):
            return result
        for key in preset_names:
            k = (str(key) if key is not None else "").strip().lower()
            if not k or k == "homeclaw":
                continue
            if k in presets:
                display = k[0].upper() + k[1:] if len(k) > 1 else k.upper()
                result.append(Friend(name=display, relation=None, who=None, identity=None, preset=k, type="ai", user_id=None))
    except Exception:
        pass
    return result


@router.get("/user/create", response_class=HTMLResponse)
def user_create_get(request: Request):
    """Show Create user form. Require login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    presets = _get_portal_friend_presets()
    saved = request.query_params.get("saved") == "1"
    error = request.query_params.get("error") == "1"
    content = _render_user_create_form(presets, saved=saved, error=error)
    return HTMLResponse(_logged_in_page("Create user", "settings", content, card_class="card card-wide"))


@router.post("/user/create", response_class=HTMLResponse)
async def user_create_post(request: Request):
    """Create user via config_api.add_user(); submit as POST /api/config/users with friend_preset_names."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    try:
        form = await request.form()
        name = (form.get("name") or "").strip()
        if not name:
            return RedirectResponse(url="/settings/user/create?error=1", status_code=302)
        username = (form.get("username") or "").strip() or None
        password = (form.get("password") or "").strip() or None
        user_type = (form.get("type") or "normal").strip().lower()
        if user_type not in ("normal", "companion"):
            user_type = "normal"
        email_raw = (form.get("email") or "").strip()
        email = [x.strip() for x in email_raw.splitlines() if x.strip()]
        im_raw = (form.get("im") or "").strip()
        im = [x.strip() for x in im_raw.splitlines() if x.strip()]
        phone_raw = (form.get("phone") or "").strip()
        phone = [x.strip() for x in phone_raw.splitlines() if x.strip()]
        preset_names = form.getlist("friend_preset_names") if hasattr(form, "getlist") else []
        if not preset_names and form.get("friend_preset_names"):
            preset_names = [form.get("friend_preset_names")]
        body = {
            "name": name,
            "username": username,
            "password": password,
            "type": user_type,
            "email": email,
            "im": im,
            "phone": phone,
            "permissions": [],
            "friend_preset_names": preset_names,
        }
        ok, _err = config_api.add_user(body)
        if ok:
            return RedirectResponse(url="/settings/user?saved=1", status_code=302)
    except Exception:
        pass
    return RedirectResponse(url="/settings/user/create?error=1", status_code=302)


@router.get("/user/{name}/edit", response_class=HTMLResponse)
def user_edit_get(request: Request, name: str):
    """Show Edit user form. Require login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    name = (name or "").strip()
    if not name:
        return RedirectResponse(url="/settings/user", status_code=302)
    user_d = _get_user_by_name(name)
    if not user_d:
        return RedirectResponse(url="/settings/user", status_code=302)
    user_d = dict(user_d)
    if user_d.get("password"):
        user_d["password"] = "***"
    presets = _get_portal_friend_presets()
    saved = request.query_params.get("saved") == "1"
    error = request.query_params.get("error") == "1"
    reset_ok = request.query_params.get("reset_ok") == "1"
    reset_err = request.query_params.get("reset_err") or None
    content = _render_user_edit_form(user_d, presets, saved=saved, error=error, reset_ok=reset_ok, reset_err=reset_err)
    return HTMLResponse(_logged_in_page("Edit user", "settings", content, card_class="card card-wide"))


@router.post("/user/{name}/edit", response_class=HTMLResponse)
async def user_edit_post(request: Request, name: str):
    """Update user via config_api.update_user(); PATCH with optional friend_preset_names."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    edit_url = "/settings/user/" + quote(name, safe="") + "/edit"
    try:
        form = await request.form()
        found = _get_user_by_name(name)
        if not found:
            return RedirectResponse(url="/settings/user", status_code=302)
        new_name = (form.get("name") or "").strip() or name
        username = (form.get("username") or "").strip() or None
        user_type = (form.get("type") or "normal").strip().lower()
        if user_type not in ("normal", "companion"):
            user_type = "normal"
        email_raw = (form.get("email") or "").strip()
        email = [x.strip() for x in email_raw.splitlines() if x.strip()]
        im_raw = (form.get("im") or "").strip()
        im = [x.strip() for x in im_raw.splitlines() if x.strip()]
        phone_raw = (form.get("phone") or "").strip()
        phone = [x.strip() for x in phone_raw.splitlines() if x.strip()]
        preset_names = form.getlist("friend_preset_names") if hasattr(form, "getlist") else []
        if not preset_names and form.get("friend_preset_names"):
            preset_names = [form.get("friend_preset_names")]
        body = {
            "name": new_name,
            "id": (form.get("id") or new_name).strip() or new_name,
            "username": username,
            "type": user_type,
            "email": email,
            "im": im,
            "phone": phone,
            "permissions": list(found.get("permissions") or []),
        }
        if preset_names:
            body["friend_preset_names"] = preset_names
        ok, _err = config_api.update_user(name, body)
        if ok:
            return RedirectResponse(url="/settings/user/" + quote(new_name, safe="") + "/edit?saved=1", status_code=302)
    except Exception:
        pass
    return RedirectResponse(url=edit_url + "?error=1", status_code=302)


@router.post("/user/{name}/delete", response_class=HTMLResponse)
async def user_delete_post(request: Request, name: str):
    """Delete user via config_api.delete_user(); redirect to user list."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    ok, _err = config_api.delete_user(name)
    if ok:
        return RedirectResponse(url="/settings/user?saved=1", status_code=302)
    return RedirectResponse(url="/settings/user?error=1", status_code=302)


@router.post("/user/{name}/reset-password", response_class=HTMLResponse)
async def user_reset_password_post(request: Request, name: str):
    """Reset user password via config_api.update_user_password(); calls reset-password API."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    edit_url = "/settings/user/" + quote(name, safe="") + "/edit"
    try:
        form = await request.form()
        new_password = (form.get("password") or "").strip()
        if not new_password or len(new_password) > 512:
            return RedirectResponse(url=edit_url + "?reset_err=Password+required", status_code=302)
        ok, err = config_api.update_user_password(name, new_password)
        if ok:
            return RedirectResponse(url=edit_url + "?reset_ok=1", status_code=302)
        return RedirectResponse(url=edit_url + "?reset_err=" + quote(err or "Failed", safe=""), status_code=302)
    except Exception:
        return RedirectResponse(url=edit_url + "?reset_err=Failed", status_code=302)


@router.get("", response_class=HTMLResponse)
def settings_index(request: Request):
    """Redirect to first settings page."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/settings/core", status_code=302)


@router.get("/{page}", response_class=HTMLResponse)
def settings_get(request: Request, page: str):
    """Show one settings page (Core, LLM, User, Advanced)."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    if page in ("memory_kb", "skills_and_plugins"):
        return RedirectResponse(url="/settings/advanced", status_code=302)
    valid = [p[0] for p in SETTINGS_PAGES]
    if page not in valid:
        return HTMLResponse("<p>Not found</p>", status_code=404)
    saved = request.query_params.get("saved") == "1"
    error = request.query_params.get("error") == "1"
    content = _get_settings_page_content(page, saved=saved, error=error)
    headers = {"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"}
    return HTMLResponse(_logged_in_page("Manage settings", "settings", content, card_class="card card-wide"), headers=headers)


@router.post("/{page}", response_class=HTMLResponse)
async def settings_post(request: Request, page: str):
    """Save form and redirect back to the same page."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    if page in ("memory_kb", "skills_and_plugins"):
        return RedirectResponse(url="/settings/advanced", status_code=302)
    valid = [p[0] for p in SETTINGS_PAGES]
    if page not in valid:
        return RedirectResponse(url="/settings/core", status_code=302)
    form_data = dict(await request.form())
    url = f"/settings/{page}"
    try:
        if page == "core":
            original = config_api.load_config_for_api("core")
            body = _form_body_from_data(form_data, original)
            if body and config_api.update_config("core", body):
                return RedirectResponse(url=url + "?saved=1", status_code=302)
        elif page == "advanced":
            data_core = config_api.load_config_for_api("core")
            data_llm = config_api.load_config_for_api("llm")
            data_friend = config_api.load_config_for_api("friend_presets")
            data_memory_kb = config_api.load_config_for_api("memory_kb")
            data_skills = config_api.load_config_for_api("skills_and_plugins")
            body_core = _form_body_from_data(form_data, data_core, _CORE_ADVANCED_KEYS)
            body_llm = _form_body_from_data(form_data, data_llm, ("hybrid_router",))
            body_friend = _form_body_from_data(form_data, data_friend, _FRIEND_PRESETS_KEYS)
            body_memory_kb = _form_body_from_data(
                form_data, data_memory_kb, tuple(yaml_config.WHITELIST_MEMORY_KB)
            )
            body_skills = _form_body_from_data(
                form_data, data_skills, tuple(yaml_config.WHITELIST_SKILLS_PLUGINS)
            )
            ok = True
            if body_core:
                ok = config_api.update_config("core", body_core) and ok
            if body_llm:
                ok = config_api.update_config("llm", body_llm) and ok
            if body_friend:
                ok = config_api.update_config("friend_presets", body_friend) and ok
            if body_memory_kb:
                ok = config_api.update_config("memory_kb", body_memory_kb) and ok
            if body_skills:
                ok = config_api.update_config("skills_and_plugins", body_skills) and ok
            if ok and (body_core or body_llm or body_friend or body_memory_kb or body_skills):
                return RedirectResponse(url=url + "?saved=1", status_code=302)
        elif page == "llm":
            original = config_api.load_config_for_api("llm")
            body = _form_body_from_data(form_data, original)
            if not body:
                pass
            else:
                # Parse main_llm_language: form sends comma-separated string
                lang = body.get("main_llm_language")
                if isinstance(lang, str) and lang.strip():
                    body["main_llm_language"] = [x.strip() for x in lang.split(",") if x.strip()]
                # Restore redacted api_key / api_key_name so we do not overwrite with "***"
                if "cloud_models" in body and isinstance(body["cloud_models"], list):
                    raw = config_api.load_config("llm")
                    raw_cloud = (raw or {}).get("cloud_models") or []
                    for entry in body["cloud_models"]:
                        if not isinstance(entry, dict):
                            continue
                        if entry.get("api_key") == "***" or entry.get("api_key_name") == "***":
                            rid = entry.get("id")
                            orig = next((x for x in raw_cloud if isinstance(x, dict) and x.get("id") == rid), None)
                            if orig:
                                if entry.get("api_key") == "***":
                                    entry["api_key"] = orig.get("api_key")
                                if entry.get("api_key_name") == "***":
                                    entry["api_key_name"] = orig.get("api_key_name")
                if config_api.update_config("llm", body):
                    return RedirectResponse(url=url + "?saved=1", status_code=302)
        elif page == "user":
            original = config_api.load_config_for_api("user")
            body = _form_body_from_data(form_data, original)
            if body and "users" in body and isinstance(body["users"], list):
                raw = config_api.load_config("user")
                raw_users = (raw or {}).get("users") or []
                for entry in body["users"]:
                    if not isinstance(entry, dict) or entry.get("password") != "***":
                        continue
                    uid = entry.get("id") or entry.get("username")
                    orig = next((u for u in raw_users if isinstance(u, dict) and (u.get("id") == uid or u.get("username") == uid)), None)
                    if orig and orig.get("password"):
                        entry["password"] = orig["password"]
                if config_api.update_config("user", body):
                    return RedirectResponse(url=url + "?saved=1", status_code=302)
        else:
            original = config_api.load_config_for_api(page)
            body = _form_body_from_data(form_data, original)
            if body and config_api.update_config(page, body):
                return RedirectResponse(url=url + "?saved=1", status_code=302)
    except Exception:
        pass
    return RedirectResponse(url=url + "?error=1", status_code=302)
