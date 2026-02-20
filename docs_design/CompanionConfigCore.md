# Config Core from Flutter Companion

**Goal:** Let the HomeClaw Flutter companion app configure Core easily—manage `core.yml` and `user.yml`

---

## Approach

- **Core** exposes a small **config API** (read/update `core.yml`, list/add/remove users in `user.yml`).
- **Companion app** adds a **“Config Core”** (or “Manage Core”) screen that calls this API so users can edit key settings and users without touching YAML by hand.

Config files stay on the machine where Core runs; the app only talks to Core over HTTP. When `auth_enabled` is true, the same API key used for `/inbound` (and stored in the app’s Settings) is used for the config API.

---

## Core API

All under the same auth as `/inbound`: when `auth_enabled` is true, require `X-API-Key` or `Authorization: Bearer`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config/core` | Return current core config (safe subset or full as JSON). Sensitive keys (e.g. `auth_api_key`) may be redacted in response. |
| PATCH | `/api/config/core` | Update core config. Body: partial JSON; only whitelisted keys are applied (e.g. `host`, `port`, `main_llm`, `use_memory`, `auth_enabled`, `auth_api_key`, `silent`, `mode`). |
| GET | `/api/config/users` | Return list of users from `user.yml` (each: `id`, `name`, `email`, `im`, `phone`, `permissions`). |
| POST | `/api/config/users` | Add a user. Body: `{ "name", "id?", "email?", "im?", "phone?", "permissions?" }`. |
| DELETE | `/api/config/users/{name}` | Remove user by `name`. |

- **core.yml:** Read from disk, merge PATCH body (whitelist only), write back. No Core restart required for most options; some (e.g. `host`/`port`) may need restart to take effect.
- **user.yml:** Load via `Util().get_users()`, apply add/remove, save via `Util().save_users()`. Core’s in-memory user list can be refreshed if we support hot-reload (e.g. existing watchdog) or on next request.

---

## Flutter app

- **CoreService:** Add `getConfigCore()`, `patchConfigCore(Map)`, `getConfigUsers()`, `addConfigUser(Map)`, `removeConfigUser(String name)` using the app’s existing base URL and API key.
- **UI:** New screen **“Config Core”** (or a “Manage Core” section in Settings) with:
  - **Core:** Form for whitelisted keys (host, port, main_llm, use_memory, auth_enabled, auth_api_key, silent, mode). Load on open, Save button calls PATCH.
  - **Users:** List of users with Add / Remove. Add: dialog with name, id (optional), email/im/phone (comma-separated or list), permissions. Remove: confirm then DELETE.

Optional: show a short note that changing host/port or main_llm may require restarting Core.

---

## Security

- Config API is protected by the same auth as `/inbound` when `auth_enabled` is true.
- Only whitelisted keys are writable for `core.yml` to avoid overwriting sensitive or structural config.
- Companion stores the API key in app settings (existing behavior); that key is used for both chat and config.

---

## Summary

- **Core:** GET/PATCH `/api/config/core`, GET/POST/DELETE `/api/config/users` (auth like `/inbound`).
- **Companion:** CoreService methods + “Config Core” screen to manage core.yml and user.yml via the API.
