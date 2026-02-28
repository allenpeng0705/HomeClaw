# Portal Phase 3: REST API auth (Core→Portal secret) — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 3.

**Goal:** Only Core (with shared secret) or logged-in browser session can call the Portal’s config and portal APIs.

---

## 1. What was implemented

### 3.1 Config for portal_url and portal_secret

- **Core (config/core.yml):** Commented optional keys added: `portal_url`, `portal_secret`, with a note to generate the secret once and set the same value in Portal (PORTAL_SECRET or config/portal_secret.txt). Uncomment and set when using Core proxy (Phase 4).
- **Portal:** `get_portal_secret()` in `portal/config.py` reads the shared secret from:
  1. Env `PORTAL_SECRET` (if set), else
  2. File `config/portal_secret.txt` (first line, stripped).
  If neither is set, returns `None` (API is not protected by secret; session-only or open for dev).

### 3.2 Portal: require secret on API routes

- **Middleware** `_APIAuthMiddleware` in `portal/app.py`: runs for every request whose path starts with `/api/`.
  - If `get_portal_secret()` is `None`: allow (no secret required).
  - Else: allow if (1) valid session cookie, or (2) header `X-Portal-Secret` matches secret (constant-time compare), or (3) `Authorization: Bearer <secret>` matches.
  - Otherwise return 401 with `{"detail": "Missing or invalid API auth (session or X-Portal-Secret)"}`.
- **Config API** (`GET/PATCH /api/config/{name}`): removed per-route session check; auth is enforced by the middleware (session or secret).
- **Portal API** (`/api/portal/*`): same middleware; no separate checks.

---

## 2. Files touched

| File | Change |
|------|--------|
| **config/core.yml** | Commented `portal_url`, `portal_secret` and usage note. |
| **portal/config.py** | `get_portal_secret()` (env + portal_secret.txt); `Optional` import. |
| **portal/app.py** | Import `get_portal_secret`, `secrets`, `BaseHTTPMiddleware`. `_APIAuthMiddleware`; `app.add_middleware(_APIAuthMiddleware)`. Config routes: removed `_require_session`, rely on middleware. |
| **.gitignore** | `config/portal_secret.txt` so secret file is not committed. |
| **docs_design/implementation_steps/Portal_Phase3_api_auth.md** | This file. |

---

## 3. Acceptance

- When `PORTAL_SECRET` or `config/portal_secret.txt` is set: request without valid session and without correct `X-Portal-Secret` (or Bearer) → 401.
- Request with correct `X-Portal-Secret` header → allowed (for Core proxy in Phase 4).
- Request with valid session cookie (Portal Web UI) → allowed.
- When no secret is configured: all `/api/*` requests allowed (backward compatible / dev).
