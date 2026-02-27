# Step 3: Memory (MD) paths per (user_id, friend_id) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) Implementation step 3.

**Goal:** Switch MD memory paths to per **(user_id, friend_id)**:
- `memories/{user_id}/{friend_id}/agent_memory.md` — long-term curated memory for this pair.
- `memories/{user_id}/{friend_id}/memory/YYYY-MM-DD.md` — daily/short-term notes.

Load/write for agent_memory and daily use these paths; append_* tools and bootstrap injection use the same paths. Existing data is migrated from old single-path layout to (user_id, HomeClaw). **Chat/session keys unchanged** (Step 8).

---

## 1. What was implemented

### 1.1 base/workspace.py

- **\_sanitize_friend_id(friend_id)** — Normalizes friend_id for paths; default `"HomeClaw"` when empty/None; sanitizes path-unsafe chars. Never raises.
- **get_agent_memory_file_path(..., friend_id=None)** — Per (user_id, friend_id): `workspace_dir/memories/{user_id}/{friend_id}/agent_memory.md`. Global user (system/companion) or missing uid: unchanged (global path).
- **ensure_agent_memory_file_exists(..., friend_id=None)** — Creates file under new path; runs **migration**: if new path missing and old `agent_memory/{user_id}.md` exists, copies content to `memories/{user_id}/{friend_id}/agent_memory.md`.
- **load_agent_memory_file(..., friend_id=None)** — Loads from per-(user_id, friend_id) path; runs migration before read when applicable.
- **clear_agent_memory_file(..., friend_id=None)** — Clears per-(user_id, friend_id) file.
- **get_daily_memory_dir(..., friend_id=None)** — Per (user_id, friend_id): `workspace_dir/memories/{user_id}/{friend_id}/memory/`. Global: unchanged.
- **get_daily_memory_path_for_date**, **ensure_daily_memory_file_exists**, **load_daily_memory_for_dates**, **append_daily_memory**, **clear_daily_memory_for_dates** — All take **friend_id**; daily path is `memories/{uid}/{fid}/memory/YYYY-MM-DD.md`. **Migration**: if new dir empty and old `daily_memory/{user_id}/` has files, copies YYYY-MM-DD.md into new dir.

### 1.2 base/agent_memory_index.py

- **get_agent_memory_files_to_index(..., friend_id=None)** — Returns files for one (user_id, friend_id) scope. Relative paths: `memories/{uid}/{fid}/agent_memory.md`, `memories/{uid}/{fid}/memory/YYYY-MM-DD.md` (or global AGENT_MEMORY.md, memory/YYYY-MM-DD.md).
- **sync_agent_memory_to_vector_store(..., scope_pairs=None)** — Replaces **system_user_ids** with **scope_pairs**: list of `(user_id, friend_id)`. When None: index global only. Each scope gets **scope_key** = `""` (global) or `"uid|fid"` for vector store payload and delete_where.
- **_scope_key_for_pair(uid, fid)** — Returns scope_key for (user_id, friend_id); used by sync and by Core search.

### 1.3 core/core.py

- **Startup sync** — Builds **scope_pairs** from users: for each user, for each friend in `user.friends`, add `(user_id, friend_name)`; if no friends, add `(user_id, "HomeClaw")`. Adds global `(None, "HomeClaw")`. Calls sync_agent_memory_to_vector_store(scope_pairs=scope_pairs).
- **Bootstrap / legacy inject** — All **load_agent_memory_file** and **load_daily_memory_for_dates** calls pass **friend_id** from request: `(str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw"`.
- **re_sync_agent_memory(system_user_id, friend_id=None)** — Takes **friend_id**; calls sync with scope_pairs=`[(system_user_id, fid)]`.
- **search_agent_memory(..., friend_id=None)** — Filters by **scope_key** = _scope_key_for_pair(system_user_id, friend_id).
- **get_agent_memory_file(..., friend_id=None)** — Resolves paths for `AGENT_MEMORY.md`, `memories/uid/fid/agent_memory.md`, `memories/uid/fid/memory/YYYY-MM-DD.md`, `agent_memory/uid.md`, `memory/YYYY-MM-DD.md`, `daily_memory/uid/YYYY-MM-DD.md` using (system_user_id, friend_id).

