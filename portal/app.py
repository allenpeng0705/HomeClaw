"""
Portal FastAPI application. Step 1: health/ready/status. Step 3: admin auth, /setup, /login, session, /dashboard.
Phase 2.3: Start Core UI (core status, start, stop). Never crash: unhandled exceptions are caught by the global exception handler and return 500.
"""
import html as html_module
import json
import logging
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from portal import config as portal_config
from portal.config import get_config_dir, get_portal_secret
from portal import auth
from portal import config_api
from portal import config_backup
from portal.session import create_session_value, verify_session_value

app = FastAPI(
    title="HomeClaw Portal",
    description="Local configuration and onboarding for HomeClaw Core.",
    version="0.1.0",
)

# Serve portal static assets (logo, etc.) from portal/static
_portal_static = Path(__file__).resolve().parent / "static"
if _portal_static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_portal_static)), name="static")

_log = logging.getLogger(__name__)

SESSION_COOKIE = "portal_session"


def _get_session_username(request: Request) -> Optional[str]:
    """Return username if valid session cookie present, else None. Never raises."""
    try:
        c = request.cookies.get(SESSION_COOKIE)
        return verify_session_value(c or "")
    except Exception:
        return None


@app.exception_handler(Exception)
def _global_exception_handler(request: Request, exc: Exception):
    """Catch any unhandled exception and return 500 so the server never crashes."""
    _log.exception("Portal route error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


class _APIAuthMiddleware(BaseHTTPMiddleware):
    """Require valid session or X-Portal-Secret (or Bearer) for /api/* when portal_secret is set (Phase 3.2). Never raises."""

    async def dispatch(self, request: Request, call_next):
        try:
            path = request.url.path
            if not path.startswith("/api/"):
                return await call_next(request)
            secret = get_portal_secret()
            has_session = _get_session_username(request) is not None
            if secret:
                if has_session:
                    return await call_next(request)
                header_secret = request.headers.get("X-Portal-Secret", "").strip()
                if not header_secret and (request.headers.get("Authorization") or "").startswith("Bearer "):
                    header_secret = (request.headers.get("Authorization") or "")[7:].strip()
                if header_secret and secrets.compare_digest(header_secret, secret):
                    return await call_next(request)
                return JSONResponse(status_code=401, content={"detail": "Missing or invalid API auth (session or X-Portal-Secret)"})
            # No portal_secret: require session for /api/* except read-only health/info
            if has_session:
                return await call_next(request)
            if path in ("/api/portal/status", "/api/portal/guide/checks") and request.method == "GET":
                return await call_next(request)
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        except Exception as e:
            _log.exception("API auth middleware error: %s", e)
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(_APIAuthMiddleware)


@app.get("/")
def root(request: Request):
    """Redirect: no admin -> /setup; not logged in -> /login; else -> /dashboard."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/ready")
def ready():
    """Readiness for process managers. Returns 200 when the app is up."""
    return PlainTextResponse("ok", status_code=200)


@app.get("/api/portal/status")
def status():
    """Minimal status: portal running and config dir exists (or not). Never raises."""
    config_dir = get_config_dir()
    config_exists = config_dir.is_dir() if config_dir else False
    return JSONResponse(content={
        "service": "portal",
        "config_dir": str(config_dir),
        "config_dir_exists": config_exists,
    })


from portal import guide as guide_module


@app.get("/api/portal/guide/checks")
def guide_checks():
    """Return step-by-step install checks (Python, venv, config dir, config files). Never raises."""
    steps = guide_module.run_guide_checks()
    return JSONResponse(content={"steps": steps})


@app.post("/api/portal/doctor")
def doctor_run():
    """Run doctor (python -m main doctor), return parsed report. Never raises."""
    report = guide_module.run_doctor_report()
    return JSONResponse(content=report)


# ----- Core start / status / stop (Phase 2.3) -----

def _get_core_base_url() -> Optional[str]:
    """Core base URL from config (host:port). Uses 127.0.0.1 when host is 0.0.0.0. Returns None on error."""
    try:
        data = config_api.load_config("core")
        if not data:
            return None
        host = (data.get("host") or "0.0.0.0").strip()
        port = int(data.get("port") or 9000)
        if host == "0.0.0.0":
            host = "127.0.0.1"
        return f"http://{host}:{port}"
    except Exception:
        return None


@app.get("/api/portal/core/status")
def core_status():
    """Poll Core readiness. Returns { running: bool, url: str, error?: str }. Only running when GET /ready returns 200. No cache."""
    def _no_cache(r: JSONResponse) -> JSONResponse:
        r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return r
    url = _get_core_base_url()
    if not url:
        _log.debug("Core status: no URL (core config missing or invalid)")
        return _no_cache(JSONResponse(content={"running": False, "url": "", "error": "no_config"}))
    ready_url = url.rstrip("/") + "/ready"
    try:
        req = Request(ready_url, method="GET")
        resp = urlopen(req, timeout=5)
        code = getattr(resp, "getcode", lambda: getattr(resp, "status", 0))()
        if code == 200:
            return _no_cache(JSONResponse(content={"running": True, "url": url}))
        return _no_cache(JSONResponse(content={"running": False, "url": url, "error": f"http_{code}"}))
    except URLError as e:
        reason = getattr(e, "reason", None)
        raw = str(reason) if reason else str(e)
        _log.debug("Core status %s: %s", ready_url, raw)
        err_msg = "connection refused" if "Connection refused" in raw or "refused" in raw.lower() else ("timeout" if "timed out" in raw.lower() else raw[:80])
        return _no_cache(JSONResponse(content={"running": False, "url": url, "error": err_msg}))
    except OSError as e:
        _log.debug("Core status %s: %s", ready_url, e)
        return _no_cache(JSONResponse(content={"running": False, "url": url, "error": str(e)}))
    except Exception as e:
        _log.debug("Core status %s: %s", ready_url, e)
        return _no_cache(JSONResponse(content={"running": False, "url": url, "error": str(e)}))


@app.post("/api/portal/core/start")
def core_start():
    """Start Core (python -m main start) in background. Returns immediately. Never raises."""
    try:
        root = str(portal_config.ROOT_DIR)
        subprocess.Popen(
            [sys.executable, "-m", "main", "start"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=None,
            start_new_session=True,
        )
        return JSONResponse(content={"result": "started"})
    except Exception as e:
        _log.warning("Core start failed: %s", e)
        return JSONResponse(content={"result": "error", "error": str(e)}, status_code=500)


@app.post("/api/portal/core/stop")
def core_stop():
    """Send shutdown to Core (GET /shutdown). Same machine only. Never raises."""
    url = _get_core_base_url()
    if not url:
        return JSONResponse(content={"result": "error", "error": "Core URL not found"}, status_code=400)
    try:
        req = Request(url.rstrip("/") + "/shutdown", method="GET")
        with urlopen(req, timeout=5) as _:
            pass
        return JSONResponse(content={"result": "sent"})
    except Exception as e:
        _log.warning("Core stop request failed: %s", e)
        return JSONResponse(content={"result": "sent"})


# ----- Channels list and start (Phase 2.4) -----

def _get_channels_list() -> list:
    """Scan channels/ for */channel.py; return sorted list of directory names. Never raises."""
    try:
        channels_dir = portal_config.ROOT_DIR / "channels"
        if not channels_dir.is_dir():
            return []
        out = []
        for entry in channels_dir.iterdir():
            if entry.is_dir() and (entry / "channel.py").is_file():
                out.append(entry.name)
        return sorted(out)
    except Exception:
        return []


@app.get("/api/portal/friend-presets")
def friend_presets_list():
    """Return { presets: [ { id, name }, ... ] } for multi-select (HomeClaw excluded; always added server-side). Never raises."""
    try:
        from base.friend_presets import load_friend_presets
        config_path = str(portal_config.get_config_dir() / "friend_presets.yml")
        presets = load_friend_presets(config_path) or {}
        out = []
        for pid, _ in (presets.items() if isinstance(presets, dict) else []):
            if not pid or not isinstance(pid, str):
                continue
            pid_str = str(pid).strip()
            if not pid_str or pid_str.lower() == "homeclaw":
                continue
            name = pid_str[0].upper() + pid_str[1:] if len(pid_str) > 1 else pid_str.upper()
            out.append({"id": pid_str, "name": name})
        return JSONResponse(content={"presets": out})
    except Exception as e:
        _log.debug("friend-presets list failed: %s", e)
        return JSONResponse(content={"presets": []})


@app.get("/api/portal/channels")
def channels_list():
    """Return { channels: [\"telegram\", \"webchat\", ...] }. Never raises."""
    return JSONResponse(content={"channels": _get_channels_list()})


@app.post("/api/portal/channels/{name}/start")
def channel_start(name: str):
    """Start channel by name (python -m channels.run <name>). Return 200 when process started. Never raises."""
    channels = _get_channels_list()
    name_clean = (name or "").strip()
    if not name_clean or name_clean not in channels:
        return JSONResponse(
            content={"result": "error", "error": f"Unknown channel: {name}"},
            status_code=400,
        )
    try:
        root = str(portal_config.ROOT_DIR)
        subprocess.Popen(
            [sys.executable, "-m", "channels.run", name_clean],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=None,
            start_new_session=True,
        )
        return JSONResponse(content={"result": "started"})
    except Exception as e:
        _log.warning("Channel start failed: %s", e)
        return JSONResponse(content={"result": "error", "error": str(e)}, status_code=500)


# ----- Skills marketplace: search & import from ClawHub -----

def _load_all_skills_list():
    """
    Load all skills from skills_dir, external_skills_dir, and skills_extra_dirs (same logic as Core).
    Returns list of {"folder", "name", "description", "path"}. Never raises; returns [] on error.
    """
    try:
        from pathlib import Path
        from base.skills import get_all_skills_dirs, load_skills_from_dirs
        root = Path(portal_config.ROOT_DIR)
        core_cfg = config_api.load_config("core") or {}
        skills_dir = (core_cfg.get("skills_dir") or "skills").strip() or "skills"
        ext_dir = (core_cfg.get("external_skills_dir") or "").strip()
        extra_dirs = core_cfg.get("skills_extra_dirs") or []
        if not isinstance(extra_dirs, list):
            extra_dirs = []
        disabled = core_cfg.get("skills_disabled") or []
        if not isinstance(disabled, list):
            disabled = []
        dirs = get_all_skills_dirs(skills_dir, ext_dir, extra_dirs, root)
        skills = load_skills_from_dirs(dirs, disabled_folders=disabled, include_body=False)
        out = []
        for s in skills:
            if not isinstance(s, dict):
                continue
            desc = s.get("description")
            desc_str = (desc if isinstance(desc, str) else str(desc or ""))[:500]
            out.append({
                "folder": s.get("folder") or "",
                "name": s.get("name") or s.get("folder") or "",
                "description": desc_str,
                "path": s.get("path") or "",
            })
        return out
    except Exception as e:
        _log.debug("load all skills failed: %s", e)
        return []


@app.get("/api/portal/skills/list")
def skills_list():
    """Return all loaded skills (skills_dir + external_skills_dir + skills_extra_dirs). Requires login. Never raises."""
    skills = _load_all_skills_list()
    return JSONResponse(content={"skills": skills})


@app.get("/api/portal/skills/search")
def skills_search(query: str = ""):
    """Search ClawHub skills via local clawhub CLI. Requires login (API middleware). Never raises."""
    try:
        from base.clawhub_integration import clawhub_available, clawhub_search
        q = (query or "").strip()
        if not q:
            return JSONResponse(content={"results": []})
        if not clawhub_available():
            return JSONResponse(status_code=400, content={"detail": "clawhub not found on PATH"})
        results, raw = clawhub_search(q, limit=20)
        if not raw.ok and raw.error:
            return JSONResponse(status_code=502, content={"detail": raw.error, "stderr": (raw.stderr or "")[-1000:]})
        return JSONResponse(content={"results": results})
    except Exception as e:
        _log.debug("skills search failed: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/portal/skills/install")
def skills_install(body: dict = Body(default_factory=dict)):
    """
    Install (download) via `clawhub install`, then convert into HomeClaw external_skills_dir.
    Requires login (API middleware). Never raises.
    """
    try:
        from base.clawhub_integration import clawhub_available, clawhub_install_and_convert
        if not clawhub_available():
            return JSONResponse(status_code=400, content={"detail": "clawhub not found on PATH"})
        if not isinstance(body, dict):
            body = {}
        skill_id = (body.get("id") or body.get("skill") or "").strip()
        version = (body.get("version") or "").strip()
        dry_run = bool(body.get("dry_run", False))
        with_deps = bool(body.get("with_deps", False))
        if not skill_id:
            return JSONResponse(status_code=400, content={"detail": "Missing skill id"})
        spec = f"{skill_id}@{version}" if version else skill_id

        core_cfg = config_api.load_config("core") or {}
        ext_dir = (core_cfg.get("external_skills_dir") or "external_skills").strip() or "external_skills"
        download_dir = (core_cfg.get("clawhub_download_dir") or "downloads").strip() or "downloads"
        out = clawhub_install_and_convert(
            skill_spec=spec,
            skill_id_hint=skill_id,
            homeclaw_root=portal_config.ROOT_DIR,
            external_skills_dir=ext_dir,
            clawhub_download_dir=download_dir,
            dry_run=dry_run,
            with_deps=with_deps,
        )

        # Skills vector store is off by default; new skills are registered when Core restarts (if vector search enabled).

        status = 200 if out.get("ok") else (502 if (out.get("install") or {}).get("ok") else 500)
        return JSONResponse(status_code=status, content=out)
    except Exception as e:
        _log.debug("skills install failed: %s", e)
        return JSONResponse(status_code=500, content={"detail": str(e)})


# ----- Shared layout and styles -----

_PORTAL_STYLES = """
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: 'Outfit', system-ui, sans-serif;
      background: linear-gradient(160deg, #0f172a 0%, #1e293b 50%, #334155 100%);
      color: #1e293b;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .card {
      background: #ffffff;
      border-radius: 1.25rem;
      box-shadow: 0 25px 50px -12px rgba(0,0,0,0.35);
      padding: 2.5rem;
      width: 100%;
      max-width: 420px;
    }
    .logo {
      display: block;
      margin: 0 auto 1.5rem;
      max-height: 52px;
      width: auto;
    }
    .title { font-size: 1.5rem; font-weight: 700; margin: 0 0 0.5rem; color: #0f172a; }
    .subtitle { font-size: 0.9375rem; color: #64748b; margin: 0 0 1.75rem; line-height: 1.5; }
    .form-group { margin-bottom: 1.25rem; }
    .form-group label { display: block; font-size: 0.875rem; font-weight: 500; color: #475569; margin-bottom: 0.375rem; }
    .form-group input {
      width: 100%;
      padding: 0.75rem 1rem;
      font-family: inherit;
      font-size: 1rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.75rem;
      background: #f8fafc;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .form-group input:focus, .form-group textarea:focus {
      outline: none;
      border-color: #f59e0b;
      box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
    }
    .form-group textarea {
      width: 100%;
      padding: 0.75rem 1rem;
      font-family: inherit;
      font-size: 0.875rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.75rem;
      background: #f8fafc;
      resize: vertical;
      min-height: 4rem;
    }
    .form-group select {
      width: 100%;
      padding: 0.75rem 1rem;
      font-family: inherit;
      font-size: 1rem;
      border: 1px solid #e2e8f0;
      border-radius: 0.75rem;
      background: #f8fafc;
    }
    .form-hint { font-size: 0.8125rem; color: #64748b; margin: 0.25rem 0 0; }
    .form-section-title { font-size: 1.125rem; font-weight: 600; color: #0f172a; margin: 1.5rem 0 0.75rem; padding-top: 1rem; border-top: 1px solid #e2e8f0; }
    .llm-btn-row { display: flex; gap: 0.5rem; align-items: center; margin-top: 0.375rem; }
    .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8125rem; }
    .llm-selected-box { margin-top: 0.5rem; padding: 0.75rem; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.375rem; }
    .llm-json-preview { margin: 0 0 0.5rem; padding: 0.75rem; font-size: 0.8125rem; overflow: auto; max-height: 12rem; white-space: pre-wrap; word-break: break-word; background: #fff; border: 1px solid #e2e8f0; border-radius: 0.25rem; }
    .modal {{ display: none; position: fixed; inset: 0; z-index: 100; align-items: center; justify-content: center; padding: 1rem; background: rgba(0,0,0,0.4); }}
    .modal.show {{ display: flex; }}
    .modal-box {{ background: #fff; border-radius: 1rem; padding: 1.5rem; max-width: 420px; width: 100%; max-height: 90vh; overflow-y: auto; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.35); }}
    .modal-box h3 {{ margin: 0 0 1rem; font-size: 1.25rem; }}
    .modal-cancel {{ margin-top: 1rem; background: #e2e8f0; color: #334155; }}
    .model-list {{ list-style: none; padding: 0; margin: 0.5rem 0; }}
    .model-list li {{ display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: #f8fafc; border-radius: 0.5rem; margin-bottom: 0.25rem; font-size: 0.875rem; }}
    .model-list li span {{ flex: 1; }}
    .btn-sm {{ padding: 0.25rem 0.75rem; font-size: 0.8125rem; background: #e2e8f0; color: #475569; border: none; border-radius: 0.5rem; cursor: pointer; }}
    .btn-sm:hover {{ background: #f59e0b; color: #fff; }}
    .btn-add {{ margin-bottom: 0.5rem; padding: 0.5rem 1rem; font-size: 0.875rem; background: #f1f5f9; color: #0f172a; border: 1px solid #e2e8f0; border-radius: 0.5rem; cursor: pointer; }}
    .btn-add:hover {{ background: #e2e8f0; }}
    .btn {
      width: 100%;
      padding: 0.875rem 1.25rem;
      font-family: inherit;
      font-size: 1rem;
      font-weight: 600;
      color: #fff;
      background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
      border: none;
      border-radius: 0.75rem;
      cursor: pointer;
      margin-top: 0.5rem;
      transition: transform 0.15s, box-shadow 0.15s;
    }
    .btn:hover { transform: translateY(-1px); box-shadow: 0 10px 20px -10px rgba(245, 158, 11, 0.5); }
    .btn:active { transform: translateY(0); }
    a.btn, .page-content a.btn, .card a.btn {{ text-decoration: none !important; }}
    a.btn:hover, .page-content a.btn:hover, .card a.btn:hover {{ text-decoration: none !important; }}
    a.btn:active, .page-content a.btn:active, .card a.btn:active {{ text-decoration: none !important; }}
    a.btn:focus, .page-content a.btn:focus, .card a.btn:focus {{ text-decoration: none !important; }}
    .dashboard-core-card .btn:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    .error { font-size: 0.875rem; color: #dc2626; margin-top: 1rem; text-align: center; }
    .dashboard-welcome { font-size: 1rem; color: #475569; margin: 0 0 1.5rem; }
    .dashboard-meta { font-size: 0.875rem; color: #94a3b8; margin-top: 1.5rem; }
    .nav-header {{ display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem 1.5rem; background: rgba(15,23,42,0.95); color: #e2e8f0; font-size: 0.9375rem; flex-wrap: wrap; }}
    .nav-header a {{
      display: inline-block;
      padding: 0.5rem 1.25rem;
      color: #cbd5e1;
      text-decoration: none !important;
      border-radius: 0.5rem;
      border: 1px solid transparent;
      background: rgba(255,255,255,0.08);
      font-weight: 500;
      transition: color 0.2s, background 0.2s, border-color 0.2s;
      touch-action: manipulation;
    }}
    .nav-header a:hover {{ color: #fff; background: rgba(255,255,255,0.12); border-color: rgba(255,255,255,0.2); }}
    .nav-header a.active {{
      color: #fff;
      font-weight: 600;
      background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
      border-color: rgba(255,255,255,0.2);
    }}
    .page-wrap { min-height: 100vh; display: flex; flex-direction: column; }
    .page-content { flex: 1; padding: 1.5rem; display: flex; align-items: flex-start; justify-content: center; }
    .card-wide { max-width: 720px; }
    .settings-msg {{ font-size: 0.875rem; margin-top: 1rem; padding: 0.5rem; border-radius: 0.5rem; }}
    .settings-msg.ok {{ background: #dcfce7; color: #166534; }}
    .settings-msg.err {{ background: #fee2e2; color: #991b1b; }}
    .btn-block {{ width: 100%; }}
    /* Settings: real tab/button style, spacing via margin so links never squeeze */
    .settings-subnav {{
      display: block;
      margin: 1.25rem 0 1.75rem;
      padding: 0;
    }}
    .settings-tab-item {{
      display: inline-block;
      margin: 0 0.5rem 0.5rem 0;
      vertical-align: top;
    }}
    .settings-subnav a.settings-tab-link {{
      display: inline-block !important;
      padding: 0.75rem 1.5rem !important;
      margin: 0 0.5rem 0.5rem 0 !important;
      font-size: 0.9375rem !important;
      font-weight: 600 !important;
      color: #475569 !important;
      text-decoration: none !important;
      border-radius: 0.5rem !important;
      border: 1px solid #cbd5e1 !important;
      background: #f1f5f9 !important;
      white-space: nowrap !important;
    }}
    .settings-subnav a.settings-tab-link:hover {{
      color: #0f172a !important;
      background: #e2e8f0 !important;
      border-color: #94a3b8 !important;
    }}
    .settings-subnav a.settings-tab-link.active {{
      color: #fff !important;
      background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
      border-color: #b45309 !important;
    }}
    .settings-subnav a.active:hover {{
      box-shadow: 0 3px 10px rgba(245, 158, 11, 0.45);
    }}
    .settings-form-wrap {{ margin-top: 0.5rem; }}
    /* Settings app: pill tabs + content (match portal look) */
    #settings-app {{ margin-top: 1.5rem; }}
    #settings-tabs {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    #settings-tabs .tab {{
      padding: 0.625rem 1.25rem;
      font-size: 0.9375rem;
      font-weight: 500;
      color: #475569;
      background: #f1f5f9;
      border: none;
      border-radius: 9999px;
      cursor: pointer;
      white-space: nowrap;
      transition: color 0.2s, background 0.2s, box-shadow 0.2s;
      touch-action: manipulation;
    }}
    #settings-tabs .tab:hover {{ color: #0f172a; background: #e2e8f0; }}
    #settings-tabs .tab.active {{
      color: #fff;
      background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
      box-shadow: 0 2px 8px rgba(245, 158, 11, 0.35);
    }}
    #settings-tabs .tab.active:hover {{ filter: brightness(1.05); }}
    #settings-content {{ min-height: 280px; padding: 0.25rem 0 1rem; }}
    #settings-content .loading-state {{ display: flex; align-items: center; justify-content: center; min-height: 200px; color: #64748b; font-size: 0.9375rem; }}
    #settings-content .settings-form {{ max-width: 100%; }}
    #settings-app .form-group {{ margin-bottom: 1.25rem; }}
    #settings-app .form-group label {{ display: block; font-size: 0.8125rem; font-weight: 600; color: #475569; margin-bottom: 0.375rem; letter-spacing: 0.01em; }}
    #settings-app .btn {{ width: auto; min-width: 120px; padding: 0.625rem 1.5rem; font-size: 0.9375rem; font-weight: 600; color: #fff; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border: none; border-radius: 0.75rem; cursor: pointer; margin-top: 0.5rem; transition: transform 0.15s, box-shadow 0.15s; touch-action: manipulation; }}
    #settings-app .btn:hover {{ transform: translateY(-1px); box-shadow: 0 8px 16px -8px rgba(245, 158, 11, 0.45); }}
    #settings-app .btn:active {{ transform: translateY(0); }}
    /* Mobile & WebView: touch targets, safe areas, responsive */
    @media (max-width: 768px) {
      .page-content { padding: 1rem; padding-left: max(1rem, env(safe-area-inset-left)); padding-right: max(1rem, env(safe-area-inset-right)); padding-bottom: max(1rem, env(safe-area-inset-bottom)); }
      .card, .card-wide { max-width: 100%; margin: 0; border-radius: 0; box-shadow: none; padding: 1rem; padding-left: max(1rem, env(safe-area-inset-left)); padding-right: max(1rem, env(safe-area-inset-right)); }
      .nav-header { padding: 0.75rem 1rem; padding-left: max(1rem, env(safe-area-inset-left)); padding-right: max(1rem, env(safe-area-inset-right)); gap: 0.75rem; font-size: 0.875rem; flex-wrap: wrap; }
      .nav-header a { min-height: 44px; min-width: 44px; display: inline-flex; align-items: center; justify-content: center; }
      .settings-subnav { margin: 1rem 0 1.25rem; overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none; }
      .settings-subnav::-webkit-scrollbar { display: none; }
      .settings-tab-item { margin: 0 0.5rem 0.5rem 0; }
      .settings-subnav a { min-height: 44px; min-width: 44px; padding: 0.7rem 1.25rem; font-size: 0.875rem; display: inline-flex; align-items: center; justify-content: center; white-space: nowrap; }
      #settings-app { margin-top: 0.75rem; }
      #settings-tabs { margin-bottom: 1.25rem; scrollbar-width: none; }
      #settings-tabs::-webkit-scrollbar { display: none; }
      #settings-tabs .tab { min-height: 44px; min-width: 44px; padding: 0.75rem 1rem; font-size: 0.875rem; }
      #settings-content { min-height: 240px; padding: 1rem 0; padding-bottom: env(safe-area-inset-bottom); }
      #settings-content .loading-state { min-height: 160px; font-size: 0.9375rem; }
      #settings-app .form-group { margin-bottom: 1rem; }
      #settings-app .form-group input, #settings-app .form-group select, #settings-app .form-group textarea { min-height: 44px; font-size: 16px; }
      #settings-app .form-group textarea { min-height: 6rem; }
      #settings-app .btn { width: 100%; min-height: 48px; padding: 0.75rem 1.5rem; font-size: 1rem; }
      .modal { padding: 0.5rem; padding-left: env(safe-area-inset-left); padding-right: env(safe-area-inset-right); align-items: flex-end; }
      .modal-box { max-width: 100%; max-height: 85vh; border-radius: 1rem 1rem 0 0; padding: 1.25rem; padding-bottom: max(1.25rem, env(safe-area-inset-bottom)); }
      .modal-box .btn, .modal-box .modal-cancel { min-height: 48px; padding: 0.75rem 1rem; }
      .btn-sm { min-height: 44px; padding: 0.5rem 1rem; }
      .btn-add { min-height: 44px; padding: 0.625rem 1rem; width: 100%; }
      .model-list li { min-height: 44px; padding: 0.625rem 0.75rem; }
      .title { font-size: 1.5rem; }
      .subtitle { font-size: 0.9375rem; }
    }
    @media (max-width: 480px) {
      .page-content { padding: 0.75rem; }
      .card, .card-wide { padding: 0.75rem; }
      #settings-tabs .tab { padding: 0.75rem 0.875rem; font-size: 0.8125rem; }
    }
  </style>
"""

def _portal_page(title: str, body: str, show_logo: bool = True) -> str:
    logo = '<img src="/static/img/homeclaw-logo.png" alt="HomeClaw" class="logo">' if show_logo else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0f172a"><title>{title} — HomeClaw Portal</title>{_PORTAL_STYLES}</head>
<body><div class="card">{logo}{body}</div></body></html>"""


def _logged_in_page(title: str, nav_active: str, content: str, card_class: str = "card") -> str:
    """Layout for dashboard/settings: nav bar + content. nav_active is 'dashboard' or 'settings'."""
    def nav_link(href: str, label: str, active: bool) -> str:
        if active:
            style = "display:inline-block;padding:0.5rem 1.25rem;color:#fff;text-decoration:none;border-radius:0.5rem;border:1px solid rgba(255,255,255,0.2);background:linear-gradient(135deg,#f59e0b 0%,#d97706 100%);font-weight:600;"
        else:
            style = "display:inline-block;padding:0.5rem 1.25rem;color:#cbd5e1;text-decoration:none;border-radius:0.5rem;border:1px solid transparent;background:rgba(255,255,255,0.08);font-weight:500;"
        cls = ' class="active"' if active else ""
        return f'<a href="{href}"{cls} style="{style}">{html_module.escape(label)}</a>'
    nav_html = nav_link("/dashboard", "Dashboard", nav_active == "dashboard") + "\n    " + nav_link("/channels", "Start channel", nav_active == "channels") + "\n    " + nav_link("/skills", "Skills", nav_active == "skills") + "\n    " + nav_link("/guide", "Guide to install", nav_active == "guide") + "\n    " + nav_link("/settings", "Manage settings", nav_active == "settings") + "\n    " + nav_link("/logout", "Log out", False)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0f172a"><title>{title} — HomeClaw Portal</title>{_PORTAL_STYLES}</head>
<body class="page-wrap">
  <nav class="nav-header" style="display:flex;align-items:center;gap:0.75rem;padding:0.75rem 1.5rem;background:rgba(15,23,42,0.95);flex-wrap:wrap;">
    {nav_html}
  </nav>
  <main class="page-content"><div class="{card_class}">{content}</div></main>
</body></html>"""


# ----- Setup (first-time admin) -----

def _setup_html(has_error: bool) -> str:
    err = '<p class="error">Please choose a username and password (both required).</p>' if has_error else ""
    return _portal_page("Set admin account", f"""
  <h1 class="title">Create admin account</h1>
  <p class="subtitle">Set the single admin account for this Portal. You’ll use it to log in from now on.</p>
  <form method="post" action="/setup">
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" required autocomplete="username" placeholder="admin">
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required autocomplete="new-password" placeholder="••••••••">
    </div>
    <button type="submit" class="btn">Create account</button>
    {err}
  </form>
""")


@app.get("/setup", response_class=HTMLResponse)
def setup_get(request: Request):
    """Show setup form if admin not configured; else redirect to login."""
    if auth.admin_is_configured():
        return RedirectResponse(url="/login", status_code=302)
    has_error = request.query_params.get("error") == "1"
    return HTMLResponse(_setup_html(has_error))


@app.post("/setup")
def setup_post(username: str = Form(""), password: str = Form("")):
    """Create admin account; redirect to login."""
    if auth.admin_is_configured():
        return RedirectResponse(url="/login", status_code=302)
    if auth.set_admin(username, password):
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/setup?error=1", status_code=302)


# ----- Login -----

def _login_html(has_error: bool) -> str:
    err = '<p class="error">Invalid username or password.</p>' if has_error else ""
    return _portal_page("Log in", f"""
  <h1 class="title">Welcome back</h1>
  <p class="subtitle">Sign in with your Portal admin account.</p>
  <form method="post" action="/login">
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" required autocomplete="username" placeholder="admin">
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required autocomplete="current-password" placeholder="••••••••">
    </div>
    <button type="submit" class="btn">Log in</button>
    {err}
  </form>
""")


@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    """Show login form; if admin not set redirect to setup."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    has_error = request.query_params.get("error") == "1"
    return HTMLResponse(_login_html(has_error))


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    """Verify credentials; set session cookie and redirect to dashboard or back to login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if auth.verify_portal_admin(username, password):
        value = create_session_value(username)
        r = RedirectResponse(url="/dashboard", status_code=302)
        r.set_cookie(
            key=SESSION_COOKIE,
            value=value,
            max_age=24 * 3600,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return r
    return RedirectResponse(url="/login?error=1", status_code=302)


# ----- Logout -----

@app.get("/logout")
def logout():
    """Clear session and redirect to login."""
    r = RedirectResponse(url="/login", status_code=302)
    r.delete_cookie(SESSION_COOKIE, path="/")
    return r


# ----- Dashboard (protected) -----

def _dashboard_html(username: str) -> str:
    safe_user = html_module.escape(username)
    return _logged_in_page("Dashboard", "dashboard", f"""
  <img src="/static/img/homeclaw-logo.png" alt="HomeClaw" class="logo">
  <h1 class="title">Dashboard</h1>
  <p class="dashboard-welcome">You’re logged in as <strong>{safe_user}</strong>.</p>
  <p class="subtitle">Manage Core and channel configuration, then start services from here.</p>
  <div class="dashboard-core-card" style="margin:1.5rem 0;padding:1.25rem;background:#f8fafc;border:1px solid #e2e8f0;border-radius:0.5rem;">
    <h2 style="font-size:1.125rem;margin:0 0 0.75rem 0;color:#0f172a;">HomeClaw</h2>
    <p style="margin:0;">
      <button type="button" class="btn" id="core-start-btn" style="display:inline-block;width:auto;padding:0.75rem 1.5rem;margin-top:0;margin-right:0.5rem;">Start</button>
      <button type="button" class="btn" id="core-stop-btn" style="display:inline-block;width:auto;padding:0.75rem 1.5rem;margin-top:0;">Stop</button>
    </p>
  </div>
  <script>
  (function() {{
    var startBtn = document.getElementById('core-start-btn');
    var stopBtn = document.getElementById('core-stop-btn');
    if (startBtn) startBtn.onclick = function() {{ fetch('/api/portal/core/start', {{ method: 'POST', credentials: 'same-origin' }}); }};
    if (stopBtn) stopBtn.onclick = function() {{ fetch('/api/portal/core/stop', {{ method: 'POST', credentials: 'same-origin' }}); }};
  }})();
  </script>
  <p><a href="/guide" class="btn" style="display:inline-block;width:auto;padding:0.75rem 1.5rem;text-decoration:none;">Guide to install</a> <a href="/settings" class="btn" style="display:inline-block;width:auto;padding:0.75rem 1.5rem;margin-left:0.5rem;text-decoration:none;">Manage settings</a></p>
  <p class="dashboard-meta">HomeClaw Portal — local config &amp; onboarding</p>
""")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_get(request: Request):
    """Show dashboard if session valid; else redirect to login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    user = _get_session_username(request)
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(_dashboard_html(user))


# ----- Start channel (Phase 2.4) -----

def _channels_page_content() -> str:
    """Start channel page: list from API, Start Core + Start <channel> buttons."""
    return r"""
  <h1 class="title">Start channel</h1>
  <p class="subtitle">Start Core from the Dashboard first, then start one or more channels.</p>
  <p><a href="/dashboard" class="btn" style="display:inline-block;width:auto;padding:0.75rem 1.5rem;text-decoration:none;">Dashboard (Start Core)</a></p>
  <div id="channels-list-wrap" style="margin-top:1.25rem;">
    <p id="channels-loading">Loading channels…</p>
    <ul id="channels-list" class="channel-buttons" style="display:none;list-style:none;padding:0;margin:0;"></ul>
  </div>
  <style>
    .channel-buttons { display: grid; gap: 0.5rem; }
    .channel-buttons li { display: flex; align-items: center; gap: 0.75rem; }
    .channel-buttons .btn { min-height: 44px; padding: 0.5rem 1.25rem; }
  </style>
  <script>
(function() {
  var listEl = document.getElementById('channels-list');
  var loadingEl = document.getElementById('channels-loading');
  function startChannel(name) {
    fetch('/api/portal/channels/' + encodeURIComponent(name) + '/start', { method: 'POST', headers: { 'Accept': 'application/json' } })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.result === 'started') alert('Started ' + name);
        else alert(data.error || 'Failed to start');
      })
      .catch(function(e) { alert('Request failed: ' + e.message); });
  }
  fetch('/api/portal/channels')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      loadingEl.style.display = 'none';
      listEl.style.display = 'grid';
      var channels = data.channels || [];
      channels.forEach(function(name) {
        var li = document.createElement('li');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn';
        btn.textContent = 'Start ' + name;
        btn.onclick = function() { startChannel(name); };
        li.appendChild(btn);
        listEl.appendChild(li);
      });
      if (channels.length === 0) listEl.innerHTML = '<li><em>No channels found.</em></li>';
    })
    .catch(function(e) {
      loadingEl.textContent = 'Failed to load channels: ' + e.message;
    });
})();
  </script>
