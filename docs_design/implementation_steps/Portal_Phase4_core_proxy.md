# Portal Phase 4: Core proxy to Portal (config + /portal-ui) — done

**Design ref:** [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 4.

**Goal:** When `portal_url` is set, Core forwards config and user API calls to the Portal, and exposes `/portal-ui` and `/portal-ui/*` as a reverse proxy to the Portal’s Web UI.

---

## 1. What was implemented

### 4.1 Core: proxy config and users API to Portal

- **CoreMetadata** (`base/base.py`): Added `portal_url: str = ""` and `portal_secret: str = ""`. Loaded from `core.yml` or env `PORTAL_URL` / `PORTAL_SECRET`. Written back in `to_yaml` when set.
- **portal_proxy** (`core/routes/portal_proxy.py`): `should_proxy_config()` returns True when `portal_url` is set. `proxy_request_to_portal(request)` forwards the request (method, path, query, body, headers) to `portal_url + request.url.path`, adds `X-Portal-Secret`, returns response or 502/503/504 on connection/timeout/error.
- **config_api** (`core/routes/config_api.py`): At the start of each of the six handlers (GET/PATCH core, GET/POST/PATCH/DELETE users), if `portal_proxy.should_proxy_config()` then return `await portal_proxy.proxy_request_to_portal(request)`; otherwise existing file read/write logic.
- **Portal** (`portal/config_api.py`): `WHITELIST_CORE` includes `portal_url` and `portal_secret` so they can be edited and saved via Portal UI. `_redact_core()` redacts `portal_secret` as `***` on GET.

### 4.2 Core: reverse proxy /portal-ui to Portal

- **Routes** (`core/route_registration.py`): `GET /portal-ui` and `GET /portal-ui/{path:path}` registered (exact path first). No auth in Phase 4 (Phase 5 will add admin auth).
- **Handlers** (`core/routes/portal_proxy.py`): `get_portal_ui_handler()` and `get_portal_ui_path_handler()` build upstream URL `portal_url + "/" + path`, send GET with `X-Portal-Secret`, stream response back. Location header rewritten so redirects point to `/portal-ui/...` instead of Portal’s origin. Set-Cookie path rewritten to `Path=/portal-ui` so the browser sends cookies on subsequent /portal-ui requests.

---

## 2. Files touched

| File | Change |
|------|--------|
| **base/base.py** | CoreMetadata: `portal_url`, `portal_secret`; from_yaml (data + env); to_yaml (write when set). |
| **core/routes/portal_proxy.py** | New: `_get_portal_url`, `_get_portal_secret`, `should_proxy_config`, `proxy_request_to_portal`, `_stream_portal_ui`, `_rewrite_location_for_portal_ui`, `get_portal_ui_handler`, `get_portal_ui_path_handler`. |
| **core/routes/config_api.py** | Import portal_proxy; in all six handlers, if should_proxy_config() then return proxy_request_to_portal(request). GET core and users handlers now take (request). |
| **core/routes/__init__.py** | Import and export portal_proxy. |
| **core/route_registration.py** | Import portal_proxy; register GET /portal-ui and GET /portal-ui/{path:path}. |
| **portal/config_api.py** | WHITELIST_CORE: add portal_url, portal_secret; _redact_core: redact portal_secret. |
| **docs_design/implementation_steps/Portal_Phase4_core_proxy.md** | This file. |

---

## 3. Acceptance

- With `portal_url` and `portal_secret` set in Core (core.yml or env), Companion (or curl) calling Core’s `GET /api/config/core` or `PATCH /api/config/core` etc. receives the response from Portal; config is read/written on the Portal side.
- With Core and Portal running, opening `http://core_host:port/portal-ui` in a browser shows the Portal’s login page (or dashboard if session); navigation and assets work; redirects and cookies are rewritten for /portal-ui.
