"""
Portal on Core: serve Portal in-process at /portal-ui (same web server as Core). No proxy; no portal_url.
When Core runs from project root, Portal is mounted at /portal-ui. When Core is not running, run Portal standalone (python -m main portal) at http://127.0.0.1:18472 — two servers, same site.
POST /api/portal/auth for token; Portal handles its own login/session.
"""
import base64
import os
import re
import secrets
import sys
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from base.util import Util


def _ensure_core_importable():
    """Ensure the directory containing the core package (project root) is first on sys.path so portal can be imported."""
    try:
        # This file is core/routes/portal_proxy.py -> parent.parent = project root (dir containing core/)
        _here = Path(__file__).resolve().parent
        _project_root = _here.parent.parent
        _root_str = os.path.abspath(os.path.normpath(str(_project_root)))
        if not sys.path or sys.path[0] != _root_str:
            sys.path.insert(0, _root_str)
    except Exception:
        pass


# Lazy-load portal.auth only when needed (after path is set in route_registration).
_portal_auth_module = None

def _get_portal_auth():
    """Return portal.auth module or None if not loadable. Used for admin auth."""
    global _portal_auth_module
    if _portal_auth_module is not None:
        return _portal_auth_module
    _ensure_core_importable()
    try:
        from portal import auth as m
        _portal_auth_module = m
        return m
    except ImportError:
        return None

# In-memory token store: token -> (username, expires_at). Purged on validation.
_PORTAL_ADMIN_TOKENS: dict[str, tuple[str, float]] = {}
_TOKEN_TTL_SEC = 3600  # 1 hour
# Last ImportError message when portal.app failed to load (for fallback response).
_portal_import_error: str | None = None

def _get_portal_secret() -> str:
    """Portal secret for API auth. Empty if not configured."""
    try:
        meta = Util().get_core_metadata()
        return (getattr(meta, "portal_secret", None) or os.environ.get("PORTAL_SECRET") or "").strip()
    except Exception:
        return ""


def should_proxy_config() -> bool:
    """False: Core never proxies config; Portal is served in-process or run standalone."""
    return False


def should_use_portal_in_process() -> bool:
    """True when Portal app can be imported (portal) and served at /portal-ui on Core."""
    _ensure_core_importable()
    try:
        import portal.app  # noqa: F401
        return True
    except ImportError as e:
        global _portal_import_error
        _portal_import_error = str(e)
        _root = (Path(__file__).resolve().parent.parent.parent)  # project root
        logger.warning(
            "Portal in-process not available (import portal.app failed): {} (sys.path[0]={!r}, project_root={!r})",
            e, sys.path[0] if sys.path else None, str(_root),
        )
        return False


def get_portal_app_for_mount():
    """Return Portal's FastAPI app for mounting at /portal-ui. Use only when should_use_portal_in_process()."""
    _ensure_core_importable()
    from portal.app import app
    return app


PREFIX = "/portal-ui"


def _rewrite_location_prefix(location: str) -> str:
    """Rewrite Location so client sees /portal-ui/... (in-process mount; no portal_base)."""
    if not location or not location.strip():
        return location
    loc = location.strip()
    if loc.startswith(PREFIX):
        return loc
    if loc.startswith("/"):
        return f"{PREFIX.rstrip('/')}{loc}"
    return f"{PREFIX}/{loc}"


# Root-relative URL attributes in HTML that must be prefixed when Portal is under /portal-ui
_HTML_URL_ATTRS = re.compile(
    r'\b(href|action|src)=["\']/(?!portal-ui/)',
    re.IGNORECASE,
)
# Inline script fetch() etc.: "/api/portal/ or '/api/portal/ -> add /portal-ui prefix (avoid double-replace)
_HTML_API_PORTAL = re.compile(r'(["\'])(?!/portal-ui)/api/portal/')


def _rewrite_html_prefix(html: str) -> str:
    """Prefix root-relative URLs in HTML with /portal-ui so they work when mounted (links, forms, and API paths in script)."""
    html = _HTML_URL_ATTRS.sub(r'\1="/portal-ui/', html)
    html = _HTML_API_PORTAL.sub(r'\1/portal-ui/api/portal/', html)
    return html


