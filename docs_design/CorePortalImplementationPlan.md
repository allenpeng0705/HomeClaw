# Core Portal — Detailed Implementation Plan

This plan breaks down the [CorePortalDesign.md](CorePortalDesign.md) into actionable phases and steps for implementation and review. Order and dependencies are explicit so work can be done incrementally.

---

## Overview

| Phase | Name | Delivers |
|-------|------|----------|
| **1** | Foundation: YAML layer + Portal server + admin auth | Portal runs locally; admin login; safe YAML edit for all six files |
| **2** | Portal Web UI (four areas) | Manage settings, Guide to install, Start Core, Start channel (HTML5, mobile-friendly) |
| **3** | Portal REST API + Core→Portal secret | Portal exposes API; Core can call Portal with secret |
| **4** | Core proxy to Portal | Core forwards config + `/portal-ui` to Portal when `portal_url` set |
| **5** | Core admin auth for Companion | POST /api/portal/auth (username+password); protect portal-ui and config proxy |
| **6** | Companion: Core setting + WebView | Entry point → login → WebView to /portal-ui |

---

## Phase 1: Foundation — YAML layer, Portal server, admin auth

**Goal:** Portal is a runnable local web server with one admin (username + password). All six config files can be read/updated via a shared YAML layer that preserves comments. No Web UI yet (or minimal “hello” + login).

### 1.1 YAML merge layer for llm, memory_kb, skills_and_plugins, friend_presets

**What:** One place that loads/saves these four files using **ruamel** (merge updates only; never full overwrite with `yaml.safe_dump`). Reuse the same pattern as `Util.update_yaml_preserving_comments` for core.yml.

**Tasks:**

1. **Extend Util or add `ui/portal/yaml_config.py` (or `base/portal_config.py`):**
   - `load_yml_preserving(path: str) -> dict | None` — load with ruamel, return dict (or None on error).
   - `update_yml_preserving(path: str, updates: dict) -> bool` — load, merge `updates` into root, dump with ruamel; atomic write (.tmp + replace). Skip write if file exists and load failed (same guard as existing `update_yaml_preserving_comments`).
2. **Define whitelists per file** (subset of keys that the Portal is allowed to change):
   - `llm.yml`: e.g. `main_llm`, `embedding_llm`, `local_models`, `cloud_models`, and other keys from current llm.yml structure.
   - `memory_kb.yml`: e.g. `use_memory`, `memory_backend`, `session`, `profile`, `use_agent_memory_file`, `knowledge_base`, etc.
   - `skills_and_plugins.yml`: e.g. `skills_*`, `plugins_*`, `tools` (or top-level keys used by Core).
   - `friend_presets.yml`: e.g. `presets` (nested dict).
   - Document: “Only whitelisted keys are merged; others and all comments preserved.”
3. **Wire core.yml and user.yml:** core.yml already uses `Util().update_yaml_preserving_comments()`. user.yml uses `User.to_yaml()` (existing). Portal will call these; no new YAML helper needed for those two.

**Files:** New: `base/portal_config.py` or `ui/portal/yaml_config.py`. Possibly extend `base/util.py` with `update_yml_preserving(path, updates)` if we want one place for all YAML.

**Acceptance:** Unit test: load each of the four files, merge one whitelisted key, save; reload and assert key changed and a known comment line still present.

---

### 1.2 Portal admin credentials (username + password)

**What:** Store and verify one admin username and password. Used for both local Portal login and (later) Companion “Core setting” login via Core.

**Tasks:**

1. **Storage:** Add `config/portal_admin.yml` (or use env only). Suggested structure:
   - `admin_username: "admin"` (or from env `PORTAL_ADMIN_USERNAME`)
   - `admin_password_hash: "<bcrypt or similar>"` (or `admin_password` in env only, no file). Prefer hash in file; plain in env for dev.
2. **First-time setup:** If no admin is set (no file or empty), Portal shows “Set admin account” (username + password); on submit, create file with hash and redirect to login.
3. **Verification:** Function `verify_portal_admin(username: str, password: str) -> bool` (compare with stored hash or env). Used by Portal login and (Phase 5) by Core’s `/api/portal/auth`.

