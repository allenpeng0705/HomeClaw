# Portal Step 1.4: Config API (GET/PATCH for all six files) — done

**Design ref:** [CorePortalDesign.md](../CorePortalDesign.md), [CorePortalImplementationPlan.md](../CorePortalImplementationPlan.md) Phase 1.4.

**Goal:** Portal exposes REST endpoints to read and update each of the six config files (core, llm, memory_kb, skills_and_plugins, user, friend_presets) with whitelisted merge, redaction of secrets, and previous backup before each PATCH.

---

## 1. What was implemented

### 1.1 Routes (require session)

- **GET /api/config/{name}** — Return config as JSON. `name` is one of: core, llm, memory_kb, skills_and_plugins, user, friend_presets. Without valid session → 401. Unknown name → 404. Response is redacted (see below).
- **PATCH /api/config/{name}** — Body = JSON object; only whitelisted keys are merged. Calls `prepare_for_update(name)` before write (backup to .previous). Without session → 401. Returns `{ "result": "ok" }` on success.

### 1.2 `portal/config_api.py`

- **load_config(name)** — Load file via `yaml_config.load_yml_preserving`; return dict or None. No redaction.
- **load_config_for_api(name)** — Load and return redacted dict for API:
  - **core:** Only keys in WHITELIST_CORE; `auth_api_key` and `pinggy.token` replaced with `"***"`.
  - **llm:** `api_key` and `api_key_name` in cloud_models/local_models entries replaced with `"***"`.
  - **user:** Top-level `users` list with each `password` replaced with `"***"`.
  - **llm, memory_kb, skills_and_plugins, friend_presets:** returned as-is (no extra redaction beyond llm).
- **update_config(name, body)** — Call `config_backup.prepare_for_update(name)`, then merge `body` with per-file whitelist via `yaml_config.update_yml_preserving`. For **user**, only top-level key `users` (full list) is allowed.

### 1.3 Whitelists

- **core:** WHITELIST_CORE in config_api.py (name, host, port, mode, compaction, auth_enabled, auth_api_key, pinggy, push_notifications, file_understanding, llama_cpp, completion, etc.).
- **llm, memory_kb, skills_and_plugins, friend_presets:** Existing whitelists in portal/yaml_config.py.

---

## 2. Files touched

| File | Change |
|------|--------|
| **portal/config_api.py** | New: load_config, load_config_for_api, update_config, redaction helpers, WHITELIST_CORE. |
| **portal/app.py** | GET /api/config/{name}, PATCH /api/config/{name}; _require_session for 401. |
| **tests/test_portal_config_api.py** | New: 7 tests (401 without session, 200 with session, 404 unknown name, PATCH 401/200, core redaction, user list redaction). |
| **docs_design/implementation_steps/Portal_Step1.4_config_api.md** | New (this file). |

---

## 3. Tests

```bash
pytest tests/test_portal_config_api.py -v
```

- **test_config_get_without_session_returns_401**
- **test_config_get_with_session_returns_200**
- **test_config_get_unknown_name_returns_404**
- **test_config_patch_without_session_returns_401**
- **test_config_patch_with_session_returns_200**
- **test_config_get_core_redacts_auth_api_key**
- **test_config_get_user_returns_users_list** (passwords redacted)

---

## 4. Next (Phase 2)

Portal Web UI: Manage settings (tabs for Core, LLM, Memory/KB, Skills & Plugins, Users, Friend presets), Guide to install, Start Core, Start channel. HTML5, mobile-friendly.
