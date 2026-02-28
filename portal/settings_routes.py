"""
Server-rendered settings pages. No JavaScript required.
Each section (Core, Advanced, LLM, etc.) is a separate URL; forms POST back to the server.
"""
import json
import html as html_module
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from portal import auth
from portal import config_api
from portal import config_backup
from portal import yaml_config
from portal.app import (
    _logged_in_page,
    _render_advanced_form,
    _render_core_form_html,
    _render_generic_form,
    _render_llm_form,
    _render_user_form,
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
    from portal.app import _get_session_username as _get
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
        form_html = _render_user_form(data)
    else:
        form_html = "<p class=\"error\">Unknown page.</p>"
    return _settings_page_html(page, form_html, saved=saved, error=error)


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