**Files:** New: `config/portal_admin.yml` (gitignore or template only). New: `ui/portal/auth.py` or in `ui/portal/` — credential load and verify.

**Acceptance:** Set admin once; subsequent login with correct/incorrect credentials returns success/failure.

---

### 1.3 Portal process and entrypoint

**What:** Portal runs as a separate process; bind 127.0.0.1 only; configurable port.

**Tasks:**

1. **Entrypoint:** In `main.py`, add command `portal` (e.g. `python -m main portal`). It starts the Portal app (FastAPI or Flask) on host 127.0.0.1 and port from env `PORTAL_PORT` or default 18472.
2. **App skeleton:** Create `ui/portal/app.py` (or extend `ui/homeclaw.py` with a clear “portal” mode). Minimal routes for Phase 1:
   - `GET /` → redirect to `/login` or, if no admin set, to `/setup`.
   - `GET /login` → login page (username + password form).
   - `POST /login` → verify credentials; set session cookie or return token; redirect to `/` or `/dashboard`.
   - `GET /setup` → “Set admin account” form (first time only).
   - `POST /setup` → create admin (hash password, write config); redirect to login.
3. **Session:** Use signed cookie or JWT for “logged in” state; session timeout optional (e.g. 24h). All routes under `/api/*` and dashboard require valid session (except `/login`, `/setup`).

**Files:** `main.py` (add `portal` command). New: `ui/portal/` — `app.py`, `auth.py`, templates or static for login/setup.

**Acceptance:** `python -m main portal` starts server; opening http://127.0.0.1:18472 shows login or setup; after login, can reach a minimal dashboard (placeholder).

---

### 1.4 Portal config API (read/write) for all six files

**What:** Portal exposes REST endpoints that **read** and **update** each config file using the YAML layer (Phase 1.1) and existing Util/User for core and users. No auth on these API routes from Core yet — that’s Phase 3 (Core will send secret). Local browser already has session.

**Tasks:**

1. **Core config:** `GET /api/config/core` — load core.yml (Util or existing load), return whitelisted keys, redact secrets. `PATCH /api/config/core` — body = partial dict; merge via `Util().update_yaml_preserving_comments()`; return `{ "result": "ok" }`.
2. **LLM, memory_kb, skills_and_plugins, friend_presets:** `GET /api/config/<name>` and `PATCH /api/config/<name>` for each; use `load_yml_preserving` / `update_yml_preserving` with per-file whitelist; redact sensitive keys on GET.
3. **Users:** `GET /api/config/users` — `Util().get_users()` and serialize. `POST /api/config/users` — add user via Util, `User.to_yaml`. `PATCH /api/config/users/{name}` and `DELETE /api/config/users/{name}` — update/remove via Util, save.
4. **Portal API auth (Phase 3):** Later, require `X-Portal-Secret` (or Bearer) on these routes when request is from Core. For Phase 1, optional: require same session as Web UI, or leave open for localhost-only testing.

**Files:** `ui/portal/app.py` (or `ui/portal/routes/config_routes.py`) — register routes; call Util and portal YAML helpers.

**Acceptance:** With Portal running, `curl` GET/PATCH to `/api/config/core` and `/api/config/llm` (and others) reads/updates files; comments preserved after PATCH.

---

**Phase 1 summary:** Portal runs; admin can log in; all six config files can be read/updated via API with comment-preserving merge. No full Web UI yet (optional: minimal dashboard with “Config” link placeholder).

---

## Phase 2: Portal Web UI (four areas)

**Goal:** Full Portal web UI: (1) Manage settings, (2) Guide to install, (3) Start Core, (4) Start channel. HTML5, responsive, usable in desktop browser and mobile WebView.

### 2.1 Manage settings UI

**What:** Tabs or sections for: Core, LLM, Memory/KB, Skills & Plugins, Users, Friend presets. Each section loads current config (via Portal’s own API or direct backend call), shows forms or structured editors, saves via PATCH (merge only).

**Tasks:**

