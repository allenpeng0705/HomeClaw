# HomeClaw Portal

Local web server for configuration, onboarding, and launching Core and Channels. See [CorePortalDesign.md](../docs_design/CorePortalDesign.md) and [CorePortalImplementationPlan.md](../docs_design/CorePortalImplementationPlan.md).

## Run

From project root with venv activated:

```bash
python -m main portal
```

The default browser opens automatically when the server is ready. To disable: `python -m main portal --no-open-browser`.

Or run the app directly (same venv, no auto-open):

```bash
python -c "import uvicorn; from portal.app import app; from portal.config import get_host, get_port; uvicorn.run(app, host=get_host(), port=get_port())"
```

- **Host:** `127.0.0.1` (override: `PORTAL_HOST`)
- **Port:** `8000` (override: `PORTAL_PORT`)

## Step 1

- `GET /ready` — readiness
- `GET /api/portal/status` — status JSON (config dir path and existence)

## Step 2

- **`portal/yaml_config.py`** — Comment-preserving YAML for llm, memory_kb, skills_and_plugins, friend_presets: `load_yml_preserving(path)`, `update_yml_preserving(path, updates, whitelist=None)`. Whitelists per file.

## Config system copy and previous backup

- **`portal/config_backup.py`** — System copy (`config/system/<name>.yml`) and single previous backup (`config/<name>.yml.previous`). User can **restore to system** or **revert to previous**. Before any config PATCH, call `prepare_for_update(name)` so current is backed up to `.previous`; system copy is created from current on first use if missing. See [PortalConfigSystemAndPreviousBackup.md](../docs_design/PortalConfigSystemAndPreviousBackup.md).

## Step 3 (admin auth)

- **`GET /`** — Redirect: no admin → `/setup`; not logged in → `/login`; else → `/dashboard`.
- **`GET/POST /setup`** — First-time admin account creation (username + password). Stored in `config/portal_admin.yml` (ignored by git). Env override for dev: `PORTAL_ADMIN_USERNAME`, `PORTAL_ADMIN_PASSWORD`.
- **`GET/POST /login`** — Login form; on success sets `portal_session` cookie (signed, 24h). Secret: `PORTAL_SESSION_SECRET`.
- **`GET /dashboard`** — Protected; minimal dashboard when session valid.
- **`portal/auth.py`** — `admin_is_configured()`, `verify_portal_admin()`, `set_admin()`. **`portal/session.py`** — `create_session_value()`, `verify_session_value()`.

## Step 1.4 (config API)

- **GET /api/config/{name}** — Return config (redacted). `name`: core, llm, memory_kb, skills_and_plugins, user, friend_presets. Requires session.
- **PATCH /api/config/{name}** — Merge JSON body (whitelisted keys only); calls `prepare_for_update(name)` before write. Requires session.
- **`portal/config_api.py`** — `load_config()`, `load_config_for_api()`, `update_config()`; redaction for core (auth_api_key, pinggy.token), llm (api_key), user (password).

All route handlers use a global exception handler so the server never crashes.

## Tests

```bash
pytest tests/test_portal_step1.py tests/test_portal_yaml_config.py tests/test_portal_config_backup.py tests/test_portal_auth.py tests/test_portal_session.py tests/test_portal_step3_routes.py tests/test_portal_config_api.py -v
```
