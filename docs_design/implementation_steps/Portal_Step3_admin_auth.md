# Portal Step 3: Admin credentials + login/setup — done

**Design ref:** [CorePortalDesign.md](../CorePortalDesign.md), [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 1.2.

**Goal:** One admin account (username + password). First visit → setup; then login; session via signed cookie. Root `/` redirects to `/setup`, `/login`, or `/dashboard` by state.

---

## 1. What was implemented

### 1.1 `portal/auth.py`

- **`admin_is_configured() -> bool`** — True if `config/portal_admin.yml` exists and non-empty, or env `PORTAL_ADMIN_USERNAME` + `PORTAL_ADMIN_PASSWORD` are set (dev override). Never raises.
- **`load_admin_credentials() -> (username, salt, hash_hex)`** — Loads from file or returns env-based tuple; None on error. Never raises.
- **`verify_portal_admin(username, password) -> bool`** — Matches against file (salt + SHA-256) or env. Never raises.
- **`set_admin(username, password) -> bool`** — Writes `portal_admin.yml` with username, salt, and hash; returns False on empty input or write error. Never raises.

Storage: `config/portal_admin.yml` (username, salt, hash). Env override: `PORTAL_ADMIN_USERNAME`, `PORTAL_ADMIN_PASSWORD` for development only.

### 1.2 `portal/session.py`

- **`create_session_value(username) -> str`** — Signed cookie value: base64(username:expiry_ts:hmac). TTL 24h; secret from `PORTAL_SESSION_SECRET`.
- **`verify_session_value(value) -> str | None`** — Returns username if valid and not expired, else None. Never raises.

### 1.3 `portal/app.py` routes

- **GET /** — Redirect: no admin → `/setup`; no valid session → `/login`; else → `/dashboard`.
- **GET /setup** — Setup form if admin not configured; else redirect to `/login`.
- **POST /setup** — Create admin via `auth.set_admin`; redirect to `/login` or `/setup?error=1` on failure.
- **GET /login** — Login form; if admin not set redirect to `/setup`.
- **POST /login** — Verify credentials; set `portal_session` cookie (HttpOnly, SameSite=Lax, 24h); redirect to `/dashboard` or `/login?error=1`.
- **GET /dashboard** — Protected; show minimal dashboard if session valid; else redirect to `/login`.

Cookie name: `portal_session`. Dependency: `python-multipart` for Form data.

### 1.4 Stability

- All auth/session functions never raise; return False/None on error.
- Root and protected routes use redirects; global exception handler returns 500 without crashing.

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/auth.py** | New: admin storage, verify, set_admin, env override. |
| **portal/session.py** | New: create/verify session value (HMAC-signed cookie). |
| **portal/app.py** | Single GET / with Request; /setup, /login, /dashboard (GET/POST); session cookie on POST /login. |
| **requirements.txt** | Added `python-multipart>=0.0.6`. |
| **.gitignore** | Added `/config/portal_admin.yml`. |
| **tests/test_portal_auth.py** | New: 6 tests (admin_is_configured, set_admin, verify, empty reject). |
| **tests/test_portal_session.py** | New: 3 tests (create/verify, expired, invalid). |
| **tests/test_portal_step3_routes.py** | New: 9 tests (redirects, setup, login, dashboard, wrong password). |
| **docs_design/implementation_steps/Portal_Step3_admin_auth.md** | New (this file). |

---

## 3. Tests

```bash
pytest tests/test_portal_auth.py tests/test_portal_session.py tests/test_portal_step3_routes.py -v
```

- **Auth:** admin_is_configured false when no file; set_admin creates file; verify after set; reject empty username/password.
- **Session:** create and verify; expired returns None; invalid value returns None.
- **Routes:** root → /setup when no admin; GET /setup 200; POST /setup → /login; root → /login after setup; POST /login sets cookie → /dashboard; GET /dashboard without session → /login; with session 200; wrong password → /login?error=1.

---

## 4. Next (Phase 1.4)

Portal config API: GET/PATCH for core.yml, llm.yml, memory_kb.yml, skills_and_plugins.yml, user.yml, friend_presets.yml (using `prepare_for_update` before PATCH). Then Phase 2: full Web UI for editing.