1. **Layout:** One “Manage settings” page with sub-tabs or accordions: Core | LLM | Memory & KB | Skills & Plugins | Users | Friend presets.
2. **Per-section:** Fetch config (GET /api/config/&lt;name&gt;), render form (key fields only, whitelisted); sensitive fields show `***`; on Save, PATCH with changed fields only; `***` means “do not change”.
3. **Users section:** List users; Add / Edit / Delete; call POST / PATCH / DELETE /api/config/users.
4. **Tech:** Prefer server-rendered HTML + minimal JS (or a small SPA). Must work in mobile WebView (touch-friendly, readable fonts, no desktop-only assumptions).

**Files:** `ui/portal/templates/` or `ui/portal/static/` — HTML/CSS/JS for settings pages. Backend routes serve pages and proxy to config API if needed.

**Acceptance:** Logged-in user can open each tab, see current values, edit and save; YAML comments preserved; sensitive values show as `***`.

---

### 2.2 Guide to install UI

**What:** Step-by-step onboarding: Python version, venv, pip install, Node (optional), config dir, doctor (optional).

**Tasks:**

1. **Steps:** (1) Check Python ≥3.9. (2) Check/create venv; show command `pip install -r requirements.txt`. (3) Optional: check Node. (4) Check config/ and key YAML files exist. (5) Optional: “Run doctor” — call doctor logic, show report.
2. **Backend:** Endpoints that run checks (e.g. `GET /api/portal/check/python` returns version; `POST /api/portal/doctor` returns report). No automatic install; only guidance and status.
3. **UI:** Single “Guide to install” page; one step visible at a time; Next/Back; show pass/fail and short instructions per step.

**Files:** `ui/portal/` — routes and templates for onboarding. Reuse or call `main.doctor` logic for doctor report.

**Acceptance:** User can go through steps; each step shows clear pass/fail and what to do next.

---

### 2.3 Start Core UI

**What:** Button “Start Core”; status “Core running at …” or “Core not running”.

**Tasks:**

1. **Start:** On click, Portal spawns Core (e.g. `subprocess.Popen(["python", "-m", "main", "start"])` or run `core.main` in a thread). Don’t wait for completion; return immediately.
2. **Status:** Poll Core’s `/ready` (URL from core.yml: host/port). E.g. every 5s or on page load; show “Core running at http://…” or “Core not running”.
3. **Optional:** “Stop Core” button → POST to Core’s `/shutdown` (with care: only if same machine).

**Files:** `ui/portal/` — route e.g. `POST /api/portal/core/start`; frontend button and status polling.

**Acceptance:** Click Start Core → Core process runs; status updates to “running” when /ready returns 200.

---

### 2.4 Start channel UI

**What:** List channels (from `channels/*/channel.py`); buttons to start Core (if not running) and to start a chosen channel.

**Tasks:**

1. **List:** `GET /api/portal/channels` — scan `channels/` for `*/channel.py`, return `{ "channels": ["telegram", "webchat", ...] }`.
2. **Start channel:** `POST /api/portal/channels/{name}/start` — run `python channels/<name>/channel.py` in subprocess (or equivalent). Return 200 when process started.
3. **UI:** “Start channel” page: list of channel names; “Start Core” (if not running) and “Start &lt;channel&gt;” per channel. Optional “Start all”.

**Files:** `ui/portal/` — backend routes; frontend “Start channel” page.

**Acceptance:** Channels list appears; clicking “Start telegram” (or similar) starts that channel’s process.

---

**Phase 2 summary:** Portal has full Web UI for all four areas; HTML5, mobile-friendly. Local admin can do everything from the browser.

---

## Phase 3: Portal REST API auth (Core→Portal secret)

**Goal:** Only Core (and local session) can call the Portal’s config and portal APIs. Portal expects a shared secret in requests from Core.

### 3.1 Config for portal_url and portal_secret

**What:** Core and Portal both know `portal_url` and `portal_secret`. Portal validates the secret on API requests.

**Tasks:**

1. **core.yml (or env):** Add `portal_url: "http://127.0.0.1:18472"` and `portal_secret: "<random 32 chars>"`. Document: generate once, put same value in Portal config.
2. **Portal:** Read `portal_secret` from env `PORTAL_SECRET` or from a small config (e.g. `config/portal_admin.yml` or `config/portal_secret.txt`). Same value as in Core.

**Files:** `config/core.yml` (optional keys; can be env-only). Portal: read secret in middleware or dependency.

