"""
Portal FastAPI application. Step 1: health/ready/status. Step 3: admin auth, /setup, /login, session, /dashboard.
Never crash: unhandled exceptions are caught by the global exception handler and return 500.
"""
import html
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from portal.config import get_config_dir
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
    .form-group input:focus {
      outline: none;
      border-color: #f59e0b;
      box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.2);
    }
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
    .error { font-size: 0.875rem; color: #dc2626; margin-top: 1rem; text-align: center; }
    .dashboard-welcome { font-size: 1rem; color: #475569; margin: 0 0 1.5rem; }
    .dashboard-meta { font-size: 0.875rem; color: #94a3b8; margin-top: 1.5rem; }
  </style>
"""

def _portal_page(title: str, body: str, show_logo: bool = True) -> str:
    logo = '<img src="/static/img/homeclaw-logo.png" alt="HomeClaw" class="logo">' if show_logo else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} — HomeClaw Portal</title>{_PORTAL_STYLES}</head>
<body><div class="card">{logo}{body}</div></body></html>"""


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


@app.get("/setup", response_class=HTMLResponse)
def setup_get(request: Request):
    """Show setup form if admin not configured; else redirect to login."""
    if auth.admin_is_configured():
        return RedirectResponse(url="/login", status_code=302)
    return HTMLResponse(_SETUP_HTML)


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


# ----- Dashboard (protected) -----

def _dashboard_html(username: str) -> str:
    safe_user = html.escape(username)
    return _portal_page("Dashboard", f"""
  <h1 class="title">Dashboard</h1>
  <p class="dashboard-welcome">You’re logged in as <strong>{safe_user}</strong>.</p>
  <p class="subtitle">Configuration and settings will be available here in a later update.</p>
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


# ----- Config API (GET/PATCH; require session) -----

def _require_session(request: Request):
    """Return (None, None) if session valid; else (401_response, None)."""
    if _get_session_username(request) is None:
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"}), None
    return None, True


@app.get("/api/config/{name}")
def api_config_get(request: Request, name: str):
    """Return config (redacted) for core, llm, memory_kb, skills_and_plugins, user, friend_presets."""
    err, _ = _require_session(request)
    if err is not None:
        return err
    if name not in config_backup.CONFIG_NAMES:
        return JSONResponse(status_code=404, content={"detail": "Unknown config name"})
    data = config_api.load_config_for_api(name)
    if data is None:
        return JSONResponse(status_code=404, content={"detail": "Config not found or could not be loaded"})
    return JSONResponse(content=data)


@app.patch("/api/config/{name}")
async def api_config_patch(request: Request, name: str):
    """Merge body into config (whitelisted keys only); backup previous before write."""
    err, _ = _require_session(request)
    if err is not None:
        return err
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
