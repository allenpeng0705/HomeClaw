# core.yml and user.yml — Where They're Written and Companion App "Manage Core"

The **Companion app** has a feature to **manage core.yml and user.yml** (Manage Core + user list): edit server, LLM, memory, session, users, etc. from the app. This doc lists every place that writes these files so we can confirm that **managing from the app does not remove content or comments**.

## Summary

- **Only one file is ever written for core config:** `config/core.yml`. No code writes to `config/core.yml.reference`; that file is for your backup/restore only.
- **Companion app** manages **core.yml** via `GET` / `PATCH` `/api/config/core` and **user.yml** via `GET` / `POST` / `PATCH` / `DELETE` `/api/config/users`. The server **always merges** request data into the full file; it never replaces the whole file with only the keys the app sent.
- **core.yml** and **user.yml** writes elsewhere (Util, main.py, ui) also use **merge** or **comment-preserving update** (ruamel). No code path should replace the whole file with a subset of keys.
- **Comments** are preserved when writes go through **ruamel.yaml**. Ensure `ruamel.yaml` is installed.

---

## 1. Writes to core.yml

| Location | When | Behavior |
|----------|------|----------|
| **base/base.py** `CoreMetadata.to_yaml()` | Called from Util when updating main_llm, silent, memory, switch_llm, get_core_metadata (default LLM), set_mainllm, and module init (reset_memory). | **Merge:** Loads file with ruamel → **deep-merges** nested dicts (cognee, database, vectorDB, graphDB, completion, llama_cpp, hybrid_router, etc.) into existing so **comments inside those sections are preserved**; scalars/lists replaced. Other keys and top-level comments preserved. Fallback: same deep-merge into existing, safe_dump (no comment preservation). |
| **base/util.py** `update_yaml_preserving_comments()` | Called by Core PATCH /api/config/core, main.py (onboarding, update_core_config), ui/homeclaw (update_config). | **Merge:** Loads with ruamel → for each key in `updates`: `data[k] = v` → dump. Callers pass **full** merged config (server loads full file, merges PATCH body, then passes that). So no keys are dropped. Fallback: load_yml_config + merge updates, then write_config (full overwrite of content, no comments). |

**Companion app:** Uses `PATCH /api/config/core` with a **body built from the form** (`_buildPatchBody()`). The body does **not** include every key in core.yml (e.g. no `main_llm_mode`, `main_llm_local`, `main_llm_cloud`, `hybrid_router`, `file_understanding`, etc.). On the server we do:

```text
data = load_yml_config(path)   # full file
for k, v in body.items(): data[k] = v   # merge body into full data
update_yaml_preserving_comments(path, data)   # write full data
```

So the file is **never** replaced by the PATCH body alone; all keys from the existing file stay, and only whitelisted keys from the body are updated. **Using "Manage Core" in the Companion app to edit core.yml is therefore safe** — keys and sections not shown in the app (e.g. `hybrid_router`, `main_llm_mode`, `main_llm_local`, `main_llm_cloud`) remain in the file.

---

## 2. user.yml and the Companion app

| Location | When | Behavior |
|----------|------|----------|
| **base/base.py** `User.to_yaml()` | Called from Util when saving users (add/update/remove via Core API or internally). | **Merge:** Loads user.yml with ruamel → sets `data['users'] = ...` (only the `users` key is updated) → dumps. Other top-level keys and comments preserved. Fallback: safe_dump of `{'users': ...}` only (no comment preservation). |
| **Core** `POST/PATCH/DELETE /api/config/users` | Companion app: Add user, Edit user, Remove user. | Server calls `Util().add_user()` / `Util().save_users()` / `Util().remove_user()`, which in turn call `User.to_yaml()`. So **managing users from the Companion app** goes through the same merge logic; other content in user.yml is preserved. |

---

## 3. Module-level write (base/util.py lines 39–43)

At **import** of `base.util`:

- Loads `config/core.yml` into `core_metadata`.
- If `reset_memory == True`, sets it to False, calls `CoreMetadata.to_yaml(...)`, then deletes `database/`.

