"""
File and sandbox routes: /files/out, /files/{scope}/{path} (static with token), /api/sandbox/list, /api/upload.
"""
import re
from datetime import datetime
from pathlib import Path
from typing import List
from urllib.parse import unquote

from fastapi import File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from loguru import logger

from base.util import Util


def _escape_for_html(s: str) -> str:
    """Escape for HTML attribute/text. Never raises."""
    try:
        if not isinstance(s, str) or not s:
            return ""
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")
    except Exception:
        return ""


def get_files_out_handler(core):  # noqa: ARG001
    """Return handler for GET /files/out (serve file or directory from sandbox)."""
    async def files_out(path: str = "", token: str = ""):
        """
        Serve a file or directory from the sandbox. Same URL as Core (core_public_url).
        Query: path (e.g. output/report_xxx.html or output), token (signed with auth_api_key).
        For a directory, returns an HTML listing with links to files and subdirs (each link has its own token).
        """
        try:
            from core.result_viewer import verify_file_access_token, build_file_view_link, get_core_public_url
            payload = verify_file_access_token(token)
            if not payload:
                logger.debug("files_out: token verification failed (token_len={})", len((token or "").strip()))
                return JSONResponse(status_code=403, content={"error": "Invalid or expired link"})
            scope, rel_path = payload
            path_arg = (path or "").replace("\\", "/").strip()
            if not path_arg:
                path_arg = rel_path
            if path_arg != rel_path:
                return JSONResponse(status_code=400, content={"error": "Path mismatch"})
            try:
                meta = Util().get_core_metadata()
                base_str = str(meta.get_homeclaw_root() or "").strip()
            except Exception:
                base_str = ""
            if not base_str:
                return JSONResponse(status_code=503, content={"error": "File serving not configured (homeclaw_root)"})
            try:
                base = Path(base_str).resolve()
                full = (base / scope / path_arg).resolve()
            except (OSError, RuntimeError, ValueError) as path_err:
                logger.debug("files_out path resolve failed: {}", path_err)
                return JSONResponse(status_code=503, content={"error": "File serving path invalid"})
            try:
                full.relative_to(base)
            except ValueError:
                return JSONResponse(status_code=403, content={"error": "Path not in sandbox"})
            if not full.is_file():
                # Case-insensitive fallback: on case-sensitive FS, file may be ID1.JPG vs images/ID1.jpg
                parent = full.parent
                if parent.is_dir():
                    try:
                        name_lower = full.name.lower()
                        for sibling in parent.iterdir():
                            if sibling.is_file() and sibling.name.lower() == name_lower:
                                full = sibling
                                break
                    except OSError:
                        pass
            if full.is_dir():
                base_url = get_core_public_url() or ""
                entries = []
                try:
                    children = sorted(full.iterdir(), key=lambda x: (not x.is_dir(), (x.name or "").lower()))
                except OSError:
                    children = []
                for p in children:
                    try:
                        name = p.name or ""
                        if not name or name in (".", ".."):
                            continue
                    except Exception:
                        continue
                    child_rel = f"{path_arg}/{name}".lstrip("/") if path_arg else name
                    child_link, _ = build_file_view_link(scope, child_rel)
                    href = child_link if child_link else "#"
                    entries.append((name, "dir" if p.is_dir() else "file", href))
                html_parts = [
                    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>",
                    _escape_for_html(path_arg or "/"),
                    "</title><style>body{font-family:system-ui;max-width:800px;margin:2rem auto;padding:0 1rem;}",
                    "h1{font-size:1.25rem;} ul{list-style:none;padding:0;} li{margin:0.4rem 0;}",
                    "a{color:#2563eb;} a:hover{text-decoration:underline;} .dir{font-weight:600;}</style></head><body>",
                    "<h1>",
                    _escape_for_html(path_arg or "Workspace"),
                    "</h1><ul>",
                ]
                for name, kind, href in entries:
                    cls = " class='dir'" if kind == "dir" else ""
                    html_parts.append(f"<li{cls}><a href='{_escape_for_html(href)}'>{_escape_for_html(name)}</a></li>")
                html_parts.append("</ul></body></html>")
                return HTMLResponse(content="".join(html_parts))
            if not full.is_file():
                attempted = str(full)
                logger.info("files/out: file not found scope=%s path=%s resolved=%s", scope, path_arg, attempted)
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": "File not found",
                        "detail": f"Server looked for: {scope}/{path_arg} (resolved to {attempted}). Check that the file exists there and that homeclaw_root in config points to the correct directory.",
                    },
                )
            media_type = None
            suf = full.suffix.lower()
            if suf in (".html", ".htm"):
                media_type = "text/html; charset=utf-8"
            elif suf == ".md":
                media_type = "text/markdown; charset=utf-8"
            elif suf in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                media_type = ("image/png" if suf == ".png" else "image/jpeg" if suf in (".jpg", ".jpeg") else "image/gif" if suf == ".gif" else "image/webp")
            return FileResponse(str(full), media_type=media_type)
        except Exception as e:
            logger.debug("files_out failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Failed to serve file"})
    return files_out