class _PortalUIInProcessMiddleware(BaseHTTPMiddleware):
    """Rewrite response Location/Set-Cookie and HTML root-relative URLs for /portal-ui when Portal is mounted on Core."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(PREFIX):
            return await call_next(request)
        response = await call_next(request)
        if not hasattr(response, "headers") or not response.headers:
            return response
        # Rewrite Location and Set-Cookie so redirects and cookies work under /portal-ui
        for k in list(response.headers.keys()):
            k_lower = k.lower()
            if k_lower == "location":
                v = response.headers[k]
                new_v = _rewrite_location_prefix(str(v) if v else "")
                if new_v != v:
                    response.headers[k] = new_v
            elif k_lower == "set-cookie":
                v = str(response.headers[k]) if response.headers[k] else ""
                if "path=" in v.lower():
                    v = v.replace("path=/", "path=/portal-ui/").replace("path=/portal-ui/", "path=/portal-ui")
                else:
                    v = (v.rstrip(";") + "; Path=/portal-ui") if v else "Path=/portal-ui"
                response.headers[k] = v
        # Rewrite root-relative URLs in HTML so links, forms, and static assets work under /portal-ui
        ct = (response.headers.get("content-type") or "").lower()
        if "text/html" in ct and getattr(response, "status_code", 0) == 200:
            try:
                raw = None
                if hasattr(response, "body") and response.body is not None:
                    raw = response.body
                elif getattr(response, "body_iterator", None):
                    raw = b"".join([chunk async for chunk in response.body_iterator])
                if raw:
                    text = raw.decode("utf-8", errors="replace")
                    rewritten = _rewrite_html_prefix(text)
                    if rewritten != text:
                        return Response(
                            content=rewritten.encode("utf-8"),
                            status_code=200,
                            media_type="text/html; charset=utf-8",
                            headers=dict(response.headers),
                        )
                    if getattr(response, "body_iterator", None):
                        return Response(content=raw, status_code=200, media_type=ct, headers=dict(response.headers))
            except Exception as e:
                logger.warning("Portal UI HTML rewrite failed: {}", e)
        return response


def _verify_portal_admin(username: str, password: str) -> bool:
    """True if username/password match Portal admin (same file/env)."""
    portal_auth = _get_portal_auth()
    if not portal_auth:
        return False
    return portal_auth.verify_portal_admin(username, password)


def _purge_expired_tokens() -> None:
    """Remove expired entries from _PORTAL_ADMIN_TOKENS."""
    now = time.time()
    expired = [t for t, (_, exp) in _PORTAL_ADMIN_TOKENS.items() if exp <= now]
    for t in expired:
        _PORTAL_ADMIN_TOKENS.pop(t, None)


def get_portal_admin_from_request(request: Request) -> str | None:
    """Return username if request has valid portal admin auth (Bearer token, Basic, or query token). Else None. Never raises."""
    try:
        _purge_expired_tokens()
        now = time.time()
        # 1. Authorization: Bearer <token>
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token and token in _PORTAL_ADMIN_TOKENS:
                username, exp = _PORTAL_ADMIN_TOKENS[token]
                if exp > now:
                    return username
            return None
        # 2. Query param token= (for WebView that can't set headers)
        token = (request.query_params.get("token") or "").strip()
        if token and token in _PORTAL_ADMIN_TOKENS:
            username, exp = _PORTAL_ADMIN_TOKENS[token]
            if exp > now:
                return username
        # 3. Authorization: Basic base64(username:password)
        if auth_header.startswith("Basic "):
            try:
                raw = base64.b64decode(auth_header[6:].strip()).decode("utf-8")
                if ":" in raw:
                    u, p = raw.split(":", 1)
                    if _verify_portal_admin(u.strip(), p):
                        return u.strip()
            except Exception:
                pass
    except Exception:
        pass
    return None


async def post_portal_auth_handler(request: Request) -> Response:
    """POST /api/portal/auth: body { username, password }. If valid, return { token } (TTL 1h). Else 401. Never raises."""
    if not _get_portal_auth():
        return JSONResponse(status_code=503, content={"detail": "Portal admin auth not available"})
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"detail": "JSON body with username and password required"})
        username = (body.get("username") or "").strip()
        password = body.get("password")
        if password is not None and not isinstance(password, str):
            password = str(password)
        else:
            password = (password or "").strip()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "JSON body with username and password required"})
    if not username or not password:
        return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})
    if not _verify_portal_admin(username, password):
        return JSONResponse(status_code=401, content={"detail": "Invalid username or password"})
    token = secrets.token_urlsafe(32)
    _PORTAL_ADMIN_TOKENS[token] = (username, time.time() + _TOKEN_TTL_SEC)
    return JSONResponse(content={"token": token})


async def proxy_request_to_portal(request: Request) -> Response:
    """No longer used: config is not proxied. Portal is in-process on Core or run standalone."""
    return JSONResponse(status_code=503, content={"detail": "Config proxy disabled. Portal is served in-process on Core or run standalone (python -m main portal)."})


def _portal_ui_fallback_detail() -> str:
    return (
        "Portal runs as its own web server. Run: python -m main portal — then open http://127.0.0.1:18472 "
        "(or set PORTAL_PORT). Core does not serve Portal."
    )


async def get_portal_proxy_status_handler(_request: Request) -> Response:
    """GET /api/portal/proxy-status: Portal runs as its own server; Core does not serve it."""
    return JSONResponse(
        status_code=200,
        content={
            "portal_reachable": False,
            "detail": _portal_ui_fallback_detail(),
        },
    )


def get_portal_ui_fallback_response() -> Response:
    """Return 503 with message when Portal is not loadable (used instead of proxy)."""
    content = {"detail": _portal_ui_fallback_detail()}
    if _portal_import_error:
        content["import_error"] = _portal_import_error
    return JSONResponse(status_code=503, content=content)


def get_portal_ui_in_process_middleware():
    """Return the middleware class for rewriting Portal responses when mounted at /portal-ui. Use when should_use_portal_in_process()."""
    return _PortalUIInProcessMiddleware


def get_portal_ui_handler():
    """Fallback when Portal not loadable: GET /portal-ui returns 503 with instructions."""
    async def handler(_request: Request):
        return get_portal_ui_fallback_response()
    return handler


def get_portal_ui_path_handler():
    """Fallback when Portal not loadable: GET /portal-ui/{path} returns 503 with instructions."""
    async def handler(_request: Request, path: str):
        return get_portal_ui_fallback_response()
    return handler