**Acceptance:** Portal has access to `portal_secret`; Core has `portal_url` and `portal_secret` in config.

---

### 3.2 Portal: require secret on API routes

**What:** Every request to `/api/config/*` and `/api/portal/*` must include the correct secret (e.g. header `X-Portal-Secret` or `Authorization: Bearer <secret>`). Browser session is separate (cookie); API calls from Core don’t use session.

**Tasks:**

1. **Middleware or dependency:** For routes under `/api/config/` and `/api/portal/`, check header. If missing or wrong → 401. If correct, proceed.
2. **Exception:** Requests that have a valid **session cookie** (browser) may be allowed without the secret for the same routes, so the Portal’s own Web UI can call its API from the same origin. Or: Web UI calls backend routes that don’t go through the same HTTP API (server-side render or internal call). Clarify: either (a) Web UI uses session; API routes require secret for non-session requests, or (b) Web UI only uses server-side; external API always requires secret. Recommend (a): if `X-Portal-Secret` present and valid, allow; else if session valid, allow; else 401.

**Files:** `ui/portal/app.py` — auth dependency or middleware.

**Acceptance:** Request without secret (and without session) → 401. Request with correct secret → 200 (for GET). Core (Phase 4) will send the secret when proxying.

---

**Phase 3 summary:** Portal API is protected; only Core (with secret) or logged-in browser session can call it.

---

## Phase 4: Core proxy to Portal (config + /portal-ui)

**Goal:** When `portal_url` is set, Core forwards config and user API calls to the Portal. Core also exposes `/portal-ui` and `/portal-ui/*` as a reverse proxy to the Portal’s Web UI so Companion can load it in a WebView.

### 4.1 Core: proxy config and users API to Portal

**What:** Core’s existing `/api/config/core`, `/api/config/users`, etc., when `portal_url` is set: forward request to Portal (with `portal_secret` header), return response to client. When `portal_url` not set, keep current behavior (Core reads/writes files).

**Tasks:**

1. **Config check:** In Core’s config API handlers (or a shared wrapper), if `getattr(meta, 'portal_url', None)` is set, do not read/write files; instead, forward:
   - Method and path (e.g. PATCH, `/api/config/core`); body if any; add header `X-Portal-Secret: <portal_secret>` (from config). Request to `portal_url + path`. Return response status and body to client.
2. **Apply to:** GET/PATCH `/api/config/core`, GET/POST/PATCH/DELETE `/api/config/users` (and `/api/config/users/{name}`). Optionally other config files if Portal exposes them and Companion will need them via Core later.
3. **Error handling:** If Portal returns 5xx or connection error, return 502 or 503 to client with clear message.

**Files:** `core/routes/config_api.py` (or a new `core/routes/portal_proxy.py`). Core metadata: ensure `portal_url` and `portal_secret` are read from config/env.

**Acceptance:** With Portal running and `portal_url` + `portal_secret` set in Core, Companion (or curl) calling Core’s `/api/config/core` gets response from Portal; config is read/written on Portal side.

---

### 4.2 Core: reverse proxy /portal-ui to Portal

**What:** Core exposes `GET /portal-ui` and `GET /portal-ui/*` that proxy to Portal’s `GET /` and `GET /*`. Companion will load `https://core_public_url/portal-ui` in a WebView. Auth for `/portal-ui` is Phase 5 (admin only).

**Tasks:**

1. **Route:** Register `GET /portal-ui` and `GET /portal-ui/{path:path}`. Handler: build upstream URL = `portal_url + "/" + path` (and query string); request with `X-Portal-Secret`; stream response back (status, headers, body). Handle redirects (e.g. Location header rewrite so client doesn’t see Portal’s localhost).
2. **Headers:** Forward or strip as needed (e.g. Host, Cookie). Portal may set cookies; rewrite cookie path to `/portal-ui` if needed so WebView sends them on next request.
3. **Auth:** In Phase 5, require admin auth before serving `/portal-ui`. For Phase 4, optional: require Core API key only, or leave open for testing.

**Files:** `core/routes/portal_proxy.py` or in `core/route_registration.py` — add proxy routes. Use httpx or aiohttp to fetch from Portal, stream to client.