def get_files_static_handler(core):  # noqa: ARG001
    """
    GET /files/{scope}/{path:path}?token=...
    Serves a file only when the token matches (scope, path). So a link for one user only accesses that user's sandbox.
    """
    from core.result_viewer import verify_file_access_token

    async def files_static(scope: str, path: str, token: str = ""):
        try:
            if not scope or scope.strip().lower() == "out":
                return JSONResponse(status_code=404, content={"error": "Not found"})
            path_arg = (path or "").replace("\\", "/").strip()
            path_arg = unquote(path_arg)
            payload = verify_file_access_token(token)
            if not payload:
                return JSONResponse(status_code=403, content={"error": "Invalid or expired link"})
            token_scope, token_path = payload
            scope_clean = unquote(scope).strip()
            if token_scope != scope_clean or token_path != path_arg:
                return JSONResponse(status_code=403, content={"error": "Link does not match requested path (access denied)"})
            try:
                meta = Util().get_core_metadata()
                base_str = str(meta.get_homeclaw_root() or "").strip()
            except Exception:
                base_str = ""
            if not base_str:
                return JSONResponse(status_code=503, content={"error": "File serving not configured (homeclaw_root)"})
            try:
                base = Path(base_str).resolve()
                full = (base / scope_clean / path_arg).resolve()
            except (OSError, RuntimeError, ValueError):
                return JSONResponse(status_code=400, content={"error": "Invalid path"})
            try:
                full.relative_to(base)
            except ValueError:
                return JSONResponse(status_code=403, content={"error": "Path not in sandbox"})
            if not full.is_file():
                parent = full.parent
                if parent.is_dir():
                    try:
                        name_lower = full.name.lower()
                        for sibling in parent.iterdir():
                            if sibling.is_file() and sibling.name.lower() == name_lower:
                                full = sibling
                                break
                    except OSError:
                        pass
            if not full.is_file():
                return JSONResponse(status_code=404, content={"error": "File not found"})
            suf = full.suffix.lower()
            media_type = None
            if suf in (".html", ".htm"):
                media_type = "text/html; charset=utf-8"
            elif suf == ".md":
                media_type = "text/markdown; charset=utf-8"
            elif suf in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                media_type = "image/png" if suf == ".png" else "image/jpeg" if suf in (".jpg", ".jpeg") else "image/gif" if suf == ".gif" else "image/webp"
            return FileResponse(str(full), media_type=media_type)
        except Exception as e:
            logger.debug("files_static failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Failed to serve file"})

    return files_static


def get_api_sandbox_list_handler(core):  # noqa: ARG001
    """Return handler for GET /api/sandbox/list."""
    async def api_sandbox_list(scope: str = "companion", path: str = "."):
        """
        List contents of a sandbox folder. Query: scope (e.g. 'companion', 'default', or user id), path (e.g. '.' or 'output').
        Returns JSON list of { name, type, path }. Auth: same as /inbound when auth_enabled.
        """
        try:
            meta = Util().get_core_metadata()
            if meta is None:
                return JSONResponse(status_code=503, content={"error": "Core config not available"})
            base_str = str(meta.get_homeclaw_root() or "").strip()
            if not base_str:
                return JSONResponse(status_code=503, content={"error": "Sandbox not configured (homeclaw_root)"})
            base = Path(base_str).resolve()
            scope_clean = str(scope or "companion").strip().lower()
            if scope_clean == "companion":
                effective_scope = "companion"
            elif scope_clean == "share":
                effective_scope = "share"
            elif scope_clean == "default":
                effective_scope = "default"
            else:
                effective_scope = re.sub(r"[^\w\-]", "_", str(scope or "").strip())[:64] or "default"
            path_arg = str(path or ".").strip().replace("\\", "/").strip().lstrip("/") or "."
            try:
                full = (base / effective_scope / path_arg).resolve()
            except (OSError, RuntimeError, ValueError):
                return JSONResponse(status_code=400, content={"error": "Invalid path"})
            try:
                full.relative_to(base)
            except ValueError:
                return JSONResponse(status_code=403, content={"error": "Path not in sandbox"})
            try:
                full.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            if not full.is_dir():
                return JSONResponse(status_code=404, content={"error": "Not a directory or not found"})
            max_entries = 500
            entries = []
            try:
                children = sorted(full.iterdir(), key=lambda x: (not x.is_dir(), (x.name or "").lower()))
            except OSError:
                children = []
            for i, p in enumerate(children):
                if i >= max_entries:
                    entries.append({"name": "...", "type": "truncated", "path": ""})
                    break
                try:
                    rel = str(p.relative_to(base))
                except ValueError:
                    rel = p.name or ""
                try:
                    entries.append({
                        "name": p.name or "",
                        "type": "dir" if p.is_dir() else "file",
                        "path": rel,
                    })
                except Exception:
                    pass
            return JSONResponse(content={"scope": effective_scope, "path": path_arg, "entries": entries})
        except Exception as e:
            logger.debug("api_sandbox_list failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Failed to list sandbox"})
    return api_sandbox_list


def get_api_upload_handler(core):  # noqa: ARG001
    """Return handler for POST /api/upload."""
    async def api_upload(files: List[UploadFile] = File(..., description="Image or file(s) to save for the model")):
        """
        Upload file(s) (images, videos, or documents). Saves to database/uploads/ and returns absolute paths.
        """
        import uuid
        root = Path(Util().root_path())
        upload_dir = root / "database" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        try:
            for f in files:
                if not f.filename:
                    continue
                ext = Path(f.filename).suffix or ".bin"
                allowed_media = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".mp4", ".webm", ".mov", ".avi")
                allowed_docs = (".pdf", ".txt", ".md", ".doc", ".docx", ".rtf", ".csv", ".xls", ".xlsx", ".odt", ".ods")
                allowed = allowed_media + allowed_docs
                if ext.lower() not in allowed:
                    ext = ".bin"
                name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
                path = upload_dir / name
                content = await f.read()
                path.write_bytes(content)
                paths.append(str(path.resolve()))
            return JSONResponse(content={"paths": paths})
        except Exception as e:
            logger.exception("Upload failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": str(e), "paths": []})
    return api_upload
