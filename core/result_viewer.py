"""
File serving and HTML generation for Core.

- Core serves files from the sandbox at GET /files/out?path=...&token=...
  Links use core_public_url (top-level in config). Tokens are signed with auth_api_key.
- When auth_api_key is unset, file links use unsigned dev mode: GET /files/out?scope=...&path=...&dev_unsigned=1
  (or static style with ?dev_unsigned=1). Insecure — anyone who can reach Core can request sandbox paths by URL.
- build_file_view_link(): single place to build file view URLs; use it everywhere for stable, consistent links (token-first, 7-day expiry). Token format is base64(payload)+hex(sig) with no separator so links stay valid when copied or linkified. Query values use percent-encoding (quote); final URLs pass normalize_public_url_for_clients() so no literal whitespace remains (clickable in markdown/chat).
- generate_result_html(): build HTML from title/content for save_result_page tool (saves to user output folder).
- When a path is a directory, /files/out returns an HTML listing with links to files/subdirs.

See docs_design/FileSandboxDesign.md. auth_api_key and core_public_url are in config/core.yml (top level).
"""

import base64
import hmac
import hashlib
import html
import os
import re
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple
from urllib.parse import quote, unquote, urlparse

from loguru import logger


def normalize_public_url_for_clients(url: str) -> str:
    """
    Remove every whitespace character (space, tab, newline, NBSP) so the string is one URL token:
    markdown autolinks, chat UIs, and SMS linkifiers do not break mid-URL. Paths and query values built
    with ``quote()`` use %20 for spaces; this only strips *accidental* literal spaces (e.g. config/proxy typos).
    Never raises.
    """
    try:
        if not url or not isinstance(url, str):
            return ""
        return "".join(url.split())
    except Exception:
        return ""


def _normalize_link_base_url(raw: Optional[str]) -> str:
    """Strip accidental whitespace in public base URLs (core_public_url, X-Forwarded-Host). Never raises."""
    return normalize_public_url_for_clients((raw or "").strip()).rstrip("/")


# Default expiry for file view links (7 days). Override via config: file_view_link_expiry_sec (seconds or e.g. "7d").
DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC = 7 * 86400
MAX_FILE_VIEW_LINK_EXPIRY_SEC = 365 * 86400  # cap 1 year

DEFAULT_MAX_RESULT_HTML_BYTES = 500 * 1024  # 500 KB for generated report HTML

# Normalize auth_api_key the same way for both create and verify (avoid mismatch from whitespace/control chars)
def _normalize_file_token_secret_key(raw: Optional[str]) -> str:
    try:
        s = str(raw or "").strip()
        return re.sub(r"[\x00-\x1f\x7f]", "", s) or ""
    except Exception:
        return ""


def _get_file_token_secret() -> Optional[bytes]:
    """Secret for signing file access tokens. Uses auth_api_key from config (normalized)."""
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        key = _normalize_file_token_secret_key(getattr(meta, "auth_api_key", None))
        if key:
            return key.encode("utf-8")
    except Exception:
        pass
    return None


def validate_file_link_scope_path(scope: str, path: str) -> bool:
    """True if scope/path are safe for sandbox file links. Never raises."""
    try:
        s = (scope or "").strip()
        p = (path or "").replace("\\", "/").strip()
        if not s or not p:
            return False
        if ".." in p or p.startswith("/"):
            return False
        if "/" in s or ".." in s:
            return False
        return True
    except Exception:
        return False


def file_unsigned_dev_mode_active() -> bool:
    """True when auth_api_key is unset — Core accepts dev_unsigned file URLs (insecure)."""
    return _get_file_token_secret() is None


_warned_dev_unsigned_file_links = False


def _maybe_warn_dev_unsigned_file_links() -> None:
    global _warned_dev_unsigned_file_links
    if _warned_dev_unsigned_file_links:
        return
    _warned_dev_unsigned_file_links = True
    logger.warning(
        "File links use unsigned dev mode because auth_api_key is not set. "
        "Anyone who can reach Core may request sandbox files by URL. Set auth_api_key for signed /files/... links."
    )