So this write uses the same merge logic as above; it does not replace the file with only CoreMetadata fields.

---

## 4. Other references (read-only or docs)

- **core/core.py** — GET /api/config/core (read); PATCH (write via `update_yaml_preserving_comments`); other refs are comments or error messages.
- **main.py** — `read_config`, `update_core_config` (uses `update_yaml_preserving_comments`), doctor (read).
- **ui/homeclaw.py** — `read_config`, `update_config` (uses `update_yaml_preserving_comments`). Local `write_config` exists but is not used for core.yml.
- **llm/llmService.py**, **base/util.py** — Read via `Util().config_path()` + `core.yml` or `CoreMetadata.from_yaml()`; no direct write.
- **Companion app (Flutter)** — Only calls GET and PATCH `/api/config/core`; no direct file access.

---

## 5. Why content might still seem to disappear

1. **ruamel not installed** — Then `CoreMetadata.to_yaml` and `update_yaml_preserving_comments` use the fallback. Fallback **merges** into loaded existing; if the file exists and is non-empty but load failed (e.g. parse error), we **skip the write** and log a warning so we never overwrite with a subset.
2. **Existing file already truncated** — If core.yml was ever overwritten by an old version of the code (before merge logic), restoring requires re-adding the missing keys (or restoring from git/backup). New writes will then only merge.
3. **Companion app** — Sends only the keys it knows about. Server merges that into the **full** loaded file and writes the full result, so unknown keys (e.g. `hybrid_router`, `main_llm_mode`) are preserved.

---

## 6. Safeguards (no fields removed)

- **CoreMetadata.to_yaml()** — Ruamel path: always load file (treat `None` as `{}`), merge `core_dict`, then write. Fallback: if file exists and is non-empty but we got `existing == {}` (load failed), **skip write** and log a warning so we never wipe core.yml.
- **update_yaml_preserving_comments()** — Same skip-write guard in fallback when file exists and is non-empty but load returned empty.

---

## 7. Mix mode and main_llm

When **main_llm_mode: mix**, routing uses **main_llm_local** and **main_llm_cloud** only. The **main_llm** key is **not** used for which model handles each request: the hybrid router picks local vs cloud per request and the code calls `main_llm_for_route("local")` or `main_llm_for_route("cloud")`, which read `main_llm_local` and `main_llm_cloud`. So having **main_llm** set (e.g. to `local_models/main_vl_model_4B`) does **not** affect mix mode; it is still used as the default when no route is given and for a few legacy paths (e.g. vision fallback, set_api_key_for_llm when not mix). Keeping **main_llm** in the file is correct and safe.

---

## 8. Restore from reference (core.yml.reference)

Code **only** writes to **config/core.yml**. Nothing ever writes to **config/core.yml.reference**.

- **Backup:** When your core.yml is correct and full, copy it to the reference file so you can restore later:
  ```bash
  cp config/core.yml config/core.yml.reference
  ```
- **Restore:** If core.yml is broken or truncated, copy the reference back:
  ```bash
  cp config/core.yml.reference config/core.yml
  ```
- **core.yml.reference** is a normal YAML file; keep it under version control or backup so it stays a known-good full config. The repo may ship a minimal `core.yml.reference` with a comment; replace it with your full backup if you use this restore flow.

---

## 9. Checklist

- [x] Core PATCH merges body into full loaded config, then passes full config to `update_yaml_preserving_comments`.
- [x] `CoreMetadata.to_yaml` merges into existing file (ruamel or fallback); never overwrites with only `core_dict` keys.
- [x] Fallback in both paths skips write when file is non-empty but load returned {} (avoids removing fields).
- [x] main.py and ui/homeclaw use `update_yaml_preserving_comments` for core config updates.
- [x] No code writes to `core.yml.reference`; only `core.yml` is ever written.
- [ ] Ensure `ruamel.yaml` is in `requirements.txt` and installed so comment preservation is used.
