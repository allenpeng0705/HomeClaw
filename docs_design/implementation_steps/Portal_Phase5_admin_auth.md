# Portal Phase 5: Core admin auth for Companion — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 5.

**Goal:** Only an admin who knows the Portal admin username and password can access `/portal-ui` and the config proxy. Core exposes `POST /api/portal/auth` and validates credentials; returns a short-lived token for subsequent requests.

---

## 1. What was implemented

### 5.1 Core: portal admin credentials and auth endpoint

- **Verification:** Core uses Portal’s admin credentials by importing `portal.auth` and calling `verify_portal_admin(username, password)` (same `config/portal_admin.yml` or env `PORTAL_ADMIN_USERNAME` / `PORTAL_ADMIN_PASSWORD`). If the portal package is not importable, auth is disabled (503 from POST /api/portal/auth).
- **POST /api/portal/auth:** Body `{ "username", "password" }`. If valid, creates an opaque token (secrets.token_urlsafe(32)), stores it in memory as `token -> (username, expires_at)` with TTL 1 hour, returns `{ "token": "<token>" }`. If invalid or missing body, 401. No Core API key required.
- **Token store:** In-memory dict in `portal_proxy`: `_PORTAL_ADMIN_TOKENS: dict[str, tuple[str, float]]`. Expired entries are removed when validating.

### 5.2 Protect /portal-ui and config proxy

- **get_portal_admin_from_request(request):** Returns username if the request has valid portal admin auth: (1) `Authorization: Bearer <token>` and token in store and not expired, (2) query param `token=...` (for WebView), or (3) `Authorization: Basic <base64(username:password)>` and `verify_portal_admin(username, password)`. Otherwise returns None.
- **/portal-ui and /portal-ui/*:** Before proxying, if `get_portal_admin_from_request(request)` is None, return 401 with `{"detail": "Portal admin auth required (Bearer token, Basic, or ?token=)"}`.
- **Config proxy:** When `should_proxy_config()` is true, before calling `proxy_request_to_portal(request)`, if `get_portal_admin_from_request(request)` is None, return 403 with `{"detail": "Portal admin auth required for config proxy (Bearer token or Basic)"}`. Applied to all six config handlers (GET/PATCH core, GET/POST/PATCH/DELETE users).

---

## 2. Files touched

| File | Change |
|------|--------|
| **core/routes/portal_proxy.py** | Import portal.auth; token store; `_verify_portal_admin`, `_purge_expired_tokens`, `get_portal_admin_from_request`; `post_portal_auth_handler`; auth check at start of `_stream_portal_ui`. |
| **core/routes/config_api.py** | In all six handlers, when `should_proxy_config()`, require `get_portal_admin_from_request(request)` or return 403 before proxying. |
| **core/route_registration.py** | Register POST /api/portal/auth -> portal_proxy.post_portal_auth_handler. |
| **docs_design/implementation_steps/Portal_Phase5_admin_auth.md** | This file. |

---

## 3. Acceptance

- Unauthenticated GET /portal-ui → 401.
- After POST /api/portal/auth with correct credentials, GET /portal-ui with `Authorization: Bearer <token>` (or `?token=...`) → 200 and Portal content.
- Config proxy (e.g. GET /api/config/core) with Bearer token → 200 (proxied to Portal).
- Config proxy without portal admin token → 403.