def create_file_access_token(scope: str, path: str, expiry_sec: int = DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC) -> Optional[str]:
    """
    Create a signed token for GET /files/out (open link in browser without API key).
    scope = workspace subdir (user id, 'companion', or 'default'). path = relative path under that (e.g. output/report_xxx.html).
    Returns None if auth_api_key is not set in config or path/scope are invalid. Never raises.
    """
    try:
        scope_s = (scope or "").strip()
        path_norm = (path or "").replace("\\", "/").strip()
        if not validate_file_link_scope_path(scope_s, path_norm):
            return None
        secret = _get_file_token_secret()
        if not secret:
            return None
        logger.debug("files/out token created (secret_len={})", len(secret))
        expiry = int(time.time()) + max(1, min(int(expiry_sec) if isinstance(expiry_sec, (int, float)) else DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC, MAX_FILE_VIEW_LINK_EXPIRY_SEC))
        payload = f"{scope_s}\0{path_norm}\0{expiry}"
        full_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        sig = full_sig[:32]  # shorter link, less likely to be truncated; 16 hex bytes = 64 bits
        b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        # No separator (e.g. no '.') so the token is stable when copied or linkified; verify finds the split by trying last 32 chars as hex sig.
        return f"{b64}{sig}"
    except Exception as e:
        logger.debug("create_file_access_token failed: {}", e)
        return None


# Token alphabet: base64url (A-Za-z0-9_-) + 32 hex for sig. Strip any other char (e.g. spurious char from LLM/channel).
_TOKEN_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


# Dev-bridge project file browser links (Companion → Core GET /files/bridge-project).
DEFAULT_BRIDGE_PROJECT_LINK_EXPIRY_SEC = 15 * 60  # 15 minutes (short-lived; streams from bridge via Core)


def validate_bridge_project_rel_path(backend: str, rel_path: str) -> bool:
    """True if backend and rel_path are safe for bridge project browser proxy. Never raises."""
    try:
        b = (backend or "").strip().lower()
        if b not in ("cursor", "claude"):
            return False
        p = (rel_path or "").replace("\\", "/").strip()
        if not p or len(p) > 4096:
            return False
        if ".." in p.split("/") or p.startswith("/"):
            return False
        return True
    except Exception:
        return False


def create_bridge_project_file_token(
    backend: str,
    rel_path: str,
    expiry_sec: int = DEFAULT_BRIDGE_PROJECT_LINK_EXPIRY_SEC,
    user_id: str = "",
    friend_id: str = "",
) -> Optional[str]:
    """
    Signed token for GET /files/bridge-project (Cursor/Claude project file on dev bridge, proxied by Core).
    Payload v1 (legacy): bridgep\\0backend\\0rel_path\\0expiry
    Payload v2: bridgep\\0backend\\0rel_path\\0user_id\\0friend_id\\0expiry — scopes bridge /project/raw to the right chat.
    Requires auth_api_key.
    """
    try:
        b = (backend or "").strip().lower()
        p = (rel_path or "").replace("\\", "/").strip()
        if not validate_bridge_project_rel_path(b, p):
            return None
        secret = _get_file_token_secret()
        if not secret:
            return None
        expiry = int(time.time()) + max(60, min(int(expiry_sec) if isinstance(expiry_sec, (int, float)) else DEFAULT_BRIDGE_PROJECT_LINK_EXPIRY_SEC, 86400))
        uid = (user_id or "").strip().replace("\0", "")
        fid = (friend_id or "").strip().replace("\0", "")
        payload = f"bridgep\0{b}\0{p}\0{uid}\0{fid}\0{expiry}"
        full_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        sig = full_sig[:32]
        b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        return f"{b64}{sig}"
    except Exception as e:
        logger.debug("create_bridge_project_file_token failed: {}", e)
        return None


def verify_bridge_project_file_token(token: str) -> Optional[Tuple[str, str, str, str]]:
    """Verify bridge project token; return (backend, rel_path, user_id, friend_id) or None. Never raises."""
    try:
        raw = (token or "").strip()
        if not raw or len(raw) > 800:
            return None
        while "%" in raw:
            prev, raw = raw, unquote(raw)
            if prev == raw:
                break
        token = "".join(c for c in raw if c in _TOKEN_ALPHABET)
        if len(token) < 33:
            return None
        secret = _get_file_token_secret()
        if not secret:
            return None
        sig = token[-32:]
        b64 = token[:-32]
        pad = 4 - (len(b64) % 4)
        if pad != 4:
            b64 += "=" * pad
        try:
            payload = base64.urlsafe_b64decode(b64).decode("utf-8")
        except Exception:
            return None
        expected_full = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        expected_sig = expected_full[:32]
        if not (hmac.compare_digest(expected_sig, sig) or hmac.compare_digest(expected_full, sig)):
            return None
        parts = payload.split("\0")
        if parts[0] != "bridgep":
            return None
        if len(parts) == 4:
            _, backend, rel_path, expiry_str = parts
            user_id, friend_id = "", ""
        elif len(parts) == 6:
            _, backend, rel_path, user_id, friend_id, expiry_str = parts
        else:
            return None
        try:
            if time.time() > int(expiry_str):
                return None
        except ValueError:
            return None
        if not validate_bridge_project_rel_path(backend, rel_path):
            return None
        return (backend.strip().lower(), rel_path, (user_id or "").strip(), (friend_id or "").strip())
    except Exception as e:
        logger.debug("verify_bridge_project_file_token failed: {}", e)
        return None


