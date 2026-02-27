# Step 5: Sandbox — auto-create all folders — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) Implementation step 5 and §6.

**Goal:** Extend `ensure_user_sandbox_folders` so that at startup we create:
- **Per user:** `homeclaw_root/{user_id}`, `downloads`, `documents`, `output`, `work`, `share` (user’s share).
- **Per (user_id, friend_id):** `homeclaw_root/{user_id}/{friend_id}`, `{friend_id}/output`, `{friend_id}/knowledge`.
- **Global:** `homeclaw_root/share`, and if companion: `homeclaw_root/companion`, `companion/output`.

We do **not** auto-create `identity.md`; only directories. No crash on mkdir failure; log only.

---

## 1. What was implemented

### 1.1 base/workspace.py

- **_sanitize_subdir(name, default)** — Sanitizes a subdir name for path use (path-unsafe chars replaced). Never raises.
- **ensure_user_sandbox_folders** extended with:
  - **User-level subdirs:** `downloads_subdir`, `documents_subdir`, `work_subdir`, `user_share_subdir` (defaults: downloads, documents, work, share). For each user we create: `{user_id}/output`, `{user_id}/knowledgebase`, `{user_id}/downloads`, `{user_id}/documents`, `{user_id}/work`, `{user_id}/share`.
  - **Per-friend:** Optional **friends_by_user: Optional[Dict[str, List[str]]]** = None. When provided, for each (user_id, list of friend names) we create `{user_id}/{friend_id}`, `{friend_id}/output`, `{friend_id}/knowledge` (friend output and knowledge subdirs configurable via **friend_output_subdir**, **friend_knowledge_subdir**).
  - **friends_map** is built from `friends_by_user` with keys sanitized by `_sanitize_system_user_id` so they match the `uid` used in the loop; friend names are sanitized with `_sanitize_friend_id`. Non-dict or invalid entries are skipped; no exception propagates.
- All mkdir calls remain in try/except; OSError is logged and we continue. Top-level Exception is caught and logged. Never raises.

### 1.2 core/core.py

- At startup, when `homeclaw_root` is set:
  - Build **user_ids** and **friends_by_user** from `Util().get_users()`: for each user, `uid = (id or name)` normalized to string; for each user’s `friends` list, collect `friend.name` (normalized to string, default "HomeClaw").
  - Call **ensure_user_sandbox_folders(root_str, user_ids, friends_by_user=friends_by_user)**.

### 1.3 config_api and other callers

- **config_api** still calls `ensure_user_sandbox_folders(root_str, [uid])` with a single user when adding/updating a user; **friends_by_user** is omitted so only that user’s base dirs (and user-level subdirs) are created. Per-friend dirs for that user can be created on next full startup or by a future “sync sandbox” call. No change required for backward compatibility.

---

## 2. Robustness and safety

- **friends_by_user** is only used when `isinstance(friends_by_user, dict)`; building **friends_map** uses try/except per key and skips invalid entries. Friend names are sanitized with `_sanitize_friend_id` (never raises).
- All new subdir names go through **_sanitize_subdir** so path-unsafe characters are replaced. No directory traversal.
- No new code path raises; existing “never raises; log on mkdir failure” behavior is preserved.

---

## 3. Files touched

| File | Change |
|------|--------|
| **base/workspace.py** | _sanitize_subdir; ensure_user_sandbox_folders: user-level downloads/documents/work/share, friends_by_user and per-friend dirs (output, knowledge). |
| **core/core.py** | Startup: build friends_by_user from users and pass to ensure_user_sandbox_folders. |

---

## 4. Share folder (global vs user)

- **homeclaw_root/share/** is the **global** share (for all users). File tools: when the user says "share" or "shared folder", use path **"share"** or **"share/..."**; resolution routes to homeclaw_root/share/ (see _resolve_file_path use_share and shared_dir). Logic is correct and stable.
- **homeclaw_root/{user_id}/share/** is the user-level share (shared among that user's friends only); access by path "share" under user sandbox would conflict with global; path resolution treats "share" as global only, so "share" always = all-users share.

---

## 5. Review (logic + robustness)

- **Logic:** Per-user and per-friend dirs created at startup; friends_by_user built from user.yml; default path = user sandbox root; path "share" = global share for all users; path "{FriendName}/..." = that friend's folder under user. ✓
- **Robustness:** ensure_user_sandbox_folders never raises; friends_map built with try/except and sanitization; all mkdir in try/except; path resolution uses existing safe patterns; tool descriptions clarify share = global. ✓

**Step 5 is complete.** Next: Step 6 (Friend identity — identity.md).
