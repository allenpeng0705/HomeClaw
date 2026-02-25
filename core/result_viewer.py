"""
File serving and HTML generation for Core.

- Core serves files from the sandbox at GET /files/out?path=...&token=...
  Links use core_public_url (top-level in config). Tokens are signed with auth_api_key.
- build_file_view_link(): single place to build file view URLs; use it everywhere for stable, consistent links (token-first, 7-day expiry). Token format is base64(payload)+hex(sig) with no separator so links stay valid when copied or linkified.
- generate_result_html(): build HTML from title/content for save_result_page tool (saves to user output folder).
- When a path is a directory, /files/out returns an HTML listing with links to files/subdirs.

See docs_design/FileSandboxDesign.md. auth_api_key and core_public_url are in config/core.yml (top level).
"""

import base64
import hmac
import hashlib
import re
import time
from typing import Optional, Tuple
from urllib.parse import quote, unquote

from loguru import logger

# Default expiry for file view links (7 days) so shared links stay valid for a stable UX.
DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC = 7 * 86400

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


def create_file_access_token(scope: str, path: str, expiry_sec: int = DEFAULT_FILE_VIEW_LINK_EXPIRY_SEC) -> Optional[str]:
    """
    Create a signed token for GET /files/out (open link in browser without API key).
    scope = workspace subdir (user id, 'companion', or 'default'). path = relative path under that (e.g. output/report_xxx.html).
    Returns None if auth_api_key is not set in config or path/scope are invalid. Never raises.
    """
    try:
        if not scope or not path or ".." in path or path.startswith("/") or "/" in scope or ".." in scope:
            return None
        secret = _get_file_token_secret()
        if not secret:
            return None
        logger.debug("files/out token created (secret_len={})", len(secret))
        expiry = int(time.time()) + max(1, min(expiry_sec, 7 * 86400))
        payload = f"{scope}\0{path}\0{expiry}"
        full_sig = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        sig = full_sig[:32]  # shorter link, less likely to be truncated; 16 hex bytes = 64 bits
        b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        # No separator (e.g. no '.') so the token is stable when copied or linkified; verify finds the split by trying last 32 chars as hex sig.
        return f"{b64}{sig}"
    except Exception as e:
        logger.debug("create_file_access_token failed: {}", e)
        return None


def verify_file_access_token(token: str) -> Optional[Tuple[str, str]]:
    """Verify token and return (scope, path) if valid and not expired. Otherwise None. Never raises."""
    try:
        raw = (token or "").strip()
        token_len = len(raw)
        if not raw:
            logger.debug("files/out token: empty token_len=0")
            return None
        token = unquote(raw) if "%" in raw else raw
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
        if len(token) < 33:
            logger.debug("files/out token: too short token_len={}", token_len)
            return None
        sig = token[-32:]
        if len(sig) != 32 or not all(c in "0123456789abcdef" for c in sig):
            logger.debug("files/out token: invalid signature suffix token_len={}", token_len)
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


def build_file_view_link(scope: str, path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Build a stable file view URL for GET /files/out. Single place for link generation so format and config checks are consistent.
    Returns (url, None) on success, or (None, error_message) when link cannot be generated (caller should show error_message to user).
    Uses token-first query order and 7-day expiry for stable UX. Never raises.
    """
    try:
        if not scope or not path or ".." in path or path.startswith("/"):
            return (None, "Invalid scope or path for file link.")
        base_url = get_result_link_base_url()
        if not base_url:
            return (None, "Set core_public_url in config (e.g. your tunnel or public URL) for shareable file links.")
        token = create_file_access_token(scope, path)
        if not token:
            return (None, "Set auth_api_key in config for shareable file links.")
        url = f"{base_url}/files/out?token={token}&path={quote(path)}"
        return (url, None)
    except Exception as e:
        logger.debug("build_file_view_link failed: {}", e)
        return (None, "Could not generate file link; check core_public_url and auth_api_key in config.")


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