### 1.4 tools/builtin.py

- **append_agent_memory** — Gets **friend_id** from context (`(str(getattr(context, "friend_id", None) or "").strip() or "HomeClaw"`); passes to get_agent_memory_file_path and re_sync_agent_memory.
- **append_daily_memory** — Passes **friend_id** from context to append_daily_memory and re_sync_agent_memory.
- **agent_memory_search** — Passes **friend_id** from context to core.search_agent_memory.
- **agent_memory_get** — Passes **friend_id** from context to core.get_agent_memory_file.

### 1.5 memory_routes.py

- **No change.** Reset still clears **global** agent_memory and daily (no user_id/friend_id). Per-user/friend reset is Step 13 (endpoints audit).

---

## 2. Migration (one-time)

- **Agent memory:** On first load/ensure for (user_id, friend_id), if `memories/{user_id}/{friend_id}/agent_memory.md` does not exist but `agent_memory/{user_id}.md` exists, content is copied to the new path. Old file is left in place (no delete).
- **Daily memory:** On first ensure for (user_id, friend_id), if `memories/{user_id}/{friend_id}/memory/` is empty but `daily_memory/{user_id}/` has .md files, those files are copied into the new directory. Old dir is left in place.

---

## 3. Robustness and safety

- **friend_id default:** All call sites default to `"HomeClaw"` when friend_id is None/empty; _sanitize_friend_id and str().strip() used so non-string never causes .strip() to raise.
- **Path sanitization:** _sanitize_friend_id and _sanitize_system_user_id remove path-unsafe chars; no directory traversal.
- **Migration:** Runs inside ensure/load; try/except and debug logging only; never raises. If migration fails, new path is used (empty or created).
- **Scope key:** scope_key is `""` (global) or `"uid|fid"`; safe for vector store filters and delete_where.

---

## 4. What Step 3 does *not* do

- **No chat/session key changes** (Step 8).
- **No /memory/reset per (user_id, friend_id)** — reset still clears global only; Step 13 will add user_id/friend_id to reset.
- **No RAG/KB/cron key changes** (Steps 9–10).

---

## 5. Files touched

| File | Change |
|------|--------|
| **base/workspace.py** | _sanitize_friend_id; get_agent_memory_file_path, ensure/load/clear_agent_memory_file, get_daily_memory_dir, get_daily_memory_path_for_date, ensure_daily_memory_file_exists, load_daily_memory_for_dates, append_daily_memory, clear_daily_memory_for_dates: + friend_id; migration helpers. |
| **base/agent_memory_index.py** | get_agent_memory_files_to_index + friend_id; sync_agent_memory_to_vector_store scope_pairs + _scope_key_for_pair; rel paths memories/uid/fid/... |
| **core/core.py** | Startup: scope_pairs from users+friends; bootstrap/legacy: friend_id from request; re_sync_agent_memory + friend_id; search_agent_memory + friend_id; get_agent_memory_file + friend_id, path resolution for memories/... |
| **tools/builtin.py** | append_agent_memory, append_daily_memory, agent_memory_search, agent_memory_get: pass context.friend_id (default HomeClaw). |

---

## 6. Review (logic + robustness)

- **Logic:** All agent/daily paths use (user_id, friend_id); channels and default = HomeClaw; bootstrap and tools pass friend_id from request/context; sync uses scope_pairs from users+friends; search/get filter by scope_key. Migration runs on first use and copies old → new without deleting. ✓
- **Robustness:** _sanitize_friend_id and _sanitize_system_user_id never raise (try/except, str() before strip); all workspace helpers have try/except or safe defaults; migration is best-effort (debug log only); Core scope_pairs normalizes uid/fid to strings so non-string from config never crashes; get_agent_memory_file path parsing is in try/except with fallback to Path(ws_dir)/path. ✓

**Step 3 is complete.** Next: Step 4 (Profile path and scope).