def build_bridge_project_browser_url(
    backend: str,
    rel_path: str,
    preferred_base_url: Optional[str] = None,
    user_id: str = "",
    friend_id: str = "",
) -> Tuple[Optional[str], Optional[str]]:
    """Build GET /files/bridge-project URL (token or dev_unsigned). Returns (url, error). Never raises."""
    try:
        b = (backend or "").strip().lower()
        p = (rel_path or "").replace("\\", "/").strip()
        if not validate_bridge_project_rel_path(b, p):
            return (None, "Invalid backend or path for bridge file link.")
        base_url = resolve_file_link_base_url(preferred_base_url)
        if not base_url:
            return (
                None,
                "Set core_public_url in config to the URL clients use to reach Core (e.g. tunnel or LAN IP).",
            )
        uid = (user_id or "").strip()
        fid = (friend_id or "").strip()
        tok = create_bridge_project_file_token(b, p, user_id=uid, friend_id=fid)
        if tok:
            token_safe = "".join(c for c in tok if c in _TOKEN_ALPHABET)
            if len(token_safe) < 33:
                return (None, "Could not generate bridge file link token.")
            u = f"{base_url.rstrip('/')}/files/bridge-project?token={quote(token_safe, safe='')}"
            return (normalize_public_url_for_clients(u), None)
        if file_unsigned_dev_mode_active():
            _maybe_warn_dev_unsigned_file_links()
            q = f"backend={quote(b, safe='')}&path={quote(p, safe='/')}&dev_unsigned=1"
            if uid:
                q += f"&user_id={quote(uid, safe='')}"
            if fid:
                q += f"&friend_id={quote(fid, safe='')}"
            u = f"{base_url.rstrip('/')}/files/bridge-project?{q}"
            return (normalize_public_url_for_clients(u), None)
        return (None, "Set auth_api_key in config for shareable bridge file links (or use dev_unsigned with no auth_api_key).")
    except Exception as e:
        logger.debug("build_bridge_project_browser_url failed: {}", e)
        return (None, "Could not build bridge file view URL.")


def verify_file_access_token(token: str) -> Optional[Tuple[str, str]]:
    """Verify token and return (scope, path) if valid and not expired. Otherwise None. Never raises."""
    try:
        raw = (token or "").strip()
        token_len = len(raw)
        if not raw:
            logger.debug("files/out token: empty token_len=0")
            return None
        if token_len > 500:
            logger.debug("files/out token: too long, likely corrupted by client/LLM token_len={}", token_len)
            return None
        # Decode percent-encoding (e.g. %25 -> %; repeat so double-encoded tokens decode fully)
        while "%" in raw:
            prev, raw = raw, unquote(raw)
            if prev == raw:
                break
        token = raw
        # Remove any character not in token alphabet (Core generates only b64+hex; spurious chars can be inserted by LLM/channel).
        token = "".join(c for c in token if c in _TOKEN_ALPHABET)
        if len(token) < 33:
            logger.debug("files/out token: too short after sanitize token_len={}", len(token))
            return None
        secret = _get_file_token_secret()
        if not secret:
            logger.debug("files/out token: auth_api_key not set on this server token_len={}", token_len)
            return None

        def _verify_b64_sig(b64: str, sig: str) -> Optional[Tuple[str, str]]:
            try:
                pad = 4 - (len(b64) % 4)
                if pad != 4:
                    b64 += "=" * pad
                payload = base64.urlsafe_b64decode(b64).decode("utf-8")
            except Exception:
                return None
            expected_full = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
            expected_sig = expected_full[:32]
            if not (hmac.compare_digest(expected_sig, sig) or hmac.compare_digest(expected_full, sig)):
                return None
            chunks = payload.split("\0", 2)
            if len(chunks) != 3:
                return None
            scope, path, expiry_str = chunks[0], chunks[1], chunks[2]
            try:
                expiry = int(expiry_str)
                if time.time() > expiry:
                    return None
            except ValueError:
                return None
            if not scope or not path or ".." in path or path.startswith("/"):
                return None
            if "/" in scope or ".." in scope:
                return None
            return (scope, path)

        # Token format: b64 + sig (no separator). Last 32 chars = hex signature, rest = base64 payload.
        sig = token[-32:].lower()  # normalize so uppercase hex (e.g. from URL) is accepted
        if len(sig) != 32 or not all(c in "0123456789abcdef" for c in sig):
            logger.debug("files/out token: invalid signature suffix token_len={}", len(token))
            return None
        b64 = token[:-32]
        result = _verify_b64_sig(b64, sig)
        if result is not None:
            return result
        logger.debug("files/out token: signature mismatch or invalid token_len={}", token_len)
        return None
    except Exception as e:
        logger.debug("verify_file_access_token failed: {}", e)
        return None