"""


@app.get("/channels", response_class=HTMLResponse)
def channels_page_get(request: Request):
    """Show Start channel page; require login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(_logged_in_page("Start channel", "channels", _channels_page_content()))


# ----- Skills marketplace (protected) -----

def _skills_page_content() -> str:
    """Skills marketplace page: list all loaded skills + search/install from ClawHub."""
    return r"""
  <h1 class="title">Skills</h1>
  <p class="subtitle">All skills loaded from <code>skills/</code>, <code>external_skills/</code>, and any extra dirs (config). Search and import more from <strong>ClawHub</strong> below.</p>

  <h2 style="font-size:1.125rem;margin:1rem 0 0.5rem 0;color:#0f172a;">Installed skills</h2>
  <p id="installed-msg" class="dashboard-meta" style="min-height:1.2rem;">Loading…</p>
  <div id="installed-skills" style="margin-top:0.5rem;"></div>

  <h2 style="font-size:1.125rem;margin:1.5rem 0 0.5rem 0;color:#0f172a;">Import from ClawHub</h2>
  <div class="form-group">
    <label for="skill-query">Search</label>
    <input type="text" id="skill-query" placeholder="e.g. summarize, github, web scraping" autocomplete="off">
  </div>
  <div style="display:flex;gap:0.5rem;flex-wrap:wrap;">
    <button type="button" class="btn" id="skill-search-btn" style="display:inline-block;width:auto;padding:0.75rem 1.25rem;margin-top:0;">Search</button>
    <button type="button" class="btn" id="skill-clear-btn" style="display:inline-block;width:auto;padding:0.75rem 1.25rem;margin-top:0;background:#334155;">Clear</button>
  </div>
  <p id="skill-msg" class="dashboard-meta" style="min-height:1.2rem;margin-top:0.75rem;"></p>
  <div id="skill-results" style="margin-top:1rem;"></div>

  <div style="margin-top:1.25rem;padding:0.9rem 1rem;background:#fff7ed;border:1px solid #fed7aa;border-radius:0.75rem;">
    <strong>Security note</strong>
    <p style="margin:0.25rem 0 0 0;color:#7c2d12;">
      ClawHub skills are third-party code. Review the installed files under <code>external_skills/</code> before enabling tools that execute scripts.
    </p>
  </div>

  <script>
  (function() {
    var qEl = document.getElementById('skill-query');
    var msgEl = document.getElementById('skill-msg');
    var resEl = document.getElementById('skill-results');
    var btnSearch = document.getElementById('skill-search-btn');
    var btnClear = document.getElementById('skill-clear-btn');
    var installedMsg = document.getElementById('installed-msg');
    var installedEl = document.getElementById('installed-skills');
    function esc(s) {
      return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
    function setMsg(s) { msgEl.textContent = s || ''; }
    function loadInstalledSkills() {
      if (!installedMsg) return;
      installedMsg.textContent = 'Loading…';
      fetch('/api/portal/skills/list', { credentials: 'same-origin' })
        .then(function(r) { return r.json().then(function(j){ return { ok:r.ok, j:j }; }); })
        .then(function(resp) {
          if (!installedMsg || !installedEl) return;
          if (!resp.ok) { installedMsg.textContent = 'Failed to load list.'; installedEl.innerHTML = ''; return; }
          var list = (resp.j && resp.j.skills) ? resp.j.skills : [];
          installedMsg.textContent = list.length + ' skill(s) loaded.';
          if (list.length === 0) { installedEl.innerHTML = '<p class="dashboard-meta">No skills in skills/ or external_skills/.</p>'; return; }
          var html = '<div style="display:grid;gap:0.5rem;">';
          list.forEach(function(s) {
            var folder = s.folder || s.name || '';
            var desc = (s.description || '').trim();
            html += '<div style="padding:0.6rem 0.75rem;border:1px solid #e2e8f0;border-radius:0.5rem;background:#f8fafc;">';
            html += '<div style="font-weight:600;color:#0f172a;"><code>' + esc(folder) + '</code></div>';
            if (desc) html += '<div class="dashboard-meta" style="margin-top:0.2rem;font-size:0.875rem;">' + esc(desc) + '</div>';
            html += '</div>';
          });
          html += '</div>';
          installedEl.innerHTML = html;
        })
        .catch(function(e) { if (installedMsg) installedMsg.textContent = 'Load error: ' + e.message; });
    }
    loadInstalledSkills();
    function renderResults(rows) {
      if (!rows || rows.length === 0) { resEl.innerHTML = '<p class="dashboard-meta">No results.</p>'; return; }
      var html = '<div style="display:grid;gap:0.75rem;">';
      rows.forEach(function(r) {
        var id = r.id || r.name || '';
        var desc = r.description || '';
        html += '<div style="padding:0.9rem 1rem;border:1px solid #e2e8f0;border-radius:0.75rem;background:#f8fafc;">';
        html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.75rem;flex-wrap:wrap;">';
        html += '<div><div style="font-weight:700;color:#0f172a;"><code>' + esc(id) + '</code></div>';
        if (desc) html += '<div class="dashboard-meta" style="margin-top:0.25rem;color:#334155;">' + esc(desc) + '</div>';
        html += '</div>';
        html += '<button type="button" class="btn btn-sm" data-skill="' + esc(id) + '" style="display:inline-block;width:auto;margin-top:0;padding:0.55rem 1rem;">Install</button>';
        html += '</div></div>';
      });
      html += '</div>';
      resEl.innerHTML = html;
      resEl.querySelectorAll('button[data-skill]').forEach(function(b) {
        b.onclick = function() { installSkill(b.getAttribute('data-skill') || ''); };
      });
    }
    function doSearch() {
      var q = (qEl.value || '').trim();
      if (!q) { setMsg('Enter a search query.'); return; }
      setMsg('Searching…');
      fetch('/api/portal/skills/search?query=' + encodeURIComponent(q), { credentials: 'same-origin' })
        .then(function(r) { return r.json().then(function(j){ return { ok:r.ok, j:j }; }); })
        .then(function(resp) {
          if (!resp.ok) { setMsg((resp.j && resp.j.detail) ? resp.j.detail : 'Search failed'); renderResults([]); return; }
          setMsg('Results: ' + ((resp.j.results || []).length));
          renderResults(resp.j.results || []);
        })
        .catch(function(e) { setMsg('Search error: ' + e.message); renderResults([]); });
    }
    function installSkill(id) {
      id = (id || '').trim();
      if (!id) return;
      if (!confirm('Install and import skill \"' + id + '\" from ClawHub?')) return;
      setMsg('Installing ' + id + '…');
      fetch('/api/portal/skills/install', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ id: id })
      })
      .then(function(r) { return r.json().then(function(j){ return { ok:r.ok, j:j, status:r.status }; }); })
      .then(function(resp) {
        if (!resp.ok) {
          var detail = (resp.j && (resp.j.error || resp.j.detail)) ? (resp.j.error || resp.j.detail) : ('Install failed (HTTP ' + resp.status + ')');
          setMsg(detail);
          return;
        }
        var out = resp.j || {};
        var output = (out.convert && out.convert.output) ? out.convert.output : '';
        setMsg('Installed. Converted to: ' + output);
        loadInstalledSkills();
      })
      .catch(function(e) { setMsg('Install error: ' + e.message); });
    }
    if (btnSearch) btnSearch.onclick = doSearch;
    if (btnClear) btnClear.onclick = function() { qEl.value=''; resEl.innerHTML=''; setMsg(''); };
    if (qEl) qEl.addEventListener('keydown', function(ev){ if (ev.key === 'Enter') doSearch(); });
  })();
  </script>
"""


