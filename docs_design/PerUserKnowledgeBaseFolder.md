# Per-user knowledge base folder — design

This doc has two parts: **(1) Review** of recent companion/user and client changes for correctness and robustness; **(2) Design** for a per-user "knowledgebase" folder that stays in sync with the knowledge base (add new files, remove when file is deleted).

---

## Part 1: Review of recent changes

### 1.1 Core: users and identity

| Area | What was checked | Result |
|------|------------------|--------|
| **check_permission** | No synthetic user; returns only (bool, User) from `get_users()` or (False, None). All call sites check `has_permission` and `user is not None` before using `user`. | **Correct.** No in-memory user creation; type is `Tuple[bool, Optional[User]]`. |
| **Identity (who)** | Resolve `_sys_uid`, `_companion_with_who`, `_current_user_for_identity` once; `_sys_uid` set before try so always defined. Workspace prefix uses `skip_identity=_companion_with_who`. Who block only when `_companion_with_who and _current_user_for_identity`; all `_who` access is defensive (isinstance, .get()). | **Correct and robust.** Failures are caught; no unbound variables. |
| **User.from_yaml / to_yaml** | from_yaml returns [] on error; who only set when isinstance(who, dict). to_yaml writes who as-is. | **Correct.** Description and other who keys are preserved. |
| **GET/POST/PATCH users** | who accepted as dict; stored in User; no iteration over who keys. | **Correct.** |

### 1.2 Core: file sandbox

| Area | What was checked | Result |
|------|------------------|--------|
| **Per-user folder** | `_get_file_workspace_subdir(context)` uses `system_user_id` from ToolContext (set from request after check_permission). Path = `{homeclaw_root}/{user_id}/`. | **Correct.** Every user gets a folder under homeclaw_root. |
| **Share folder** | Paths `share/...` resolve to `{homeclaw_root}/share/` for any user. | **Correct.** All users can access share. |

### 1.3 Companion app (Flutter)

| Area | What was checked | Result |
|------|------------------|--------|
| **CoreService.sendMessage** | Takes `required String userId`; body has `user_id: userId`, `channel_name: 'companion'`. No isFriendChat, no session_id/conversation_type. | **Correct.** |
| **FriendListScreen** | Fetches `getConfigUsers()`, shows one tile per user; tap opens ChatScreen(userId, userName). | **Correct.** |
| **ChatScreen** | Takes userId, userName; load/save/clear history by userId; sendMessage(userId: widget.userId); title = userName. | **Correct.** |
| **ChatHistoryStore** | Key = `chat_$userId`; load/save/clear(userId); clearAll() deletes all keys with prefix. | **Correct.** |
| **Settings** | Removed system identity picker and saveSystemUserId; no remaining references to systemUserId. | **Correct.** |

### 1.4 WebChat / homeclaw-browser

| Area | What was checked | Result |
|------|------------------|--------|
| **Proxy** | GET /api/core/users forwards to CORE_URL/api/config/users with auth. | **Correct.** |
| **control-ui** | loadUsers() fetches /api/core/users, fills &lt;select id="user_id"&gt;. Payload: user_id + channel_name: 'companion'. No Assistant/Friend. | **Correct.** |

### 1.5 Robustness summary

- **No crash paths:** Identity block and user resolution are in try/except or use defensive get/None checks; check_permission never raises; from_yaml returns [] on error.
- **Same logic everywhere:** All messages have an owner user; user_id is always from user.yml (list → select → send).

---

## Part 2: Per-user knowledge base folder — design

### 2.1 Goal

- Every user has **one private folder** for “knowledge base” files: e.g. `{homeclaw_root}/{user_id}/knowledgebase/`.
- User can put files there; files received from channels or the companion app can be saved there. All of these become part of that user’s **private knowledge base** (chunked, embedded, searchable).
- A **sync process** runs periodically (or on demand):
  - **Add:** Scan the folder; for files that are supported and not yet in the KB, read content and add to the KB.
  - **Remove:** If a file that was in the KB is deleted from the folder, remove its chunks from the KB so the store does not grow without bound.

### 2.2 Paths and layout

- **Folder per user:**  
  `{homeclaw_root}/{user_id}/knowledgebase/`  
  Same `user_id` as used for sandbox and file tools (sanitized id/name from user.yml). Requires `homeclaw_root` to be set.

- **Received files:**  
  When the Core processes inbound with attachments (files/images/videos/audios), it can optionally **copy** (or move) supported document files into the requesting user’s `knowledgebase/` folder so the next sync will pick them up. Exact policy (e.g. only “document” types, only when user asks, or always for documents) can be configurable.

- **Share folder:**  
  Unchanged. `share/` remains shared; the **knowledgebase** folder is per-user only.

### 2.3 Sync logic (high level)

1. **List files on disk**  
   Recursively (or one level, configurable) under `{homeclaw_root}/{user_id}/knowledgebase/`.  
   Only consider **allowed extensions** (e.g. `.md`, `.txt`, `.pdf`, `.docx`, `.html`, …) and **max file size** to avoid OOM.

2. **List current KB sources for this user**  
   Use existing `list_sources(user_id)`. Filter to `source_type == "folder"` (or a dedicated type like `"kb_folder"`).  
   Each such source has a `source_id` = path relative to the user’s knowledgebase folder (e.g. `doc.pdf`, `notes/readme.md`).

3. **Add new or updated files**  
   For each file on disk:
   - `source_id` = path relative to `knowledgebase/` (stable and unique per user).
   - If this `source_id` is not in the KB, or if “re-sync on mtime change” is enabled and file mtime &gt; last add time:
     - Read content (reuse existing document_read / file-understanding pipeline).
     - If this source_id was already in the KB, call `remove_by_source_id(user_id, source_id)` first.
     - Call `add(user_id, content, source_type="folder", source_id=source_id)`.

