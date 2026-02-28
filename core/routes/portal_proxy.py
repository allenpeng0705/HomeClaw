"""
Portal proxy: when portal_url is set in Core config, forward /api/config/* to Portal (Phase 4.1)
and reverse-proxy /portal-ui and /portal-ui/* to Portal's Web UI (Phase 4.2).
Phase 5: Portal admin auth — POST /api/portal/auth issues token; /portal-ui and config proxy require token or Basic.
"""
import base64
import os
import secrets
import time
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger

from base.util import Util
import httpx

try:
    from portal import auth as portal_auth
except ImportError:
    portal_auth = None  # Portal not on path; auth will fail

# In-memory token store: token -> (username, expires_at). Purged on validation.
_PORTAL_ADMIN_TOKENS: dict[str, tuple[str, float]] = {}
_TOKEN_TTL_SEC = 3600  # 1 hour


def _get_portal_url() -> str:
    """Portal base URL from config or env. Empty if not configured."""
    try:
        meta = Util().get_core_metadata()
        url = (getattr(meta, "portal_url", None) or os.environ.get("PORTAL_URL") or "").strip()
        return url
    except Exception:
        return ""


def _get_portal_secret() -> str:
    """Portal secret for X-Portal-Secret header. Empty if not configured."""
    try:
        meta = Util().get_core_metadata()
        return (getattr(meta, "portal_secret", None) or os.environ.get("PORTAL_SECRET") or "").strip()
    except Exception:
        return ""


def should_proxy_config() -> bool:
    """True when Core should forward /api/config/* requests to Portal."""
    return bool(_get_portal_url())


def _verify_portal_admin(username: str, password: str) -> bool:
    """True if username/password match Portal admin (same file/env)."""
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
    if not portal_auth:
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
    """Forward the current request to Portal (method, path, query, body, headers + X-Portal-Secret). Phase 5: callers must ensure portal admin auth already checked (403 if not). Return response or 502/503 on error."""
    base = _get_portal_url().rstrip("/")
    if not base:
        return JSONResponse(status_code=502, content={"detail": "Portal URL not configured"})
    secret = _get_portal_secret()
    path = request.url.path
    query = str(request.url.query)
    url = f"{base}{path}" + ("?" + query if query else "")
    headers = dict(request.headers)
    # Drop headers that shouldn't be forwarded; drop client auth so Portal only sees X-Portal-Secret
    drop_lower = frozenset(("host", "connection", "transfer-encoding", "authorization"))
    for k in list(headers.keys()):
        if k.lower() in drop_lower:
            headers.pop(k, None)
    if secret:
        headers["X-Portal-Secret"] = secret
    try:
        body = await request.body()
    except Exception as e:
        logger.warning("Portal proxy: failed to read body: {}", e)
        return JSONResponse(status_code=500, content={"detail": "Failed to read request body"})
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
        # Forward status and body; drop hop-by-hop headers
        skip_headers = frozenset({"connection", "transfer-encoding", "keep-alive"})
        response_headers = [(k, v) for k, v in r.headers.items() if k.lower() not in skip_headers]
        return Response(
            status_code=r.status_code,
            content=r.content,
            headers=dict(response_headers),
        )
    except httpx.ConnectError as e:
        logger.warning("Portal proxy: connection failed to {}: {}", base, e)
        return JSONResponse(status_code=502, content={"detail": "Cannot reach Portal; is it running?"})
    except httpx.TimeoutException:
        logger.warning("Portal proxy: timeout to {}", url)
        return JSONResponse(status_code=504, content={"detail": "Portal request timed out"})
    except Exception as e:
        logger.exception("Portal proxy error: {}", e)
        return JSONResponse(status_code=503, content={"detail": str(e)})


def _rewrite_location_for_portal_ui(location: str, portal_base: str, portal_ui_prefix: str) -> str:
    """Rewrite Location header so client sees /portal-ui/... instead of Portal's origin."""
    if not location:
        return location
    location = location.strip()
    try:
        if location.startswith(portal_base):
            path = location[len(portal_base):].lstrip("/")
            return f"{portal_ui_prefix.rstrip('/')}/{path}" if path else portal_ui_prefix.rstrip("/") or "/portal-ui"
        if location.startswith("/") and not location.startswith("/portal-ui"):
            return f"{portal_ui_prefix.rstrip('/')}{location}"
    except Exception:
        pass
    return location


async def _stream_portal_ui(request: Request, path: str) -> Response:
    """Reverse-proxy GET to Portal and stream response. Rewrite Location and Set-Cookie path for /portal-ui. Phase 5: require portal admin auth when portal_url is set."""
    base = _get_portal_url().rstrip("/")
    if not base:
        return JSONResponse(status_code=502, content={"detail": "Portal URL not configured"})
    if get_portal_admin_from_request(request) is None:
        return JSONResponse(status_code=401, content={"detail": "Portal admin auth required (Bearer token, Basic, or ?token=)"})
    secret = _get_portal_secret()
    upstream_path = path.strip("/") if path else ""
    query = str(request.url.query)
    url = f"{base}/{upstream_path}" + ("?" + query if query else "")
    headers = {"Accept": request.headers.get("accept", "*/*")}
    if secret:
        headers["X-Portal-Secret"] = secret
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, headers=headers)
            # Read full body inside context so connection is released; avoids streaming after client close.
            content = r.content
    except httpx.ConnectError as e:
        logger.warning("Portal UI proxy: connection failed: {}", e)
        return JSONResponse(status_code=502, content={"detail": "Cannot reach Portal; is it running?"})
    except httpx.TimeoutException:
        logger.warning("Portal UI proxy: timeout to {}", url)
        return JSONResponse(status_code=504, content={"detail": "Portal request timed out"})
    except Exception as e:
        logger.exception("Portal UI proxy error: {}", e)
        return JSONResponse(status_code=503, content={"detail": str(e)})

    skip_headers = frozenset({"connection", "transfer-encoding", "keep-alive"})
    out_headers = {}
    for k, v in r.headers.items():
        k_lower = k.lower()
        if k_lower in skip_headers:
            continue
        if k_lower == "location":
            v = _rewrite_location_for_portal_ui(v, base, "/portal-ui")
        if k_lower == "set-cookie":
            # Rewrite path in Set-Cookie so cookie is sent for /portal-ui
            if "path=" in v.lower():
                v = v.replace("path=/", "path=/portal-ui/").replace("path=/portal-ui/", "path=/portal-ui")
            else:
                v = v.rstrip(";") + "; Path=/portal-ui"
        out_headers[k] = v

    return Response(
        status_code=r.status_code,
        content=content,
        headers=out_headers,
        media_type=r.headers.get("content-type"),
    )


def get_portal_ui_handler():
    """Handler for GET /portal-ui (exact)."""
    async def handler(request: Request):
        return await _stream_portal_ui(request, "")
    return handler


def get_portal_ui_path_handler():
    """Handler for GET /portal-ui/{path:path}."""
    async def handler(request: Request, path: str):
        return await _stream_portal_ui(request, path)
    return handler