@app.get("/skills", response_class=HTMLResponse)
def skills_page_get(request: Request):
    """Show skills marketplace page; require login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(_logged_in_page("Skills", "skills", _skills_page_content(), card_class="card card-wide"))


# ----- Guide to install (protected) -----

def _guide_page_content() -> str:
    """Guide to install: steps 1–4 from API, step 5 = Run doctor. One step at a time, Next/Back."""
    return r"""
  <h1 class="title">Guide to install</h1>
  <p class="subtitle">Step-by-step checks: Python, venv, config, and optional doctor.</p>
  <div id="guide-steps" class="guide-steps">
    <p id="guide-loading">Loading checks…</p>
    <div id="guide-content" style="display:none;">
      <p id="guide-step-label" class="guide-step-label"></p>
      <div id="guide-step-box" class="guide-step-box"></div>
      <div class="llm-btn-row" style="margin-top:1rem;">
        <button type="button" class="btn btn-sm" id="guide-back">Back</button>
        <button type="button" class="btn btn-sm" id="guide-next">Next</button>
      </div>
    </div>
  </div>
  <style>
    .guide-step-label { font-weight: 600; color: #0f172a; margin-bottom: 0.5rem; }
    .guide-step-box { padding: 1rem; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; }
    .guide-step-box.ok { border-left: 4px solid #22c55e; }
    .guide-step-box.fail { border-left: 4px solid #ef4444; }
    .guide-step-box .hint { margin-top: 0.75rem; color: #475569; font-size: 0.9375rem; }
    #guide-doctor-result { white-space: pre-wrap; font-size: 0.875rem; margin-top: 0.5rem; }
  </style>
  <script>
(function() {
  var steps = [];
  var current = 0;
  var doctorResult = null;
  var content = document.getElementById('guide-content');
  var loading = document.getElementById('guide-loading');
  var stepLabel = document.getElementById('guide-step-label');
  var stepBox = document.getElementById('guide-step-box');

  function stepTitles() {
    var t = ['Python (system or venv)', 'Dependencies', 'Node.js', 'llama.cpp', 'GGUF models', 'Doctor (optional)'];
    return t;
  }

  function renderStep() {
    if (current === 5) {
      stepLabel.textContent = 'Step 6 of 6: Doctor';
      stepBox.className = 'guide-step-box';
      stepBox.innerHTML = '<p>Run the doctor to check config and LLM connectivity.</p>' +
        '<button type="button" class="btn btn-sm" id="guide-run-doctor">Run doctor</button>' +
        '<pre id="guide-doctor-result"></pre>';
      var btn = document.getElementById('guide-run-doctor');
      if (btn) btn.onclick = runDoctor;
      var pre = document.getElementById('guide-doctor-result');
      if (pre && doctorResult) pre.textContent = doctorResult;
      return;
    }
    var s = steps[current];
    if (!s) {
      stepLabel.textContent = 'Step ' + (current + 1) + ' of 6: ' + stepTitles()[current];
      stepBox.textContent = 'No data.';
      stepBox.className = 'guide-step-box';
      return;
    }
    stepLabel.textContent = 'Step ' + (current + 1) + ' of 6: ' + stepTitles()[current];
    stepBox.className = 'guide-step-box ' + (s.ok ? 'ok' : 'fail');
    stepBox.innerHTML = '<p><strong>' + (s.ok ? 'Pass' : 'Fail') + '</strong>: ' + escapeHtml(s.message) + '</p>' +
      '<p class="hint">' + escapeHtml(s.hint || '').replace(/\n/g, '<br>') + '</p>';
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function runDoctor() {
    var pre = document.getElementById('guide-doctor-result');
    if (pre) pre.textContent = 'Running doctor…';
    fetch('/api/portal/doctor', { method: 'POST', headers: { 'Accept': 'application/json' } })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var lines = [];
        if (data.error) lines.push('Error: ' + data.error);
        data.ok = data.ok || [];
        data.issues = data.issues || [];
        data.ok.forEach(function(s) { lines.push('OK: ' + s); });
        data.issues.forEach(function(s) { lines.push('Issue: ' + s); });
        if (!lines.length && data.output) lines.push(data.output);
        doctorResult = lines.join('\n');
        if (pre) pre.textContent = doctorResult;
      })
      .catch(function(e) {
        doctorResult = 'Request failed: ' + e.message;
        if (pre) pre.textContent = doctorResult;
      });
  }

  function updateButtons() {
    var back = document.getElementById('guide-back');
    var next = document.getElementById('guide-next');
    if (back) back.style.display = current > 0 ? 'inline-block' : 'none';
    if (next) {
      next.style.display = 'inline-block';
      next.textContent = current < 5 ? 'Next' : 'Done';
    }
  }

  document.getElementById('guide-back').onclick = function() {
    if (current > 0) { current--; renderStep(); updateButtons(); }
  };
  document.getElementById('guide-next').onclick = function() {
    if (current < 5) { current++; renderStep(); updateButtons(); }
  };

  fetch('/api/portal/guide/checks')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      steps = data.steps || [];
      loading.style.display = 'none';
      content.style.display = 'block';
      current = 0;
      renderStep();
      updateButtons();
    })
    .catch(function(e) {
      loading.textContent = 'Failed to load checks: ' + e.message;
    });
})();
  </script>
"""


@app.get("/guide", response_class=HTMLResponse)
def guide_get(request: Request):
    """Show Guide to install page; require login."""
    if not auth.admin_is_configured():
        return RedirectResponse(url="/setup", status_code=302)
    if _get_session_username(request) is None:
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(_logged_in_page("Guide to install", "guide", _guide_page_content(), card_class="card card-wide"))


# ----- Manage settings: server-rendered pages (no JavaScript required) -----

_CORE_HIDDEN_KEYS = frozenset({
    "name", "llm_config_file", "skills_dir", "skills_and_plugins_config_file",
    "use_prompt_manager", "prompts_dir", "prompt_cache_ttl_seconds", "workspace_dir",
    "memory_kb_config_file", "endpoints", "use_workspace_bootstrap", "outbound_markdown_format",
    "file_link_style", "file_static_prefix", "push_notifications", "file_understanding",
})
# Core-only advanced keys (llama_cpp, completion, vision_llm live in llm.yml)
_CORE_ADVANCED_KEYS = ("push_notifications", "file_understanding")
# vision_llm is on the LLM page as a dropdown; only these advanced keys stay on Advanced tab
_LLM_ADVANCED_KEYS = ("llama_cpp", "completion", "vision_llm_host", "vision_llm_port", "vision_image_max_dimension")
_FRIEND_PRESETS_KEYS = ("presets",)
REDACTED_PLACEHOLDER = "***"

SETTINGS_PAGES = [
    ("core", "Core"),
    ("llm", "LLM"),
    ("user", "Users"),
    ("advanced", "Advanced"),
]


def _render_core_form_html(data: Optional[Dict[str, Any]]) -> str:
    """Server-render Core config form so content shows without JavaScript. Never raises."""
    if not data or not isinstance(data, dict):
        return (
            '<form class="settings-form" id="form-core">'
            '<p class="error">No config data. Create core.yml in config dir.</p>'
            '<button type="submit" class="btn btn-block">Save</button>'
            '<div id="msg-core" class="settings-msg" style="display:none;"></div></form>'
        )
    out = ['<form class="settings-form" id="form-core">']
    for key, val in data.items():
        if key in _CORE_HIDDEN_KEYS:
            continue
        is_redacted = val == REDACTED_PLACEHOLDER
        esc = html_module.escape
        if key == "mode":
            mode_val = "dev" if (val == REDACTED_PLACEHOLDER or val is None) else str(val).lower()
            sel_dev = " selected" if mode_val == "dev" else ""
            sel_prod = " selected" if mode_val == "production" else ""
            out.append(
                '<div class="form-group"><label>mode</label><select name="mode">'
                f'<option value="dev"{sel_dev}>dev (debug log)</option>'
                f'<option value="production"{sel_prod}>production (production log)</option></select>'
                '<p class="form-hint">dev: debug log file; production: production log file, filtered.</p></div>'
            )
            continue
        if key == "silent":
            silent_val = val is True or str(val).lower() == "true"
            out.append(
                '<div class="form-group"><label>silent</label><select name="silent">'
                f'<option value="false"{"" if silent_val else " selected"}>false (verbose console)</option>'
                f'<option value="true"{" selected" if silent_val else ""}>true (less console noise)</option></select></div>'
            )
            continue
        if isinstance(val, dict) and val and not isinstance(val, list):
            body = "" if is_redacted else esc(json.dumps(val, indent=2))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="6" data-json="1" placeholder="•••">{body}</textarea></div>')
        elif isinstance(val, list):
            body = "" if is_redacted else esc(json.dumps(val, indent=2))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="6" data-json="1" placeholder="•••">{body}</textarea></div>')
        else:
            v = "" if is_redacted else esc(str(val) if val is not None else "")
            out.append(f'<div class="form-group"><label>{esc(key)}</label><input type="text" name="{esc(key)}" value="{v}" placeholder="•••"></div>')
    out.append('<button type="submit" class="btn btn-block">Save</button></form>')
    return "".join(out)


def _render_generic_form(config_name: str, data: Optional[Dict[str, Any]]) -> str:
    """Server-render a generic config form (llm, memory_kb, skills_and_plugins, user). Never raises."""
    if not data or not isinstance(data, dict):
        return (
            f'<form method="post" action="/settings/{config_name}" class="settings-form">'
            '<p class="error">No config data.</p>'
            '<button type="submit" class="btn btn-block">Save</button></form>'
        )
    esc = html_module.escape
    out = [f'<form method="post" action="/settings/{config_name}" class="settings-form">']
    for key, val in data.items():
        is_redacted = val == REDACTED_PLACEHOLDER
        if isinstance(val, dict) and not isinstance(val, list):
            body = "" if is_redacted else esc(json.dumps(val, indent=2))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="6" placeholder="•••">{body}</textarea></div>')
        elif isinstance(val, list):
            body = "" if is_redacted else esc(json.dumps(val, indent=2))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="6" placeholder="•••">{body}</textarea></div>')
        else:
            v = "" if is_redacted else esc(str(val) if val is not None else "")
            out.append(f'<div class="form-group"><label>{esc(key)}</label><input type="text" name="{esc(key)}" value="{v}" placeholder="•••"></div>')
    out.append('<button type="submit" class="btn btn-block">Save</button></form>')
    return "".join(out)


def _get_portal_users_list():
    """Return list of user dicts (id, name, username, type, ...). Use Util() when available else config. Never raises."""
    try:
        from base.util import Util
        users = Util().get_users() or []
        return [
            {
                "id": getattr(u, "id", None) or getattr(u, "name", ""),
                "name": getattr(u, "name", ""),
                "type": str(getattr(u, "type", None) or "normal").strip().lower() or "normal",
                "username": getattr(u, "username", None),
                "email": list(getattr(u, "email", None) or []),
                "im": list(getattr(u, "im", None) or []),
                "phone": list(getattr(u, "phone", None) or []),
            }
            for u in users if getattr(u, "name", None)
        ]
    except Exception:
        data = config_api.load_config_for_api("user")
        users = (data.get("users") or []) if isinstance(data, dict) else []
        return [u for u in users if isinstance(u, dict) and (u.get("name") or u.get("id"))]


def _get_portal_friend_presets():
    """Return list of {id, name} for presets (HomeClaw excluded). Never raises."""
    try:
        from base.friend_presets import load_friend_presets
        config_path = str(portal_config.get_config_dir() / "friend_presets.yml")
        presets = load_friend_presets(config_path) or {}
        out = []
        for pid in (presets.keys() if isinstance(presets, dict) else []):
            if not pid or str(pid).strip().lower() == "homeclaw":
                continue
            pid_str = str(pid).strip()
            name = pid_str[0].upper() + pid_str[1:] if len(pid_str) > 1 else pid_str.upper()
            out.append({"id": pid_str, "name": name})
        return out
    except Exception:
        return []


def _render_user_list_and_actions(users: list) -> str:
    """HTML: Create user button + list of users with Edit link. HomeClaw is always added server-side."""
    esc = html_module.escape
    out = ['<p><a href="/settings/user/create" class="btn" style="display:inline-block;width:auto;padding:0.75rem 1.25rem;text-decoration:none;">Create user</a></p>']
    if not users:
        out.append("<p class=\"subtitle\">No users yet. Create one above.</p>")
        return "".join(out)
    out.append("<ul style=\"list-style:none;padding:0;margin:0.75rem 0;\">")
    for u in users:
        if not isinstance(u, dict):
            continue
        name = (u.get("name") or u.get("id") or "?").strip() or "?"
        uname = (u.get("username") or "").strip()
        typ = (u.get("type") or "normal").strip().lower()
        edit_url = "/settings/user/" + quote(str(name), safe="") + "/edit"
        delete_url = "/settings/user/" + quote(str(name), safe="") + "/delete"
        out.append(
            f'<li style="padding:0.5rem 0;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;">'
            f'<span>{esc(name)}</span>'
            f'<span style="color:#64748b;font-size:0.875rem;">{esc(uname or "—")} · {esc(typ)}</span>'
            f'<a href="{edit_url}" class="btn btn-sm" style="margin-left:auto;">Edit</a>'
            f'<form method="post" action="{delete_url}" style="display:inline;" onsubmit="return confirm(\'Delete this user? This cannot be undone.\');">'
            f'<button type="submit" class="btn btn-sm" style="background:#dc2626;color:#fff;border:none;">Delete</button></form>'
            f'</li>'
        )
    out.append("</ul>")
    return "".join(out)


def _render_user_create_form(presets: list, saved: bool = False, error: bool = False) -> str:
    """Form: name, username, optional password, type, email/im/phone (optional), multi-select AI friend presets. HomeClaw not in list; always added."""
    esc = html_module.escape
    msg = ""
    if saved:
        msg = '<p class="settings-msg ok">User created.</p>'
    if error:
        msg = '<p class="settings-msg err">Create failed. Check name and try again.</p>'
    preset_checks = "".join(
        f'<label style="display:block;margin:0.25rem 0;"><input type="checkbox" name="friend_preset_names" value="{esc(p["id"])}"> {esc(p["name"])}</label>'
        for p in (presets or []) if isinstance(p, dict) and p.get("id")
    )
    return f"""
  <h1 class="title">Create user</h1>
  <p class="subtitle">HomeClaw is always added as the first AI friend. Optionally add more from presets below.</p>
  {msg}
  <form method="post" action="/settings/user/create" class="settings-form">
    <div class="form-group">
      <label for="name">Name *</label>
      <input type="text" id="name" name="name" required placeholder="Display name">
    </div>
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" placeholder="Login username (defaults to name)">
    </div>
    <div class="form-group">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" placeholder="Optional; default 'changeme'">
    </div>
    <div class="form-group">
      <label for="type">Type</label>
      <select id="type" name="type">
        <option value="normal">normal</option>
        <option value="companion">companion</option>
      </select>
    </div>
    <div class="form-group">
      <label>Email (one per line, optional)</label>
      <textarea name="email" rows="2" placeholder="email@example.com"></textarea>
    </div>
    <div class="form-group">
      <label>IM (one per line, optional)</label>
      <textarea name="im" rows="2" placeholder="e.g. telegram id"></textarea>
    </div>
    <div class="form-group">
      <label>Phone (one per line, optional)</label>
      <textarea name="phone" rows="2" placeholder="+1234567890"></textarea>
    </div>
    <div class="form-group">
      <label>AI friends (presets)</label>
      <p class="form-hint">Select presets to add. HomeClaw is always included.</p>
      {preset_checks if preset_checks else "<p>No presets in friend_presets.yml.</p>"}
    </div>
    <button type="submit" class="btn btn-block">Create user</button>
    <p style="margin-top:1rem;"><a href="/settings/user">← Back to Users</a></p>
  </form>
"""


def _render_user_edit_form(user_d: Dict[str, Any], presets: list, saved: bool = False, error: bool = False, reset_ok: bool = False, reset_err: Optional[str] = None) -> str:
    """Form: same fields as create (pre-filled) + optional preset multi-select to replace AI friends, and Reset password."""
    esc = html_module.escape
    if not isinstance(user_d, dict):
        user_d = {}
    name = (user_d.get("name") or user_d.get("id") or "").strip() or "?"
    username = (user_d.get("username") or "").strip()
    typ = (user_d.get("type") or "normal").strip().lower()
    email = user_d.get("email") or []
    im = user_d.get("im") or []
    phone = user_d.get("phone") or []
    if isinstance(email, list):
        email_txt = "\n".join(str(x) for x in email if x)
    else:
        email_txt = str(email or "")
    if isinstance(im, list):
        im_txt = "\n".join(str(x) for x in im if x)
    else:
        im_txt = str(im or "")
    if isinstance(phone, list):
        phone_txt = "\n".join(str(x) for x in phone if x)
    else:
        phone_txt = str(phone or "")
    msg = ""
    if saved:
        msg = '<p class="settings-msg ok">User updated.</p>'
    if error:
        msg = '<p class="settings-msg err">Update failed.</p>'
    if reset_ok:
        msg += '<p class="settings-msg ok">Password reset.</p>'
    if reset_err:
        msg += f'<p class="settings-msg err">{esc(reset_err)}</p>'
    selected_preset_ids = set()
    for f in (user_d.get("friends") or []):
        if isinstance(f, dict) and f.get("preset"):
            selected_preset_ids.add(str(f.get("preset", "")).strip().lower())
    preset_checks = "".join(
        f'<label style="display:block;margin:0.25rem 0;"><input type="checkbox" name="friend_preset_names" value="{esc(p["id"])}"{" checked" if (p.get("id") or "").strip().lower() in selected_preset_ids else ""}> {esc(p["name"])}</label>'
        for p in (presets or []) if isinstance(p, dict) and p.get("id")
    )
    edit_action = esc("/settings/user/" + quote(name, safe="") + "/edit")
    reset_action = esc("/settings/user/" + quote(name, safe="") + "/reset-password")
    return f"""
  <h1 class="title">Edit user</h1>
  <p class="subtitle">{esc(name)}</p>
  {msg}
  <form method="post" action="{edit_action}" class="settings-form">
    <div class="form-group">
      <label for="name">Name *</label>
      <input type="text" id="name" name="name" required value="{esc(name)}">
    </div>
    <div class="form-group">
      <label for="username">Username</label>
      <input type="text" id="username" name="username" value="{esc(username)}">
    </div>
    <div class="form-group">
      <label for="type">Type</label>
      <select id="type" name="type">
        <option value="normal"{" selected" if typ == "normal" else ""}>normal</option>
        <option value="companion"{" selected" if typ == "companion" else ""}>companion</option>
      </select>
    </div>
    <div class="form-group">
      <label>Email (one per line)</label>
      <textarea name="email" rows="2">{esc(email_txt)}</textarea>
    </div>
    <div class="form-group">
      <label>IM (one per line)</label>
      <textarea name="im" rows="2">{esc(im_txt)}</textarea>
    </div>
    <div class="form-group">
      <label>Phone (one per line)</label>
      <textarea name="phone" rows="2">{esc(phone_txt)}</textarea>
    </div>
    <div class="form-group">
      <label>Replace AI friends by presets (optional)</label>
      <p class="form-hint">Check presets to set; HomeClaw is always kept.</p>
      {preset_checks if preset_checks else "<p>No presets.</p>"}
    </div>
    <button type="submit" class="btn btn-block">Save</button>
  </form>
  <h3 class="form-section-title">Reset password</h3>
  <form method="post" action="{reset_action}" class="settings-form" style="margin-top:0.5rem;">
    <div class="form-group">
      <label for="new_password">New password</label>
      <input type="password" id="new_password" name="password" placeholder="New password">
    </div>
    <button type="submit" class="btn btn-block">Reset password</button>
  </form>
  <p style="margin-top:1.5rem;"><a href="/settings/user">← Back to Users</a></p>
"""


def _render_user_form(data: Optional[Dict[str, Any]]) -> str:
    """Server-render User tab: list + Create/Edit links, then user picker and JSON editor."""
    esc = html_module.escape
    if not data:
        return (
            _render_user_list_and_actions(_get_portal_users_list())
            + '<form method="post" action="/settings/user" class="settings-form">'
            '<p class="error">No user config data.</p>'
            '<button type="submit" class="btn btn-block">Save</button></form>'
        )
    users_for_list = _get_portal_users_list()
    out = [_render_user_list_and_actions(users_for_list)]
    users = data.get("users")
    if not isinstance(users, list):
        users = []
    users_json = json.dumps(users, indent=2)

    out.append('<form method="post" action="/settings/user" class="settings-form" id="user-form">')
    out.append('<div class="form-group"><label>User</label><select id="user-select">')
    out.append('<option value="">—</option>')
    for i, u in enumerate(users):
        if not isinstance(u, dict):
            continue
        label = esc(u.get("name") or u.get("id") or u.get("username") or f"User {i}")
        out.append(f'<option value="{i}">{label}</option>')
    out.append('</select>')
    out.append('<div id="user-selected" class="llm-selected-box" style="display:none;"><pre id="user-json-preview" class="llm-json-preview"></pre></div>')
    out.append('<div class="llm-btn-row"><button type="button" class="btn btn-sm" id="user-add">Add</button><button type="button" class="btn btn-sm" id="user-remove">Remove</button></div>')
    out.append(f'<textarea name="users" id="user-json" rows="1" style="display:none;">{esc(users_json)}</textarea>')
    out.append('<button type="submit" class="btn btn-block">Save</button></form>')

    out.append('''
<div id="user-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:100;align-items:center;justify-content:center;">
  <div style="background:#fff;border-radius:0.5rem;padding:1.5rem;max-width:28rem;width:90%;max-height:90vh;overflow:auto;">
    <h3 style="margin-top:0;">Add user</h3>
    <div class="form-group"><label>ID</label><input type="text" id="user-modal-id" placeholder="e.g. my_user"></div>
    <div class="form-group"><label>Name</label><input type="text" id="user-modal-name" placeholder="Display name"></div>
    <div class="form-group"><label>Username</label><input type="text" id="user-modal-username" placeholder="Login username"></div>
    <div class="form-group"><label>Password</label><input type="password" id="user-modal-password" placeholder="Password"></div>
    <div style="display:flex;gap:0.5rem;margin-top:1rem;">
      <button type="button" class="btn" id="user-modal-submit">Add</button>
      <button type="button" class="btn" id="user-modal-cancel">Cancel</button>
    </div>
  </div>
</div>''')

    out.append("""
<script>
(function() {
  var userJson = document.getElementById('user-json');
  var userSelect = document.getElementById('user-select');
  var userSelectedBox = document.getElementById('user-selected');
  var userPreview = document.getElementById('user-json-preview');
  var modal = document.getElementById('user-modal');

  function getUsers() { try { return JSON.parse(userJson.value || '[]'); } catch (e) { return []; } }
  function setUsers(arr) { userJson.value = JSON.stringify(arr, null, 2); }

  function updateSelectedUserDisplay() {
    var val = userSelect.value;
    if (val === '' || val === null) {
      userSelectedBox.style.display = 'none';
      return;
    }
    var idx = parseInt(val, 10);
    var users = getUsers();
    if (isNaN(idx) || idx < 0 || idx >= users.length) {
      userSelectedBox.style.display = 'none';
      return;
    }
    userPreview.textContent = JSON.stringify(users[idx], null, 2);
    userSelectedBox.style.display = 'block';
  }

  function refreshDropdown() {
    var users = getUsers();
    var curVal = userSelect.value;
    userSelect.innerHTML = '<option value="">—</option>';
    users.forEach(function(u, i) {
      if (!u || typeof u !== 'object') return;
      var label = (u.name || u.id || u.username || 'User ' + i);
      var opt = document.createElement('option');
      opt.value = i;
      opt.textContent = label;
      if (String(i) === curVal) opt.selected = true;
      userSelect.appendChild(opt);
    });
    updateSelectedUserDisplay();
  }

  function removeSelectedUser() {
    var val = userSelect.value;
    if (val === '' || val === null) return;
    var idx = parseInt(val, 10);
    var users = getUsers();
    if (isNaN(idx) || idx < 0 || idx >= users.length) return;
    var u = users[idx];
    var label = (u && (u.name || u.id || u.username)) || ('User ' + idx);
    if (!confirm('Remove user "' + label + '"? This cannot be undone until you save.')) return;
    users.splice(idx, 1);
    setUsers(users);
    refreshDropdown();
  }

  userSelect.addEventListener('change', updateSelectedUserDisplay);
  document.getElementById('user-remove').onclick = removeSelectedUser;

  document.getElementById('user-add').onclick = function() {
    modal.style.display = 'flex';
  };
  document.getElementById('user-modal-cancel').onclick = function() {
    modal.style.display = 'none';
  };
  document.getElementById('user-modal-submit').onclick = function() {
    var id = (document.getElementById('user-modal-id').value || '').trim();
    var name = (document.getElementById('user-modal-name').value || '').trim() || id;
    var username = (document.getElementById('user-modal-username').value || '').trim();
    var password = (document.getElementById('user-modal-password').value || '').trim();
    if (!id) return;
    var users = getUsers();
    if (users.some(function(u) { return u && (u.id === id || u.username === username); })) return;
    users.push({
      id: id,
      name: name,
      username: username || id,
      password: password,
      email: [],
      im: [],
      phone: [],
      permissions: [],
      friends: []
    });
    setUsers(users);
    refreshDropdown();
    modal.style.display = 'none';
    document.getElementById('user-modal-id').value = '';
    document.getElementById('user-modal-name').value = '';
    document.getElementById('user-modal-username').value = '';
    document.getElementById('user-modal-password').value = '';
  };

  updateSelectedUserDisplay();
})();
</script>""")
    return "".join(out)


def _render_llm_form(data: Optional[Dict[str, Any]]) -> str:
    """Server-render LLM tab: mode/local/cloud/embedding pickers, local/cloud model lists, add-model modal (no hybrid_router). Never raises."""
    esc = html_module.escape
    if not data or not isinstance(data, dict):
        return (
            '<form method="post" action="/settings/llm" class="settings-form">'
            '<p class="error">No LLM config data.</p>'
            '<button type="submit" class="btn btn-block">Save</button></form>'
        )
    local_models = data.get("local_models")
    cloud_models = data.get("cloud_models")
    if not isinstance(local_models, list):
        local_models = []
    if not isinstance(cloud_models, list):
        cloud_models = []

    main_llm_mode = (data.get("main_llm_mode") or "local").strip().lower()
    if main_llm_mode not in ("local", "cloud", "mix"):
        main_llm_mode = "local"
    main_llm_local = data.get("main_llm_local") or ""
    main_llm_cloud = data.get("main_llm_cloud") or ""
    embedding_llm = data.get("embedding_llm") or ""
    vision_llm = data.get("vision_llm") or ""
    main_llm_language = data.get("main_llm_language")
    if isinstance(main_llm_language, list):
        lang_str = ", ".join(str(x) for x in main_llm_language)
    else:
        lang_str = str(main_llm_language or "")

    # Next suggested port for new local / cloud (unique, avoid common ports)
    def next_local_port():
        ports = [m.get("port") for m in local_models if isinstance(m, dict) and isinstance(m.get("port"), int)]
        return max([5100] + ports) + 1

    def next_cloud_port():
        ports = [m.get("port") for m in cloud_models if isinstance(m, dict) and isinstance(m.get("port"), int)]
        return max([5200] + ports) + 1

    local_json = json.dumps(local_models, indent=2)
    cloud_json = json.dumps(cloud_models, indent=2)

    out = ['<form method="post" action="/settings/llm" class="settings-form" id="llm-form">']

    # --- Main mode ---
    out.append('<div class="form-group"><label>Main LLM mode</label><select name="main_llm_mode">')
    for opt, label in [("local", "Local"), ("cloud", "Cloud"), ("mix", "Mix")]:
        sel = ' selected' if main_llm_mode == opt else ''
        out.append(f'<option value="{esc(opt)}"{sel}>{esc(label)}</option>')
    out.append('</select></div>')

    # --- Main local: picker + Add/Remove small buttons + selected model JSON ---
    out.append('<div class="form-group"><label>Main LLM (local)</label><select name="main_llm_local" id="llm-select-local">')
    out.append('<option value="">—</option>')
    for m in local_models:
        if isinstance(m, dict) and m.get("id"):
            ref = "local_models/" + str(m["id"])
            label = esc(m.get("alias") or m["id"])
            sel = ' selected' if main_llm_local == ref else ''
            out.append(f'<option value="{esc(ref)}"{sel}>{label}</option>')
    out.append('</select>')
    out.append('<div id="llm-local-selected" class="llm-selected-box" style="display:none;"><pre id="llm-local-json-preview" class="llm-json-preview"></pre></div>')
    out.append('<div class="llm-btn-row"><button type="button" class="btn btn-sm" id="llm-add-local">Add</button><button type="button" class="btn btn-sm" id="llm-remove-local">Remove</button></div></div>')

    # --- Main cloud: picker + Add/Remove small buttons + selected model JSON ---
    out.append('<div class="form-group"><label>Main LLM (cloud)</label><select name="main_llm_cloud" id="llm-select-cloud">')
    out.append('<option value="">—</option>')
    for m in cloud_models:
        if isinstance(m, dict) and m.get("id"):
            ref = "cloud_models/" + str(m["id"])
            label = esc(m.get("alias") or m["id"])
            sel = ' selected' if main_llm_cloud == ref else ''
            out.append(f'<option value="{esc(ref)}"{sel}>{label}</option>')
    out.append('</select>')
    out.append('<div id="llm-cloud-selected" class="llm-selected-box" style="display:none;"><pre id="llm-cloud-json-preview" class="llm-json-preview"></pre></div>')
    out.append('<div class="llm-btn-row"><button type="button" class="btn btn-sm" id="llm-add-cloud">Add</button><button type="button" class="btn btn-sm" id="llm-remove-cloud">Remove</button></div></div>')

    out.append('<div class="form-group"><label>Embedding LLM</label><select name="embedding_llm">')
    out.append('<option value="">—</option>')
    for m in local_models:
        if isinstance(m, dict) and m.get("id"):
            ref = "local_models/" + str(m["id"])
            label = esc(m.get("alias") or m["id"]) + " (local)"
            sel = ' selected' if embedding_llm == ref else ''
            out.append(f'<option value="{esc(ref)}"{sel}>{label}</option>')
    for m in cloud_models:
        if isinstance(m, dict) and m.get("id"):
            ref = "cloud_models/" + str(m["id"])
            label = esc(m.get("alias") or m["id"]) + " (cloud)"
            sel = ' selected' if embedding_llm == ref else ''
            out.append(f'<option value="{esc(ref)}"{sel}>{label}</option>')
    out.append('</select></div>')

    # Vision sidecar: optional model for image description when main model has no vision. Empty = disabled.
    out.append('<div class="form-group"><label>Vision LLM (sidecar)</label><select name="vision_llm">')
    out.append('<option value="">— (disabled)</option>')
    for m in local_models:
        if isinstance(m, dict) and m.get("id"):
            ref = "local_models/" + str(m["id"])
            label = esc(m.get("alias") or m["id"]) + " (local)"
            sel = ' selected' if vision_llm == ref else ''
            out.append(f'<option value="{esc(ref)}"{sel}>{label}</option>')
    for m in cloud_models:
        if isinstance(m, dict) and m.get("id"):
            ref = "cloud_models/" + str(m["id"])
            label = esc(m.get("alias") or m["id"]) + " (cloud)"
            sel = ' selected' if vision_llm == ref else ''
            out.append(f'<option value="{esc(ref)}"{sel}>{label}</option>')
    out.append('</select></div>')

    out.append(
        '<div class="form-group"><label>Main LLM language (comma-separated)</label>'
        f'<input type="text" name="main_llm_language" value="{esc(lang_str)}" placeholder="e.g. en, zh"></div>'
    )

    out.append(f'<textarea name="local_models" id="llm-local-json" rows="1" style="display:none;">{esc(local_json)}</textarea>')
    out.append(f'<textarea name="cloud_models" id="llm-cloud-json" rows="1" style="display:none;">{esc(cloud_json)}</textarea>')

    out.append('<button type="submit" class="btn btn-block">Save</button></form>')

    # --- Modal: Add local / Add cloud ---
    next_lp = next_local_port()
    next_cp = next_cloud_port()
    out.append('''
<div id="llm-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:100;align-items:center;justify-content:center;">
  <div style="background:#fff;border-radius:0.5rem;padding:1.5rem;max-width:28rem;width:90%;max-height:90vh;overflow:auto;">
    <div id="llm-modal-local" style="display:none;">
      <h3 style="margin-top:0;">Add local model</h3>
      <div class="form-group"><label>ID</label><input type="text" id="llm-local-id" placeholder="e.g. my-model"></div>
      <div class="form-group"><label>Alias</label><input type="text" id="llm-local-alias" placeholder="Display name"></div>
      <div class="form-group"><label>Path</label><input type="text" id="llm-local-path" placeholder="model.gguf or path"></div>
      <div class="form-group"><label>Type</label><input type="text" id="llm-local-type" value="llama.cpp" placeholder="llama.cpp or ollama"></div>
      <div class="form-group"><label>Capabilities (comma-separated)</label><input type="text" id="llm-local-capabilities" value="Chat" placeholder="Chat, embedding"></div>
      <div class="form-group"><label>Host</label><input type="text" id="llm-local-host" value="127.0.0.1"></div>
      <div class="form-group"><label>Port</label><input type="number" id="llm-local-port" value="''' + str(next_lp) + '''"></div>
      <div style="display:flex;gap:0.5rem;margin-top:1rem;">
        <button type="button" class="btn" id="llm-modal-local-submit">Add</button>
        <button type="button" class="btn" id="llm-modal-cancel">Cancel</button>
      </div>
    </div>
    <div id="llm-modal-cloud" style="display:none;">
      <h3 style="margin-top:0;">Add cloud model</h3>
      <div class="form-group"><label>ID</label><input type="text" id="llm-cloud-id" placeholder="e.g. OpenAI-GPT4o"></div>
      <div class="form-group"><label>Alias</label><input type="text" id="llm-cloud-alias" placeholder="Display name"></div>
      <div class="form-group"><label>Path</label><input type="text" id="llm-cloud-path" placeholder="openai/gpt-4o"></div>
      <div class="form-group"><label>API key</label><input type="password" id="llm-cloud-apikey" placeholder="Optional if using env var"></div>
      <div class="form-group"><label>API key env name</label><input type="text" id="llm-cloud-apikey-name" placeholder="e.g. OPENAI_API_KEY"></div>
      <div class="form-group"><label>Capabilities (comma-separated)</label><input type="text" id="llm-cloud-capabilities" value="Chat" placeholder="Chat, embedding"></div>
      <div class="form-group"><label>Host</label><input type="text" id="llm-cloud-host" value="127.0.0.1"></div>
      <div class="form-group"><label>Port</label><input type="number" id="llm-cloud-port" value="''' + str(next_cp) + '''"></div>
      <div style="display:flex;gap:0.5rem;margin-top:1rem;">
        <button type="button" class="btn" id="llm-modal-cloud-submit">Add</button>
        <button type="button" class="btn" id="llm-modal-cancel2">Cancel</button>
      </div>
    </div>
  </div>
</div>''')

    # --- Script: add/remove, sync dropdowns, show selected model JSON ---
    out.append("""
<script>
(function() {
  var form = document.getElementById('llm-form');
  var localJson = document.getElementById('llm-local-json');
  var cloudJson = document.getElementById('llm-cloud-json');
  var selectLocal = document.getElementById('llm-select-local');
  var selectCloud = document.getElementById('llm-select-cloud');
  var localSelectedBox = document.getElementById('llm-local-selected');
  var cloudSelectedBox = document.getElementById('llm-cloud-selected');
  var localPreview = document.getElementById('llm-local-json-preview');
  var cloudPreview = document.getElementById('llm-cloud-json-preview');
  var modal = document.getElementById('llm-modal');
  var modalLocal = document.getElementById('llm-modal-local');
  var modalCloud = document.getElementById('llm-modal-cloud');

  function getLocal() { try { return JSON.parse(localJson.value || '[]'); } catch (e) { return []; } }
  function getCloud() { try { return JSON.parse(cloudJson.value || '[]'); } catch (e) { return []; } }
  function setLocal(arr) { localJson.value = JSON.stringify(arr, null, 2); }
  function setCloud(arr) { cloudJson.value = JSON.stringify(arr, null, 2); }

  function escapeHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function optionHtml(value, label, selected) { return '<option value="' + escapeHtml(value) + '"' + (selected ? ' selected' : '') + '>' + escapeHtml(label) + '</option>'; }

  function updateSelectedLocalDisplay() {
    var val = selectLocal.value;
    if (!val) {
      localSelectedBox.style.display = 'none';
      return;
    }
    var id = val.indexOf('local_models/') === 0 ? val.slice(13) : val;
    var local = getLocal();
    var model = local.filter(function(m) { return m && m.id === id; })[0];
    if (!model) {
      localSelectedBox.style.display = 'none';
      return;
    }
    localPreview.textContent = JSON.stringify(model, null, 2);
    localSelectedBox.style.display = 'block';
  }
  function updateSelectedCloudDisplay() {
    var val = selectCloud.value;
    if (!val) {
      cloudSelectedBox.style.display = 'none';
      return;
    }
    var id = val.indexOf('cloud_models/') === 0 ? val.slice(13) : val;
    var cloud = getCloud();
    var model = cloud.filter(function(m) { return m && m.id === id; })[0];
    if (!model) {
      cloudSelectedBox.style.display = 'none';
      return;
    }
    cloudPreview.textContent = JSON.stringify(model, null, 2);
    cloudSelectedBox.style.display = 'block';
  }

  function refreshDropdowns() {
    var local = getLocal();
    var cloud = getCloud();
    var mainLocal = form.querySelector('select[name="main_llm_local"]');
    var mainCloud = form.querySelector('select[name="main_llm_cloud"]');
    var embed = form.querySelector('select[name="embedding_llm"]');
    var curMainLocal = mainLocal.value;
    var curMainCloud = mainCloud.value;
    var curEmbed = embed.value;
    mainLocal.innerHTML = '<option value="">—</option>';
    mainCloud.innerHTML = '<option value="">—</option>';
    embed.innerHTML = '<option value="">—</option>';
    local.forEach(function(m) {
      if (m && m.id) {
        var ref = 'local_models/' + m.id;
        mainLocal.innerHTML += optionHtml(ref, m.alias || m.id, ref === curMainLocal);
        embed.innerHTML += optionHtml(ref, (m.alias || m.id) + ' (local)', ref === curEmbed);
      }
    });
    cloud.forEach(function(m) {
      if (m && m.id) {
        var ref = 'cloud_models/' + m.id;
        mainCloud.innerHTML += optionHtml(ref, m.alias || m.id, ref === curMainCloud);
        embed.innerHTML += optionHtml(ref, (m.alias || m.id) + ' (cloud)', ref === curEmbed);
      }
    });
    updateSelectedLocalDisplay();
    updateSelectedCloudDisplay();
  }

  function removeSelectedLocal() {
    var val = selectLocal.value;
    if (!val) return;
    var id = val.indexOf('local_models/') === 0 ? val.slice(13) : val;
    var local = getLocal();
    var model = local.filter(function(m) { return m && m.id === id; })[0];
    var label = model && (model.alias || model.id) ? (model.alias || model.id) : id;
    if (!confirm('Remove local model "' + label + '"? This cannot be undone until you save.')) return;
    var arr = local.filter(function(m) { return m && m.id !== id; });
    setLocal(arr);
    refreshDropdowns();
  }
  function removeSelectedCloud() {
    var val = selectCloud.value;
    if (!val) return;
    var id = val.indexOf('cloud_models/') === 0 ? val.slice(13) : val;
    var cloud = getCloud();
    var model = cloud.filter(function(m) { return m && m.id === id; })[0];
    var label = model && (model.alias || model.id) ? (model.alias || model.id) : id;
    if (!confirm('Remove cloud model "' + label + '"? This cannot be undone until you save.')) return;
    var arr = cloud.filter(function(m) { return m && m.id !== id; });
    setCloud(arr);
    refreshDropdowns();
  }

  selectLocal.addEventListener('change', updateSelectedLocalDisplay);
  selectCloud.addEventListener('change', updateSelectedCloudDisplay);
  document.getElementById('llm-remove-local').onclick = removeSelectedLocal;
  document.getElementById('llm-remove-cloud').onclick = removeSelectedCloud;
  updateSelectedLocalDisplay();
  updateSelectedCloudDisplay();

  document.getElementById('llm-add-local').onclick = function() {
    modalLocal.style.display = 'block';
    modalCloud.style.display = 'none';
    modal.style.display = 'flex';
    document.getElementById('llm-local-port').value = Math.max(5100, getLocal().reduce(function(max, m) { return Math.max(max, (m && m.port) || 0); }, 5099) + 1);
  };
  document.getElementById('llm-add-cloud').onclick = function() {
    modalCloud.style.display = 'block';
    modalLocal.style.display = 'none';
    modal.style.display = 'flex';
    document.getElementById('llm-cloud-port').value = Math.max(5200, getCloud().reduce(function(max, m) { return Math.max(max, (m && m.port) || 0); }, 5199) + 1);
  };

  function closeModal() {
    modal.style.display = 'none';
    modalLocal.style.display = 'none';
    modalCloud.style.display = 'none';
  }
  document.getElementById('llm-modal-cancel').onclick = closeModal;
  document.getElementById('llm-modal-cancel2').onclick = closeModal;

  document.getElementById('llm-modal-local-submit').onclick = function() {
    var id = (document.getElementById('llm-local-id').value || '').trim();
    var alias = (document.getElementById('llm-local-alias').value || '').trim() || id;
    var path = (document.getElementById('llm-local-path').value || '').trim();
    var type = (document.getElementById('llm-local-type').value || '').trim() || 'llama.cpp';
    var capStr = (document.getElementById('llm-local-capabilities').value || 'Chat').trim();
    var host = (document.getElementById('llm-local-host').value || '').trim() || '127.0.0.1';
    var port = parseInt(document.getElementById('llm-local-port').value, 10) || 5100;
    var caps = capStr.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    if (!id) return;
    var arr = getLocal();
    if (arr.some(function(m) { return m && m.id === id; })) return;
    arr.push({ id: id, alias: alias, path: path, type: type, capabilities: caps, host: host, port: port });
    setLocal(arr);
    refreshDropdowns();
    closeModal();
  };
  document.getElementById('llm-modal-cloud-submit').onclick = function() {
    var id = (document.getElementById('llm-cloud-id').value || '').trim();
    var alias = (document.getElementById('llm-cloud-alias').value || '').trim() || id;
    var path = (document.getElementById('llm-cloud-path').value || '').trim();
    var apikey = (document.getElementById('llm-cloud-apikey').value || '').trim();
    var apikeyName = (document.getElementById('llm-cloud-apikey-name').value || '').trim();
    var capStr = (document.getElementById('llm-cloud-capabilities').value || 'Chat').trim();
    var host = (document.getElementById('llm-cloud-host').value || '').trim() || '127.0.0.1';
    var port = parseInt(document.getElementById('llm-cloud-port').value, 10) || 5200;
    var caps = capStr.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    if (!id) return;
    var arr = getCloud();
    if (arr.some(function(m) { return m && m.id === id; })) return;
    var entry = { id: id, alias: alias, path: path, capabilities: caps, host: host, port: port };
    if (apikeyName) entry.api_key_name = apikeyName;
    if (apikey) entry.api_key = apikey;
    arr.push(entry);
    setCloud(arr);
    refreshDropdowns();
    closeModal();
  };
})();
</script>""")

    return "".join(out)


def _render_generic_section(data: Optional[Dict], keys: Optional[tuple], esc, out: list) -> None:
    """Append form groups for the given keys from data (dict/list -> textarea, else input). Never raises."""
    if not data or not isinstance(data, dict):
        return
    key_iter = keys if keys is not None else [k for k in data if data.get(k) is not None]
    for key in key_iter:
        val = data.get(key)
        if val is None:
            continue
        is_redacted = val == REDACTED_PLACEHOLDER
        if isinstance(val, dict) or isinstance(val, list):
            body = "" if is_redacted else esc(json.dumps(val, indent=2))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="4" placeholder="•••">{body}</textarea></div>')
        else:
            v = "" if is_redacted else esc(str(val))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><input type="text" name="{esc(key)}" value="{v}" placeholder="•••"></div>')


def _render_advanced_form(
    data_core: Optional[Dict],
    data_llm: Optional[Dict],
    data_friend: Optional[Dict],
    data_memory_kb: Optional[Dict],
    data_skills_and_plugins: Optional[Dict],
) -> str:
    """Server-render Advanced tab: core advanced, LLM advanced (llm.yml), hybrid_router, friend presets, Memory & KB, Skills & Plugins."""
    esc = html_module.escape
    out = ['<form method="post" action="/settings/advanced" class="settings-form">']
    for key in _CORE_ADVANCED_KEYS:
        val = data_core.get(key) if data_core else None
        if val is None and data_core is not None:
            continue
        if val is not None:
            is_redacted = val == REDACTED_PLACEHOLDER
            if isinstance(val, dict) or isinstance(val, list):
                body = "" if is_redacted else esc(json.dumps(val, indent=2))
                out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="4" placeholder="•••">{body}</textarea></div>')
            else:
                v = "" if is_redacted else esc(str(val))
                out.append(f'<div class="form-group"><label>{esc(key)}</label><input type="text" name="{esc(key)}" value="{v}" placeholder="•••"></div>')
    # LLM advanced keys (llm.yml): llama_cpp, completion, vision_llm
    _llm_data = data_llm if isinstance(data_llm, dict) else {}
    for key in _LLM_ADVANCED_KEYS:
        val = _llm_data.get(key)
        if val is None and _llm_data:
            continue
        if val is not None:
            is_redacted = val == REDACTED_PLACEHOLDER
            if isinstance(val, dict) or isinstance(val, list):
                body = "" if is_redacted else esc(json.dumps(val, indent=2))
                out.append(f'<div class="form-group"><label>{esc(key)} (llm.yml)</label><textarea name="{esc(key)}" rows="4" placeholder="•••">{body}</textarea></div>')
            else:
                v = "" if is_redacted else esc(str(val) if val is not None else "")
                out.append(f'<div class="form-group"><label>{esc(key)} (llm.yml)</label><input type="text" name="{esc(key)}" value="{v}" placeholder="•••"></div>')
    if data_llm and data_llm.get("hybrid_router") is not None:
        out.append('<h3 class="form-section-title">Hybrid router (LLM)</h3>')
        val = data_llm["hybrid_router"]
        is_redacted = val == REDACTED_PLACEHOLDER
        body = "" if is_redacted else esc(json.dumps(val, indent=2) if isinstance(val, (dict, list)) else str(val))
        out.append(f'<div class="form-group"><label>hybrid_router</label><textarea name="hybrid_router" rows="4" placeholder="•••">{body}</textarea></div>')
    out.append('<h3 class="form-section-title">Friend presets</h3>')
    for key in _FRIEND_PRESETS_KEYS:
        val = data_friend.get(key) if data_friend else None
        if val is None and data_friend is not None:
            continue
        if val is not None:
            body = "" if val == REDACTED_PLACEHOLDER else esc(json.dumps(val, indent=2))
            out.append(f'<div class="form-group"><label>{esc(key)}</label><textarea name="{esc(key)}" rows="6" placeholder="•••">{body}</textarea></div>')
    out.append('<h3 class="form-section-title">Memory &amp; KB</h3>')
    _render_generic_section(data_memory_kb, None, esc, out)
    out.append('<h3 class="form-section-title">Skills &amp; Plugins</h3>')
    _render_generic_section(data_skills_and_plugins, None, esc, out)
    out.append('<button type="submit" class="btn btn-block">Save</button></form>')
    return "".join(out)


def _settings_nav_html(current: str) -> str:
    """Sub-nav: inline styles so tabs look like buttons and stay spaced even if CSS is stripped."""
    parts = []
    for page, label in SETTINGS_PAGES:
        is_active = page == current
        if is_active:
            link_style = (
                "display:inline-block;padding:0.75rem 1.5rem;margin:0 0.5rem 0.5rem 0;"
                "font-size:0.9375rem;font-weight:600;color:#fff;text-decoration:none;"
                "border-radius:0.5rem;border:1px solid #b45309;"
                "background:linear-gradient(135deg,#f59e0b 0%,#d97706 100%);"
            )
        else:
            link_style = (
                "display:inline-block;padding:0.75rem 1.5rem;margin:0 0.5rem 0.5rem 0;"
                "font-size:0.9375rem;font-weight:600;color:#475569;text-decoration:none;"
                "border-radius:0.5rem;border:1px solid #cbd5e1;background:#f1f5f9;"
            )
        parts.append(
            f'<a href="/settings/{page}" class="settings-tab-link{" active" if is_active else ""}" style="{link_style}">'
            f'{html_module.escape(label)}</a>'
        )
    return '<nav class="settings-subnav" style="display:block;margin:1.25rem 0 1.75rem;padding:0;">' + "".join(parts) + "</nav>"


def _settings_page_html(page: str, form_html: str, saved: bool = False, error: bool = False) -> str:
    """Full HTML for one settings page: title, subtitle, sub-nav, form, optional message."""
    msg = ""
    if saved:
        msg = '<p class="settings-msg ok">Saved.</p>'
    if error:
        msg = '<p class="settings-msg err">Save failed. Check the form and try again.</p>'
    nav = _settings_nav_html(page)
    return f"""
  <h1 class="title">Manage settings</h1>
  <p class="subtitle" style="margin-bottom:0;">Edit config files. Sensitive values show as ••• and are not changed on save. Core does not need to be running.</p>
  {nav}
  <div class="settings-form-wrap">{msg}{form_html}</div>
"""


def _form_body_from_data(form_data: dict, original: Optional[Dict], keys: Optional[tuple] = None) -> Dict[str, Any]:
    """Build merge body from form data with types from original config. Skip empty and •••. Never raises."""
    body = {}
    if form_data is None or not isinstance(form_data, dict):
        form_data = {}
    keys_iter = list(keys) if keys is not None else list(form_data.keys())
    for key in keys_iter:
        if key not in form_data:
            continue
        val = form_data.get(key)
        val = (val if isinstance(val, str) else (str(val) if val is not None else ""))
        val = val.strip()
        if val == "" or val == "•••":
            continue
        orig_val = original.get(key) if original else None
        if isinstance(orig_val, bool):
            body[key] = val.lower() in ("true", "1", "yes")
        elif isinstance(orig_val, int):
            try:
                body[key] = int(val)
            except ValueError:
                body[key] = val
        elif isinstance(orig_val, (dict, list)) or (orig_val is None and val.strip().startswith(("[", "{"))):
            try:
                body[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                body[key] = val
        else:
            body[key] = val
    return body


from portal.settings_routes import router as settings_router
app.include_router(settings_router, prefix="/settings")


# ----- Config API: users CRUD and friend-presets (then GET/PATCH by name) -----

@app.get("/api/config/users")
def api_config_users_list(request: Request):
    """Return { users: [...] } (redacted). For Portal UI and API parity with Core."""
    data = config_api.load_config_for_api("user")
    if data is None:
        return JSONResponse(content={"users": []})
    return JSONResponse(content=data)


@app.get("/api/config/friend-presets")
def api_config_friend_presets_list(request: Request):
    """Return { presets: [ { id, name }, ... ] } for multi-select. HomeClaw excluded (always added server-side)."""
    try:
        from base.friend_presets import load_friend_presets
        config_path = str(portal_config.get_config_dir() / "friend_presets.yml")
        presets = load_friend_presets(config_path) or {}
        out = []
        for pid, _ in (presets.items() if isinstance(presets, dict) else []):
            if not pid or not isinstance(pid, str):
                continue
            pid_str = str(pid).strip()
            if not pid_str or pid_str.lower() == "homeclaw":
                continue
            name = pid_str[0].upper() + pid_str[1:] if len(pid_str) > 1 else pid_str.upper()
            out.append({"id": pid_str, "name": name})
        return JSONResponse(content={"presets": out})
    except Exception as e:
        _log.debug("friend-presets list failed: %s", e)
        return JSONResponse(content={"presets": []})


@app.post("/api/config/users")
async def api_config_users_post(request: Request):
    """Add user. Body: name, username?, password?, type?, email?, im?, phone?, friend_preset_names?."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body"})
    ok, err = config_api.add_user(body if isinstance(body, dict) else {})
    if not ok:
        return JSONResponse(status_code=400 if err and "required" in (err or "").lower() else 500, content={"detail": err or "Failed to add user"})
    return JSONResponse(content={"result": "ok", "name": (body.get("name") or "").strip()})