def infer_public_base_url_from_http_request(request: Any) -> Optional[str]:
    """
    Derive http(s) base URL from a Starlette/FastAPI Request (Host, X-Forwarded-Host, X-Forwarded-Proto).
    Use for file view links so they match how the client reached Core (tunnel, reverse proxy, LAN).
    Never raises.
    """
    try:
        if request is None:
            return None
        hdr = getattr(request, "headers", None)
        if hdr is not None:
            fwd_host = (hdr.get("x-forwarded-host") or hdr.get("X-Forwarded-Host") or "").strip()
            fwd_proto = (hdr.get("x-forwarded-proto") or hdr.get("X-Forwarded-Proto") or "").strip().lower()
        if fwd_host:
            host = fwd_host.split(",")[0].strip()
            scheme = fwd_proto if fwd_proto in ("http", "https") else str(getattr(request.url, "scheme", None) or "http")
            if host:
                return _normalize_link_base_url(f"{scheme}://{host}")
        bu = getattr(request, "base_url", None)
        if bu is not None and str(bu).strip():
            return _normalize_link_base_url(str(bu))
    except Exception as e:
        logger.debug("infer_public_base_url_from_http_request failed: {}", e)
    return None


def infer_public_base_url_from_websocket(websocket: Any) -> Optional[str]:
    """Derive http(s) base from a WebSocket (wss -> https). Same goal as HTTP inbound. Never raises."""
    try:
        if websocket is None:
            return None
        hdr = getattr(websocket, "headers", None)
        if hdr is not None:
            fwd_host = (hdr.get("x-forwarded-host") or hdr.get("X-Forwarded-Host") or "").strip()
            fwd_proto = (hdr.get("x-forwarded-proto") or hdr.get("X-Forwarded-Proto") or "").strip().lower()
            if fwd_host:
                host = fwd_host.split(",")[0].strip()
                scheme = fwd_proto if fwd_proto in ("http", "https") else "https"
                if host:
                    return _normalize_link_base_url(f"{scheme}://{host}")
        u = getattr(websocket, "url", None)
        if u is None:
            return None
        sch = str(getattr(u, "scheme", "") or "").lower()
        scheme = "https" if sch in ("wss", "https") else "http"
        host = getattr(u, "hostname", None) or ""
        if not host:
            return None
        port = getattr(u, "port", None)
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{host}:{port}"
        else:
            netloc = host
        return _normalize_link_base_url(f"{scheme}://{netloc}")
    except Exception as e:
        logger.debug("infer_public_base_url_from_websocket failed: {}", e)
    return None


def preferred_file_link_base_from_context(context: Any) -> Optional[str]:
    """Read public_request_base_url from PromptRequest.request_metadata (set by inbound). Never raises."""
    try:
        req = getattr(context, "request", None)
        if req is None:
            return None
        md = getattr(req, "request_metadata", None) or {}
        if isinstance(md, dict):
            u = _normalize_link_base_url(md.get("public_request_base_url") or "")
            return u or None
    except Exception:
        pass
    return None


