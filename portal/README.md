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
- **Port:** `18472` (override: `PORTAL_PORT`)

## Workflow: reaching Portal when only Core (9000) is exposed

You expose **only** the machine’s **port 9000** (Core) to the internet — e.g. via Cloudflare Tunnel, reverse proxy, or port forward — and use your domain (e.g. `https://homeclaw.gpt4people.online`) to reach Core.

**You do not expose Portal (18472).** Portal listens only on `127.0.0.1:18472` on the same machine. Nothing on the internet talks to port 18472.

**How you reach the Portal UI (Core setting):**

1. Use the **same** base URL and port as Core, with path **`/portal-ui`**:
   - From Companion: the app already uses your Core URL and loads `.../portal-ui` (e.g. `https://homeclaw.gpt4people.online/portal-ui`).
   - From a browser: open `https://your-domain/portal-ui` (same host as Core; if Core is on 443, no port; if Core is on 9000 and you proxy to it, still use the public URL + `/portal-ui`).

2. **Request path:**  
   **Client (Companion/browser)** → **Cloudflare** (or your proxy) → **Core :9000** → Core proxies the request to **Portal at `http://127.0.0.1:18472`** → Portal responds → Core sends the response back → client.

3. So there is **one public entry point**: your domain (Core). Portal is only reached **by Core on localhost**. No need to open or expose port 18472.

**If you get 502 (from Cloudflare or the client):**  
That 502 is almost always **Core returning 502** because Core could not connect to Portal (e.g. Portal not running or wrong `portal_url`). Cloudflare then forwards that response. Fix: on the **same machine** where Core runs, start Portal (`python -m main portal`) and set `portal_url: "http://127.0.0.1:18472"` in `config/core.yml`.

## Companion gets 502 when opening "Core setting"

Companion loads Core’s `/portal-ui`; Core then **proxies** that request to the Portal at `portal_url`. A 502 means Core could not reach the Portal.

**Portal must run on the same machine as Core.** `portal_url` is usually `http://127.0.0.1:18472` — that is Core’s **localhost**. If Core runs on a server (e.g. VPS or home machine behind Cloudflare), start Portal on that **same** server.

**Checklist:**

1. **Start Portal** on the host where Core runs:
   ```bash
   python -m main portal
   ```
   Leave it running (same terminal or run in background / as a service).

2. **Confirm Portal is up** on that host:
   ```bash
   curl http://127.0.0.1:18472/ready
   ```
   Expect: `ok` and status 200.

3. **Confirm `config/core.yml`** has `portal_url: "http://127.0.0.1:18472"` (or the port you use). Restart Core after changing it.

4. **If you use a different port** for Portal (e.g. `PORTAL_PORT=9001`), set `portal_url: "http://127.0.0.1:9001"` in core.yml.

5. **502 response body** from Core includes `detail` and sometimes `portal_url` — e.g. "Cannot reach Portal; is it running?" means Core tried `portal_url` and got connection refused (Portal not listening).

6. **Diagnostic:** On the machine where Core runs, open or curl Core’s proxy-status (no auth):
   ```bash
   curl http://127.0.0.1:9000/api/portal/proxy-status
   ```
   Response: `portal_url`, `portal_reachable` (true/false), and `detail`. If `portal_reachable` is false, Core cannot reach Portal at that URL — fix the port or start Portal.

## portal_secret (Core → Portal API auth)

When Core proxies requests to Portal (`/portal-ui`, `/api/config/*`), it can send a shared secret so Portal accepts only requests from Core.

**1. Choose one secret** (e.g. 32 random characters). Use the same value in both places below.

**2. Core** — set in `config/core.yml` or env:

```yaml
portal_secret: "your-secret-here"
```

Or: `PORTAL_SECRET=your-secret-here`

**3. Portal** — set in one of:

- **Env:** `PORTAL_SECRET=your-secret-here`
- **File:** `config/portal_secret.txt` — first line = the secret (no quotes). File is in `.gitignore`.

Core sends the secret in the `X-Portal-Secret` header on every proxied request. Portal’s middleware allows `/api/*` if the request has a valid session cookie **or** a matching `X-Portal-Secret` (or `Authorization: Bearer <secret>`). If you leave `portal_secret` empty on both sides, Portal still requires a session for `/api/*` (except GET status/guide); the secret is optional and adds protection when Core and Portal are on the same host.

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

## Phase 2.1 (Manage settings UI)

- **GET /dashboard** — Logged-in layout with nav: Dashboard | Manage settings | Log out. Link to **Manage settings**.
- **GET /settings** — Manage settings page: tabs (Core, LLM, Memory & KB, Skills & Plugins, Users, Friend presets). Each tab loads config via GET /api/config/{name}, shows a form (scalars as inputs, objects/arrays as JSON textareas). Redacted values show as ••• and are not sent on save. **Save** sends only changed fields via PATCH. Requires session.
- **GET /logout** — Clears session cookie and redirects to /login.

All route handlers use a global exception handler so the server never crashes.

## Tests

```bash
pytest tests/test_portal_step1.py tests/test_portal_yaml_config.py tests/test_portal_config_backup.py tests/test_portal_auth.py tests/test_portal_session.py tests/test_portal_step3_routes.py tests/test_portal_config_api.py -v
```