**Acceptance:** With Core and Portal running, opening `http://core_host:port/portal-ui` in browser shows Portal’s login page (or dashboard if session); all assets and navigation work (relative links may need base tag or rewrite).

---

**Phase 4 summary:** Core proxies config API and full Portal UI to Companion; Companion can use Core’s URL to reach config and Portal pages.

---

## Phase 5: Core admin auth for Companion (username + password)

**Goal:** Only an admin who knows the Portal admin username and password can access `/portal-ui` and (optionally) config proxy. Core exposes `POST /api/portal/auth` and validates credentials; returns token used for subsequent requests.

### 5.1 Core: portal admin credentials and auth endpoint

**What:** Core can verify Portal admin username/password (same as Portal). Core exposes `POST /api/portal/auth` with body `{ "username", "password" }`; if valid, return short-lived token. Requests to `/portal-ui` and config proxy require this token (or the same username+password in header) when coming from Companion.

**Tasks:**

1. **Core has admin credentials:** Read from same source as Portal (e.g. `config/portal_admin.yml` or env `PORTAL_ADMIN_USERNAME`, `PORTAL_ADMIN_PASSWORD`). Core must be able to call the same `verify_portal_admin(username, password)` logic (e.g. shared module in `base/` or Portal exports verification; or Core reads hash and verifies). Prefer: Portal stores hash; Core reads same file and verifies password.
2. **POST /api/portal/auth:** Body: `{ "username": "...", "password": "..." }`. If valid, return `{ "token": "<jwt or opaque>" }` with short TTL (e.g. 1h). If invalid, 401.
3. **Protect /portal-ui:** For `GET /portal-ui` and `GET /portal-ui/*`, require either (a) `Authorization: Bearer <token>` (from /api/portal/auth), or (b) query/header with username+password (e.g. for WebView: pass token in URL fragment or header). If missing or invalid → 401 or redirect to Companion’s login screen (Companion handles that; Core just rejects).
4. **Config proxy:** When Core proxies config to Portal, it adds `X-Portal-Secret`. Companion may call config API with only Core API key today; decide: either (1) config proxy also requires portal admin token (so only admin can PATCH config from Companion), or (2) config proxy only requires Core API key. Design chose (1): only admin can manage settings. So: when Core proxies GET/PATCH /api/config/* to Portal, first check that the request has valid portal admin token (or username+password); if not, 403. So Companion must call POST /api/portal/auth first, then send token with every config request. Alternatively, Companion sends username+password in headers for each config request; Core verifies and then proxies. Simpler: token once, then Bearer for /portal-ui and for config proxy.

**Files:** `core/routes/portal_proxy.py` or new `core/routes/portal_auth.py`. Shared: `base/portal_admin.py` or Portal’s auth module importable by Core for `verify_portal_admin`.

**Acceptance:** Unauthenticated request to /portal-ui → 401. After POST /api/portal/auth with correct credentials, request with Bearer token to /portal-ui → 200 and Portal content. Config proxy with Bearer token → 200; without token → 403.

---

**Phase 5 summary:** Companion (or any client) must authenticate as portal admin to open /portal-ui or to use config proxy; Core validates and issues token.

---

## Phase 6: Companion app — “Core setting” entry and WebView

**Goal:** Companion has a “Core setting” (or “Manage Core”) entry; tapping it forces username + password; then opens WebView to Core’s `/portal-ui` (with token or auth).

### 6.1 Companion: “Core setting” entry and login screen

**What:** Add an entry point (e.g. in settings or menu) “Core setting” (or “Manage Core”). On tap, show a **login screen** (username + password). Do not show WebView until login succeeds.

**Tasks:**

1. **Screen:** New screen or bottom sheet: two fields (username, password) and “Log in”. On submit, call Core `POST /api/portal/auth` with body `{ "username", "password" }`. If 200, store token (memory or secure storage); if 401, show “Invalid username or password”.
2. **Navigation:** After success, open the WebView screen (Phase 6.2) with the token. Optional: “Remember me” or session TTL; re-prompt after expiry.
3. **Entry:** From settings/menu, “Core setting” navigates to this login screen (not directly to WebView).

**Files:** `clients/HomeClawApp/` — new screen/screen logic; Core API client: add `postPortalAuth(username, password)` and store token.

**Acceptance:** User taps “Core setting” → sees login; wrong credentials → error; correct → proceeds to WebView.

---

### 6.2 Companion: WebView loading /portal-ui with auth

**What:** After login, Companion opens a WebView that loads `https://core_base_url/portal-ui` and sends the auth token so Core allows the request.

**Tasks:**

1. **URL:** Build URL = Core base URL + `/portal-ui`. Add token: either (a) `Authorization: Bearer <token>` in WebView’s request headers (if WebView API supports custom headers), or (b) pass token in URL (e.g. `?token=...` or fragment); Core’s /portal-ui handler reads token from query/fragment and validates. Option (a) is cleaner; (b) works everywhere.
2. **WebView:** Load URL (with token). Handle back button: close WebView or go back inside WebView. Optionally inject base tag or ensure Portal UI works with a base path (Core serves at /portal-ui so relative links like /api/config/core must be rewritten by Core to Portal; or Portal’s front-end uses relative paths that Core’s proxy can serve).
3. **Logout:** “Log out” or “Back” clears token and returns to Companion; next “Core setting” tap shows login again.

**Files:** `clients/HomeClawApp/` — WebView screen; pass token via header or URL; Core’s /portal-ui accepts token from query if needed (e.g. `GET /portal-ui?token=...` for WebView that can’t set headers).

**Acceptance:** After login, WebView shows Portal’s dashboard/settings; user can navigate and use all four areas; logout or back returns to Companion.

---

**Phase 6 summary:** Companion has a single “Core setting” flow: login (username + password) → WebView of Portal via Core; no native settings screens to maintain.

---

## Dependencies and order

```
Phase 1.1 (YAML layer) ─────────────────────────────────────────┐
Phase 1.2 (admin credentials) ─────────────────────────────────┤
Phase 1.3 (Portal process) ─────────────────────────────────────┼──► Phase 1.4 (Portal config API)
Phase 1.4 depends on 1.1, 1.2, 1.3                             ┘

Phase 2 (Web UI) depends on Phase 1 (all steps).

Phase 3 (Portal API secret) depends on Phase 1.4 (API exists).

Phase 4 (Core proxy) depends on Phase 3 (secret); Portal and Core both run.

Phase 5 (Core admin auth) depends on Phase 4 (/portal-ui exists); Core can verify admin.

Phase 6 (Companion) depends on Phase 5 (auth endpoint + protected /portal-ui).
```

---

## Files to create or modify (summary)

| Area | New | Modify |
|------|-----|--------|
| **YAML / config** | `base/portal_config.py` (or in util) | `base/util.py` (optional) |
| **Portal admin** | `config/portal_admin.yml` (template/gitignore), `ui/portal/auth.py` | — |
| **Portal app** | `ui/portal/app.py`, `ui/portal/routes/`, templates/static | `main.py` (portal command) |
| **Core proxy** | `core/routes/portal_proxy.py`, `core/routes/portal_auth.py` | `core/route_registration.py`, `core/routes/config_api.py`, CoreMetadata (portal_url, portal_secret) |
| **Companion** | New screen(s) for login + WebView | Navigation/settings entry, Core API client |
| **Config** | — | `config/core.yml` (portal_url, portal_secret, optional portal_admin ref) |

---

## Review checklist

- [ ] Phase 1: YAML never overwrites with full file; comments preserved; whitelists documented.
- [ ] Phase 1: Admin password stored hashed; first-time setup flow clear.
- [ ] Phase 2: All four areas (settings, guide, start Core, start channel) implemented; UI works on mobile WebView.
- [ ] Phase 3: Only Core (with secret) or session can call Portal API.
- [ ] Phase 4: Core proxy forwards config and /portal-ui; no leakage of portal_secret to client.
- [ ] Phase 5: Only valid portal admin gets token; /portal-ui and config proxy require auth.
- [ ] Phase 6: Companion always prompts for username+password at “Core setting”; WebView receives auth and loads Portal UI correctly.

---

**User documentation:** For how to use the Portal from a web browser and from the Companion app, see [PortalUsage.md](PortalUsage.md).

*Ref: [CorePortalDesign.md](CorePortalDesign.md).*