4. **Remove deleted files from KB**  
   For each KB source with `source_type == "folder"` (and same user_id):
   - If the file no longer exists at `knowledgebase/{source_id}` (or the full path derived from it), call `remove_by_source_id(user_id, source_id)`.

5. **Idempotency and errors**  
   - Sync should be safe to run repeatedly.  
   - Per-file errors (e.g. read failure, add failure) should be logged and not stop the rest of the sync.  
   - No crash: wrap in try/except; timeouts for read/add/remove.

### 2.4 Source id and type

- **source_type:** e.g. `"folder"` or `"kb_folder"` so we can distinguish “folder-synced” sources from other sources (document, web, url, manual). That allows:
  - **Removal rule:** Only consider `source_type == "folder"` when deciding what to remove because a file is missing.
  - **Listing:** Optional “list folder-synced sources” for UI or debugging.

- **source_id:** Path relative to the user’s knowledgebase directory, with a consistent separator (e.g. `/`). Examples: `doc.pdf`, `subdir/note.md`. This is stable across runs and unique per user per file.

### 2.5 When to run sync

- **Option A – Scheduled:** Cron (or Core’s internal scheduler) calls an endpoint or internal method at an interval (e.g. every 6 or 24 hours). Config: e.g. `knowledge_base.folder_sync.schedule` (cron expression) and `knowledge_base.folder_sync.enabled`.
- **Option B – On demand:** Endpoint `POST /knowledge_base/sync_folder` (or similar) that runs sync for the current user (or for a given user_id if admin). Useful for testing and “sync now” from UI.
- **Option C – After inbound with files:** When Core saves received documents into the user’s knowledgebase folder, optionally trigger a sync for that user (or queue it) so new files are indexed soon. Can be combined with A/B.

Recommendation: implement **A + B** first (schedule + on-demand); add C later if needed.

### 2.6 Config (core.yml)

Under `knowledge_base:` (or a dedicated subsection), for example:

```yaml
knowledge_base:
  enabled: true
  # ... existing keys (backend, chunk_size, etc.) ...

  # Per-user folder sync (optional)
  folder_sync:
    enabled: false
    # Folder name under each user's sandbox: {homeclaw_root}/{user_id}/{folder_name}/
    folder_name: knowledgebase
    # Cron expression; empty = only on-demand via API
    schedule: "0 */6 * * *"
    # Allowed extensions (lowercase)
    allowed_extensions: [".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".rst"]
    max_file_size_bytes: 5_000_000
    # If true, re-add when file mtime is newer than last add (requires tracking last mtime or “last sync” per file)
    resync_on_mtime_change: true
```

- If `folder_sync.enabled` is false, no scan/sync runs.  
- If `homeclaw_root` is not set, folder sync is skipped (or log warning and skip).

### 2.7 Saving received files into the folder (optional)

- When processing **inbound** (companion, WebChat, channels) with `files` (or document-type attachments), Core can:
  1. Save/copy each file to `{homeclaw_root}/{user_id}/knowledgebase/{original_filename}` (or a safe name if conflict).
  2. Rely on the next **scheduled or on-demand sync** to add it to the KB.

- Alternatively, do **not** auto-save to knowledgebase; only sync what the user (or another process) has put in the folder. Then “receiving from channels/companion” is handled by existing upload + optional “save to my knowledge base” (e.g. user asks to add to KB; we add and optionally write to folder for consistency). Design can support both; first phase can be “sync folder only,” then add “save inbound docs to folder” as an option.

### 2.8 Implementation outline

1. **Config**  
   Add `folder_sync` (and optional `folder_name`) under `knowledge_base` in core.yml; parse in CoreMetadata / config loader.

2. **Path helper**  
   `get_user_knowledgebase_dir(user_id)` → `Path(homeclaw_root) / sanitize(user_id) / folder_name` (e.g. `knowledgebase`). Return None if homeclaw_root not set.

3. **Sync function (per user)**  
   - `sync_user_kb_folder(user_id)` (async or sync, wrapped in try/except):
     - Get user’s knowledgebase dir; if missing, return.
     - List files (respect allowed_extensions, max_file_size).
     - Call KB `list_sources(user_id)`, filter by source_type `"folder"`.
     - **Remove:** For each folder source_id where file does not exist, call `remove_by_source_id(user_id, source_id)`.
     - **Add/update:** For each file on disk, compute relative source_id; if not in list_sources or (resync_on_mtime_change and mtime &gt; last known), read content (reuse document_read or file-understanding), then add (removing old by source_id first if updating).

4. **Scheduler**  
   If `folder_sync.enabled` and `folder_sync.schedule` is set, register a job that, at schedule time, gets all user ids (from user.yml or from “users who have a knowledgebase dir”) and runs `sync_user_kb_folder(user_id)` for each. One failure per user should not stop others.

5. **Endpoint**  
   `POST /knowledge_base/sync_folder` (auth required): body optional `user_id` (default: current request user). Calls `sync_user_kb_folder(user_id)`.

6. **Received files (phase 2)**  
   In inbound file handling, if `folder_sync.enabled` and config says “save inbound docs to user’s knowledgebase folder,” copy supported documents to the user’s knowledgebase dir with a safe filename, then optionally trigger sync for that user or rely on next scheduled run.

### 2.9 Summary

- **One folder per user:** `{homeclaw_root}/{user_id}/knowledgebase/`.
- **Sync:** Periodically and/or on demand: add new/changed files (source_type `"folder"`, source_id = relative path), remove KB entries when the file is deleted.
- **Stable and bounded:** Only folder-synced sources are removed when files disappear; sync is idempotent and fault-tolerant so the system stays correct and does not grow without bound.
