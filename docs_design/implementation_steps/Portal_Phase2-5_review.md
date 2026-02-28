# Portal Phases 2.4–6: Review for correctness and stability

**Date:** Full review after Phase 6.

## Changes made for robustness (never crash)

### Core portal_proxy.py
- **Streaming bug:** Replaced streaming response with full read inside `async with httpx.AsyncClient()` so the connection is not used after the client context exits. Returns `Response(content=content, ...)` instead of `StreamingResponse(stream(), ...)`.
- **Timeout:** Added explicit `httpx.TimeoutException` handling for Portal UI proxy (504).
- **get_portal_admin_from_request:** Wrapped entire body in `try/except: return None` so it never raises.
- **post_portal_auth_handler:** Validate `body` is a dict before calling `.get()` to avoid AttributeError on non-dict body.

### Portal app.py
- **API auth middleware:** Wrapped `dispatch` in try/except; on any exception return 500 JSON (never raise).
- **When portal_secret is not set:** Require session for all `/api/*` so config and portal API are never open. Exception: allow GET `/api/portal/status` and GET `/api/portal/guide/checks` without session (read-only health/info).

## Test results

- **Portal tests (46):** All pass (config API, auth, session, step1, step3, yaml_config, config_backup).
- **Core / friend_presets / litellm tests:** Fail in current environment due to missing optional dependencies (aiohttp, uvicorn, chromadb, litellm), not due to Portal/Phase code changes.

## Additional fixes (this review)

- **Core proxy_request_to_portal:** Strip client `Authorization` (and Host, Connection, Transfer-Encoding) when forwarding to Portal so Portal only sees `X-Portal-Secret`. Use case-insensitive header drop (`k.lower() in drop_lower`) so "Authorization" and "authorization" are both removed.
- **Companion portal_login_screen:** Set `_loading = false` after successful `postPortalAuth` and before `pushReplacement` so state is clean and any navigation error doesn’t leave the button stuck in loading.

## Logic summary

| Area | Behavior |
|------|----------|
| Portal API auth | When `portal_secret` set: allow session OR X-Portal-Secret/Bearer. When not set: require session, except GET status and guide/checks. |
| Core config proxy | When `portal_url` set: require portal admin (Bearer/Basic/query token) then proxy; else 403. When not set: local file read/write. Proxy strips client Authorization so Portal sees only X-Portal-Secret. |
| Core /portal-ui | When `portal_url` set: require portal admin auth then proxy (full body read, no streaming). When not set: 502. |
| Core POST /api/portal/auth | Validates via portal.auth; returns token or 401/503; never raises. |
| Companion Core setting | Login → postPortalAuth → save token → WebView /portal-ui?token=; sub-navigations get token appended; logout clears token and pops. |
