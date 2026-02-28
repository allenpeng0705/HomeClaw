# Portal: System setting copy and previous backup

**Goal:** (1) Keep one persistent **system/original** copy of each config file; user can **restore to system** at any time. (2) Keep **one previous** backup before each change; user can **revert to previous** to undo the last change.

---

## 1. Layout

- **Current config:** `config/core.yml`, `config/llm.yml`, etc. (the live files Core and Portal use).
- **System copy (original):** `config/system/core.yml`, `config/system/llm.yml`, …  
  - Never changed by normal edits. Only updated on **system upgrade** (explicit “Save current as system default” or installer/upgrade script).
  - If missing, can be created once by copying current → system (first-run bootstrap).
- **Previous backup:** `config/core.yml.previous`, `config/llm.yml.previous`, …  
  - Single file per config: the state **before the last write**. Overwritten each time we are about to apply a change (so “revert” goes back one step only).

---

## 2. Operations

| Operation | Meaning |
|-----------|--------|
| **Restore to system** | Copy `config/system/<name>.yml` → `config/<name>.yml`. System copy must exist. |
| **Revert to previous** | Copy `config/<name>.yml.previous` → `config/<name>.yml`. Previous backup must exist. |
| **Before each PATCH** | Copy current `config/<name>.yml` → `config/<name>.yml.previous` (overwrite), then apply the merge. |
| **Save current as system** (system upgrade) | Copy `config/<name>.yml` → `config/system/<name>.yml`. Only when user or installer explicitly requests it. |
| **Bootstrap system** | If `config/system/<name>.yml` does not exist and `config/<name>.yml` exists, copy current → system once (so “restore to system” is defined). Optional; can be done on first Portal run or first restore attempt. |

---

## 3. Invariants

- **System copy:** Never overwritten by normal config edits. Only by “Save current as system” or upgrade process.
- **Previous backup:** Only the last version before the most recent write. One level of undo.
- **Current:** The only file Core and the rest of the app read; all edits (merge) apply to current.

---

## 4. API (Portal)

- `POST /api/portal/config/<name>/restore-system` — Restore to system copy.
- `POST /api/portal/config/<name>/revert-previous` — Revert to previous backup.
- `POST /api/portal/config/<name>/save-as-system` — Save current as system (system upgrade).
- Before any `PATCH /api/config/<name>`: call backup_previous(name) then perform merge.

Implementation: `portal/config_backup.py` with:
- `ensure_system_copy(name)` — bootstrap system copy from current if missing.
- `backup_previous(name)` — copy current → `.previous` (call before each PATCH).
- `prepare_for_update(name)` — ensure system copy + backup previous; call this before applying any config PATCH.
- `restore_to_system(name)` — copy system → current.
- `revert_to_previous(name)` — copy `.previous` → current.
- `save_current_as_system(name)` — copy current → system (system upgrade).
- `has_system_copy(name)`, `has_previous_backup(name)` — for UI to show/hide Restore / Revert buttons.

Paths: system = `config/system/<name>.yml`, previous = `config/<name>.yml.previous`. All functions never raise; return bool where applicable.