def resolve_file_link_base_url(preferred_base_url: Optional[str] = None) -> str:
    """
    Effective base URL for /files/out links.
    Order: (1) preferred (from inbound HTTP/WS), (2) core_public_url or Pinggy runtime, (3) if unsigned dev (no auth_api_key), localhost Core URL from config.
    Returns "" if nothing can be determined (signed tokens need auth_api_key + a reachable base).
    Never raises.
    """
    u = _normalize_link_base_url(preferred_base_url)
    if u:
        return u
    u2 = _normalize_link_base_url(get_result_link_base_url())
    if u2:
        return u2
    if file_unsigned_dev_mode_active():
        return _normalize_link_base_url(get_core_public_url() or "")
    return ""


def build_file_view_link(
    scope: str, path: str, preferred_base_url: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Build a file view URL. Single place for link generation so format and config checks are consistent.
    Returns (url, None) on success, or (None, error_message) when link cannot be generated (caller should show error_message to user).
    - file_link_style "token" (default): signed GET /files/out?token=... (7-day expiry). Requires auth_api_key.
    - When auth_api_key is unset: unsigned dev GET /files/out?scope=...&path=...&dev_unsigned=1 (uses core_public_url or localhost).
    - file_link_style "static": URL = base_url/ file_static_prefix /scope/path?token=... (e.g. /files/AllenPeng/images/ID1.jpg?token=...). The token is required so the link only accesses that user's sandbox (scope+path); Core serves the file after verifying the token.
    Never raises.
    """
    try:
        scope_s = (scope or "").strip()
        path_norm = (path or "").replace("\\", "/").strip()
        if not validate_file_link_scope_path(scope_s, path_norm):
            return (None, "Invalid scope or path for file link.")
        unsigned_dev = file_unsigned_dev_mode_active()
        base_url = resolve_file_link_base_url(preferred_base_url)
        if not base_url:
            return (
                None,
                "Set core_public_url in config to the URL clients use to reach Core (e.g. tunnel or LAN IP), "
                "or call Core via HTTP so the link can be derived from the request. "
                "With auth_api_key set, signed links require a stable public base.",
            )

        def _link_ok(u: str) -> Tuple[Optional[str], None]:
            """Strip all whitespace so the URL is one token for markdown/linkifiers; values are already percent-encoded."""
            return (normalize_public_url_for_clients(u), None)

        try:
            from base.util import Util
            meta = Util().get_core_metadata()
            link_style = (getattr(meta, "file_link_style", None) or "token").strip().lower()
            static_prefix = (getattr(meta, "file_static_prefix", None) or "files").strip().strip("/") or "files"
            expiry_sec = getattr(meta, "file_view_link_expiry_sec", None)
            if expiry_sec is None or not isinstance(expiry_sec, (int, float)):
                expiry_sec = DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC
            expiry_sec = max(1, min(int(expiry_sec), MAX_FILE_VIEW_LINK_EXPIRY_SEC))
        except Exception:
            link_style = "token"
            static_prefix = "files"
            expiry_sec = DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC
        if link_style == "static":
            # URL path = prefix/scope/path; always add token so the link only accesses this user's sandbox (scope+path).
            path_encoded = "/".join(quote(seg, safe="") for seg in path_norm.strip("/").split("/"))
            scope_safe = quote(scope_s, safe="")
            token = create_file_access_token(scope_s, path_norm, expiry_sec=expiry_sec)
            if token:
                token_safe = "".join(c for c in token if c in _TOKEN_ALPHABET)
                if len(token_safe) < 33:
                    return (None, "Could not generate file link (token invalid).")
                url = f"{base_url.rstrip('/')}/{static_prefix}/{scope_safe}/{path_encoded}?token={token_safe}"
                return _link_ok(url)
            if unsigned_dev:
                _maybe_warn_dev_unsigned_file_links()
                url = f"{base_url.rstrip('/')}/{static_prefix}/{scope_safe}/{path_encoded}?dev_unsigned=1"
                return _link_ok(url)
            return (None, "Set auth_api_key in config for shareable file links.")
        token = create_file_access_token(scope_s, path_norm, expiry_sec=expiry_sec)
        if token:
            token_safe = "".join(c for c in token if c in _TOKEN_ALPHABET)
            if len(token_safe) < 33:
                return (None, "Could not generate file link (token invalid).")
            # Keep "/" readable in query path (e.g. output/report.pdf); quote encodes spaces and special chars.
            url = f"{base_url.rstrip('/')}/files/out?token={quote(token_safe, safe='')}&path={quote(path_norm, safe='/')}"
            return _link_ok(url)
        if unsigned_dev:
            _maybe_warn_dev_unsigned_file_links()
            scope_q = quote(scope_s, safe="")
            path_q = quote(path_norm, safe="/")
            url = f"{base_url.rstrip('/')}/files/out?scope={scope_q}&path={path_q}&dev_unsigned=1"
            return _link_ok(url)
        return (None, "Set auth_api_key in config for shareable file links.")
    except Exception as e:
        logger.debug("build_file_view_link failed: {}", e)
        return (None, "Could not generate file link; check core_public_url and auth_api_key in config.")


def build_file_view_link_for_context(scope: str, path: str, context: Any) -> Tuple[Optional[str], Optional[str]]:
    """build_file_view_link with inbound-derived base URL when ToolContext comes from POST /inbound or /ws."""
    return build_file_view_link(scope, path, preferred_file_link_base_from_context(context))


def rewrite_vmprint_preview_html_assets(html: str, scope: str, path_arg: str) -> str:
    """
    VMPrint hybrid preview HTML uses href/src like ./styles.css. Browsers resolve those against the
    request URL path (/files/out), yielding /files/styles.css — wrong and 403 on /files/{scope}/{path}
    without a token. Rewrite ./... to the same view URLs as the preview file (output/styles.css, etc.).
    """
    try:
        s_html = html if isinstance(html, str) else ""
        if not s_html or "homeclaw-vmprint-ui-hint" not in s_html:
            return s_html
        from pathlib import PurePosixPath

        scope_s = (scope or "").strip()
        pnorm = (path_arg or "").replace("\\", "/").strip()
        if not scope_s or not pnorm:
            return s_html
        parent = PurePosixPath(pnorm).parent
        cache = {}

        def sibling_url(rel_after_dot_slash: str) -> str:
            rel_after_dot_slash = (rel_after_dot_slash or "").strip().lstrip("/")
            full_rel = str(parent / rel_after_dot_slash) if str(parent) != "." else rel_after_dot_slash
            if full_rel in cache:
                return cache[full_rel]
            url, _ = build_file_view_link(scope_s, full_rel)
            out = url if url else f"./{rel_after_dot_slash}"
            cache[full_rel] = out
            return out

        def esc_attr(u: str) -> str:
            return u.replace("&", "&amp;").replace("'", "&#39;")

        out = s_html
        for attr in ("href", "src"):
            pat1 = re.compile(re.escape(attr) + r"='\./([^']+)'")

            def repl1(m, a=attr):
                u = sibling_url(m.group(1))
                return f"{a}='{esc_attr(u)}'"

            out = pat1.sub(repl1, out)
            pat2 = re.compile(re.escape(attr) + r'="\./([^"]+)"')

            def repl2(m, a=attr):
                u = sibling_url(m.group(1))
                return f'{a}="{html.escape(u, quote=True)}"'

            out = pat2.sub(repl2, out)
        return out
    except Exception as e:
        logger.debug("rewrite_vmprint_preview_html_assets failed: {}", e)
        return html if isinstance(html, str) else ""


def file_absolute_path_to_view_url(path_str: str) -> Tuple[Optional[str], Optional[str]]:
    """
    If ``path_str`` is an absolute path to a file under ``homeclaw_root``, return a file view URL
    from ``build_file_view_link`` (same paths served by GET /files/out).

    Also accepts legacy paths under ``<project>/database/uploads/`` when they are the same inode as
    ``homeclaw_root/database/uploads/...`` (symlink / bind mount). Otherwise (None, reason).
    Never raises.
    """
    try:
        from pathlib import Path

        from base.util import Util

        p = Path((path_str or "").strip())
        if not p.is_absolute() or not p.is_file():
            return (None, "not an absolute file path")
        full = p.resolve()
        meta = Util().get_core_metadata()
        base_str = str(getattr(meta, "homeclaw_root", None) or "").strip()
        if not base_str:
            try:
                base_str = str(meta.get_homeclaw_root() or "").strip()
            except Exception:
                base_str = ""
        if not base_str:
            return (None, "homeclaw_root not configured")
        base = Path(base_str).expanduser().resolve()

        def _link(scope: str, inner: str) -> Tuple[Optional[str], Optional[str]]:
            url, err = build_file_view_link(scope, inner)
            if url and not err:
                return (url, None)
            return (None, err or "could not build file link")

        try:
            rel = full.relative_to(base)
        except ValueError:
            rel = None
        if rel is not None:
            rel_posix = rel.as_posix()
            parts = rel_posix.split("/", 1)
            if len(parts) < 2:
                return (None, "invalid sandbox layout")
            u, e = _link(parts[0], parts[1])
            if u:
                return (u, None)
            if e:
                return (None, e)

        # Legacy: upload used <project>/database/uploads while homeclaw_root is elsewhere — only if same file as sandbox.
        root = Path(Util().root_path()).expanduser().resolve()
        proj_upload = (root / "database" / "uploads").resolve()
        try:
            rel_u = full.relative_to(proj_upload)
        except ValueError:
            return (
                None,
                "path not under homeclaw_root (set homeclaw_root to your project dir, or re-upload: files now save under homeclaw_root/database/uploads)",
            )
        inner = f"uploads/{rel_u.as_posix().replace(chr(92), '/')}"
        cand = (base / "database" / "uploads" / rel_u).resolve()
        try:
            if cand.is_file():
                if os.path.samefile(full, cand):
                    return _link("database", inner)
        except Exception:
            pass
        return (
            None,
            "upload path is under the repo, not under homeclaw_root; re-send the attachment (Core now stores uploads in homeclaw_root/database/uploads) or align homeclaw_root with your project.",
        )
    except Exception as e:
        logger.debug("file_absolute_path_to_view_url failed: {}", e)
        return (None, "could not build file link")


def file_view_url_to_core_relative(url: str) -> str:
    """
    If ``url`` is http(s) to this Core's /files routes on a loopback host, return ``/files/...?...`` only
    so mobile/web clients can prefix their own reachable ``baseUrl`` (emulator, LAN).
    """
    try:
        u = urlparse((url or "").strip())
        if u.scheme not in ("http", "https") or not u.path:
            return url
        host = (u.hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return url
        if not (u.path.startswith("/files/") or u.path.startswith("/files/out")):
            return url
        return u.path + (("?" + u.query) if u.query else "")
    except Exception:
        return url


# When a tunnel (e.g. Pinggy) provides a URL at runtime, Core sets it here so file/report/folder links use it when core_public_url is not in config.
_runtime_public_url: Optional[str] = None


def set_runtime_public_url(url: Optional[str]) -> None:
    """Set the public URL when a tunnel (e.g. Pinggy) provides it at runtime. Used by Core when the tunnel is up."""
    global _runtime_public_url
    _runtime_public_url = (url or "").strip().rstrip("/") or None


def get_core_public_url() -> str:
    """
    Public URL that reaches Core. Used for file/report links and folder listing links.
    Returns, in order: (1) core_public_url from config if set, (2) runtime URL (e.g. from Pinggy), (3) http://127.0.0.1:<port> for local use.
    Link format: get_core_public_url() + "/files/out?token=" + create_file_access_token(...) + "&path=" + quote(path). Token is b64+hex sig with no separator.
    """
    base = get_result_link_base_url()
    if base:
        return base
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        port = int(getattr(meta, "port", 0) or 9000)
        host = (getattr(meta, "host", None) or "").strip() or "0.0.0.0"
        if host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        return f"http://{host}:{port}"
    except Exception:
        return "http://127.0.0.1:9000"


def build_image_view_links(
    image_paths: Optional[List[str]],
    scope: str,
) -> List[str]:
    """
    Build list of view URLs for image paths under homeclaw_root/scope/.
    Used when client does not accept inline images (reply_accepts text-only) and Core has a public URL.
    Returns []. Never raises.
    """
    if not image_paths or not get_result_link_base_url():
        return []
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        base = (getattr(meta, "homeclaw_root", None) or "").strip()
        if not base:
            return []
    except Exception:
        return []
    scope = (scope or "companion").strip() or "companion"
    try:
        sandbox = Path(base).resolve() / scope
    except (OSError, RuntimeError, ValueError):
        return []
    links: List[str] = []
    for image_path in image_paths:
        if not isinstance(image_path, str):
            continue
        try:
            full = Path(image_path).resolve()
            if not full.is_file():
                continue
            rel = full.relative_to(sandbox)
            rel_str = str(rel).replace("\\", "/")
            url, _ = build_file_view_link(scope, rel_str)
            if url:
                links.append(url)
        except (ValueError, OSError, RuntimeError):
            continue
    return links


def get_result_link_base_url() -> str:
    """
    Base URL to use when generating result/view links to send to the user (save_result_page, file_write output/, get_file_view_link).
    Uses only core_public_url from config or runtime tunnel URL — never localhost.
    Returns empty string if neither is set or on any error (caller should then ask user to set core_public_url and auth_api_key).
    Never raises.
    """
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        if meta is None:
            return ""
        url = str(getattr(meta, "core_public_url", None) or "").strip()
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    try:
        if _runtime_public_url:
            return str(_runtime_public_url).strip().rstrip("/") or ""
    except Exception:
        pass
    return ""


def generate_result_html(title: str, content: str, format: str = "html", max_bytes: Optional[int] = None) -> str:
    """
    Generate HTML document from title and content (for save_result_page tool or any HTML output).
    format: "html" or "markdown". If max_bytes not set, uses tools.save_result_page_max_file_size_kb from config or 500 KB.
    """
    if max_bytes is None:
        try:
            from base.util import Util
            tools = getattr(Util().get_core_metadata(), "tools", None) or {}
            max_kb = int(tools.get("save_result_page_max_file_size_kb") or 500)
            max_bytes = max_kb * 1024
        except Exception:
            max_bytes = DEFAULT_MAX_RESULT_HTML_BYTES
    if len(content.encode("utf-8")) > max_bytes:
        content = content[: max_bytes // 2] + "\n\n… [content truncated due to size limit]"
    content_stripped = content.strip().lower()
    is_full_html_doc = (
        content_stripped.startswith("<!doctype") or content_stripped.startswith("<html")
    )
    if is_full_html_doc:
        return content
    use_html = (format or "").lower() == "html"
    body_block = content if use_html else _markdown_to_html(content)
    # Escape braces so format() does not interpret {/} in body as placeholders
    body_safe = (body_block or "").replace("{", "{{").replace("}", "}}")
    return _HTML_TEMPLATE.format(title=_escape_html(title or ""), body=body_safe)


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _markdown_to_html(content: str) -> str:
    """Convert markdown to HTML when markdown is available; else show escaped in pre."""
    try:
        import markdown
        return markdown.markdown(content, extensions=["extra", "nl2br"])
    except ImportError:
        return f"<pre>{_escape_html(content)}</pre>"


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ --page-bg: #f8f9fa; --card-bg: #fff; --text: #1a1a1a; --muted: #5c5c5c; --border: #e0e0e0; --accent: #2563eb; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 1.5rem; line-height: 1.6; color: var(--text); background: var(--page-bg); }}
    .container {{ max-width: 52rem; margin: 0 auto; background: var(--card-bg); padding: 2rem; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    .page-header {{ border-bottom: 2px solid var(--accent); padding-bottom: 0.75rem; margin-bottom: 1.5rem; }}
    .page-header h1 {{ margin: 0; font-size: 1.5rem; font-weight: 600; color: var(--text); }}
    .page-body {{ }}
    .page-body h1 {{ font-size: 1.35rem; margin: 1.25rem 0 0.5rem; font-weight: 600; }}
    .page-body h2 {{ font-size: 1.2rem; margin: 1rem 0 0.4rem; font-weight: 600; color: var(--muted); }}
    .page-body p {{ margin: 0.5rem 0 1rem; }}
    .page-body ul {{ margin: 0.5rem 0 1rem; padding-left: 1.5rem; }}
    .page-body table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.95rem; }}
    .page-body th, .page-body td {{ border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; }}
    .page-body th {{ background: var(--page-bg); font-weight: 600; }}
    .page-body pre, .page-body code {{ font-family: ui-monospace, monospace; font-size: 0.9em; }}
    .page-body pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0.75rem 0; padding: 1rem; background: var(--page-bg); border-radius: 6px; border: 1px solid var(--border); }}
    .page-footer {{ margin-top: 2rem; padding-top: 0.75rem; border-top: 1px solid var(--border); font-size: 0.85rem; color: var(--muted); }}
  </style>
</head>
<body>
  <div class="container">
    <header class="page-header"><h1>{title}</h1></header>
    <main class="page-body">{body}</main>
    <footer class="page-footer">Generated by HomeClaw</footer>
  </div>
</body>
</html>
"""