@app.patch("/api/config/users/{user_name}")
async def api_config_users_patch(request: Request, user_name: str):
    """Update user by name. Body: name?, id?, username?, password?, type?, email?, im?, phone?, friend_preset_names?, reset_password?."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body"})
    ok, err = config_api.update_user(user_name, body if isinstance(body, dict) else {})
    if not ok:
        if err and "not found" in (err or "").lower():
            return JSONResponse(status_code=404, content={"detail": err})
        return JSONResponse(status_code=400 if err and "required" in (err or "").lower() else 500, content={"detail": err or "Update failed"})
    return JSONResponse(content={"result": "ok", "name": (body.get("name") or user_name).strip()})


@app.delete("/api/config/users/{user_name}")
def api_config_users_delete(request: Request, user_name: str):
    """Remove user by name."""
    ok, err = config_api.delete_user(user_name)
    if not ok:
        if err and "not found" in (err or "").lower():
            return JSONResponse(status_code=404, content={"detail": err})
        return JSONResponse(status_code=500, content={"detail": err or "Delete failed"})
    return JSONResponse(content={"result": "ok", "name": user_name})


@app.post("/api/config/users/{user_name}/reset-password")
async def api_config_users_reset_password(request: Request, user_name: str):
    """Set new password for user. Body: { \"password\": \"...\" }. Admin reset."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body"})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"detail": "JSON object required"})
    new_password = (body.get("password") or "").strip() if isinstance(body.get("password"), str) else ""
    ok, err = config_api.update_user_password(user_name, new_password)
    if not ok:
        if err and "not found" in (err or "").lower():
            return JSONResponse(status_code=404, content={"detail": err})
        return JSONResponse(status_code=400 if err and "required" in (err or "").lower() else 500, content={"detail": err})
    return JSONResponse(content={"result": "ok", "name": user_name})


# ----- Config API (GET/PATCH by config name; auth by middleware) -----

@app.get("/api/config/{name}")
def api_config_get(request: Request, name: str):
    """Return config (redacted) for core, llm, memory_kb, skills_and_plugins, user, friend_presets. Auth: session or X-Portal-Secret (middleware)."""
    if name not in config_backup.CONFIG_NAMES:
        return JSONResponse(status_code=404, content={"detail": "Unknown config name"})
    data = config_api.load_config_for_api(name)
    if data is None:
        return JSONResponse(status_code=404, content={"detail": "Config not found or could not be loaded"})
    return JSONResponse(content=data)


@app.patch("/api/config/{name}")
async def api_config_patch(request: Request, name: str):
    """Merge body into config (whitelisted keys only); backup previous before write. Auth: session or X-Portal-Secret (middleware)."""
    if name not in config_backup.CONFIG_NAMES:
        return JSONResponse(status_code=404, content={"detail": "Unknown config name"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid JSON body"})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"detail": "Body must be a JSON object"})
    ok = config_api.update_config(name, body)
    if not ok:
        return JSONResponse(status_code=500, content={"detail": "Update failed"})
    return JSONResponse(content={"result": "ok"})
