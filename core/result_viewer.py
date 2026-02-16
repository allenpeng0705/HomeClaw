"""
Complex result viewer: save HTML result pages, serve them under /result, and build shareable links.

- Runs a separate HTTP server for report pages (port in result_viewer.port in core.yml).
  Core uses its own port (e.g. 9000); the report server uses a different port (e.g. 9001).
  Starts when Core starts, stops when Core stops.
- Links only when base_url is set in config. We append /result/<id>.html to base_url.
  How the user exposes the local server (e.g. Cloudflare tunnel, ngrok) is up to them; we do not
  fetch or use the public IP. If base_url is not set, no link is produced — the model should send
  the full response to the user in chat.
- Retention: files older than retention_days are removed (e.g. on save or startup).
See docs/ComplexResultViewerDesign.md.
"""

import asyncio
import os
import threading
import uuid
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger

# Server and thread for the report HTTP server; set by start_report_server(), cleared by stop_report_server()
_report_server = None
_report_thread = None


def get_config() -> dict:
    """Return result_viewer config from core_metadata (read-only)."""
    try:
        from base.util import Util
        meta = Util().get_core_metadata()
        return getattr(meta, "result_viewer", None) or {}
    except Exception:
        return {}


def get_result_pages_dir() -> Path:
    """Return the directory where result HTML files are stored. Creates it if missing."""
    cfg = get_config()
    root = _root_path()
    raw = (cfg.get("dir") or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = Path(root) / path
    else:
        path = Path(root) / "database" / "result_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _root_path() -> str:
    try:
        from base.util import Util
        return Util().root_path()
    except Exception:
        return os.getcwd()


def get_base_url() -> Optional[str]:
    """
    Return base URL for result links. Only from config result_viewer.base_url (e.g. Cloudflare tunnel URL).
    We do not fetch or use the public IP. Link = base_url + /result/<id>.html.
    Returns None if base_url is not set — then no link is produced and the model should send the full response in chat.
    """
    cfg = get_config()
    base = (cfg.get("base_url") or "").strip()
    if not base:
        return None
    return base.rstrip("/")


def cleanup_old_results() -> None:
    """Remove result page files older than retention_days. No-op if retention_days is 0."""
    cfg = get_config()
    days = int(cfg.get("retention_days") or 7)
    if days <= 0:
        return
    try:
        import time
        from pathlib import Path
        dir_path = get_result_pages_dir()
        cutoff = time.time() - (days * 24 * 3600)
        removed = 0
        for f in dir_path.iterdir():
            if f.is_file() and f.suffix.lower() == ".html":
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        removed += 1
                except OSError:
                    pass
        if removed:
            logger.debug("Result viewer: removed %d old result page(s) (retention_days=%d)", removed, days)
    except Exception as e:
        logger.warning("Result viewer cleanup failed: %s", e)


def save_result_page(title: str, content: str, format: str = "html") -> Tuple[str, Optional[str]]:
    """
    Generate HTML from title and content, save to result_pages dir, run retention cleanup,
    and build link if base URL is available.

    format: "html" (content is HTML) or "markdown" (we wrap in a minimal page; no full markdown render).
    Returns (file_id, link or None). link is None when base_url cannot be obtained (e.g. public IP failed).
    """
    cfg = get_config()
    if not cfg.get("enabled", False):
        return "", None

    dir_path = get_result_pages_dir()
    file_id = uuid.uuid4().hex[:16]
    filename = f"{file_id}.html"

    max_kb = int(cfg.get("max_file_size_kb") or 500)
    max_bytes = max_kb * 1024
    if len(content.encode("utf-8")) > max_bytes:
        content = content[: max_bytes // 2] + "\n\n… [content truncated due to size limit]"

    # If content is clearly a full HTML document (e.g. model sent full page), save as-is so it
    # renders correctly. Otherwise we'd double-wrap it in our template and get invalid/messy output.
    content_stripped = content.strip().lower()
    is_full_html_doc = (
        content_stripped.startswith("<!doctype") or content_stripped.startswith("<html")
    )

    if is_full_html_doc:
        html = content
    else:
        use_html = (format or "").lower() == "html"
        if use_html:
            body_block = content
        else:
            body_block = _markdown_to_html(content)
        html = _HTML_TEMPLATE.format(title=_escape_html(title), body=body_block)

    file_path = dir_path / filename
    try:
        file_path.write_text(html, encoding="utf-8")
    except OSError as e:
        logger.warning("Result viewer: failed to write %s: %s", file_path, e)
        return "", None

    cleanup_old_results()

    base = get_base_url()
    if base:
        link = f"{base}/result/{filename}"
        return file_id, link
    return file_id, None


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _markdown_to_html(content: str) -> str:
    """Convert markdown to HTML when the markdown library is available; otherwise show escaped in a styled pre."""
    try:
        import markdown
        return markdown.markdown(content, extensions=["extra", "nl2br"])
    except ImportError:
        body_escaped = _escape_html(content)
        return f"<pre>{body_escaped}</pre>"


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
    .page-body h3 {{ font-size: 1.05rem; margin: 0.85rem 0 0.35rem; font-weight: 600; }}
    .page-body p {{ margin: 0.5rem 0 1rem; }}
    .page-body ul, .page-body ol {{ margin: 0.5rem 0 1rem; padding-left: 1.5rem; }}
    .page-body li {{ margin: 0.25rem 0; }}
    .page-body table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.95rem; }}
    .page-body th, .page-body td {{ border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; }}
    .page-body th {{ background: var(--page-bg); font-weight: 600; }}
    .page-body tr:nth-child(even) {{ background: #fafafa; }}
    .page-body pre, .page-body code {{ font-family: ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, monospace; font-size: 0.9em; }}
    .page-body pre {{ white-space: pre-wrap; word-wrap: break-word; margin: 0.75rem 0; padding: 1rem; background: var(--page-bg); border-radius: 6px; border: 1px solid var(--border); overflow-x: auto; }}
    .page-body code {{ padding: 0.15em 0.4em; background: var(--page-bg); border-radius: 4px; }}
    .page-body blockquote {{ margin: 1rem 0; padding: 0.5rem 0 0.5rem 1rem; border-left: 4px solid var(--accent); color: var(--muted); }}
    .page-footer {{ margin-top: 2rem; padding-top: 0.75rem; border-top: 1px solid var(--border); font-size: 0.85rem; color: var(--muted); }}
  </style>
</head>
<body>
  <div class="container">
    <header class="page-header"><h1>{title}</h1></header>
    <main class="page-body">{body}</main>
    <footer class="page-footer">Generated by HomeClaw · Result report</footer>
  </div>
</body>
</html>
"""


def start_report_server() -> bool:
    """
    Start the report web server (separate port from Core). Serves result_pages at /result.
    Call when Core starts. Runs in a background thread; stop with stop_report_server() when Core stops.
    Returns True if started, False if disabled or error.
    """
    global _report_server, _report_thread
    cfg = get_config()
    if not cfg.get("enabled", False):
        return False
    if _report_server is not None:
        return True
    try:
        from fastapi import FastAPI
        from fastapi.staticfiles import StaticFiles
        import uvicorn
        dir_path = get_result_pages_dir()
        cleanup_old_results()
        app = FastAPI()
        app.mount("/result", StaticFiles(directory=str(dir_path), html=True), name="result")
        host = (cfg.get("bind_host") or "0.0.0.0").strip()
        port = int(cfg.get("port") or 9001)
        config = uvicorn.Config(app, host=host, port=port, log_level="critical")
        _report_server = uvicorn.Server(config)

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_report_server.serve())
            finally:
                loop.close()

        _report_thread = threading.Thread(target=_run, daemon=True)
        _report_thread.start()
        logger.debug("Result viewer: report server started on %s:%s", host, port)
        return True
    except Exception as e:
        logger.warning("Result viewer: failed to start report server: %s", e)
        _report_server = None
        _report_thread = None
        return False


def stop_report_server() -> None:
    """Stop the report web server. Call when Core stops."""
    global _report_server, _report_thread
    if _report_server is None:
        return
    try:
        from base.util import Util
        Util().stop_uvicorn_server(_report_server)
    except Exception as e:
        logger.debug("Result viewer: stop report server: %s", e)
    _report_server = None
    _report_thread = None
