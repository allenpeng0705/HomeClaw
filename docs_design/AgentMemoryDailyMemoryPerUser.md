# AGENT_MEMORY and daily memory: per-user (markdown)

**Conclusion:** **AGENT_MEMORY** and **daily memory** are **per-user** when a user is present; they remain **markdown files** (`.md`). For the **company app** (no user / companion / system), the **global** paths are still used so behavior is unchanged.

---

## Current behavior (implemented)

| Context | AGENT_MEMORY | Daily memory |
|---------|--------------|---------------|
| **With user** (`system_user_id` set, not system/companion) | Per-user: `workspace_dir/agent_memory/{user_id}.md` | Per-user: `workspace_dir/daily_memory/{user_id}/YYYY-MM-DD.md` |
| **Company app** (no user, or system/companion) | Global: `workspace_dir/AGENT_MEMORY.md` (or `agent_memory_path`) | Global: `workspace_dir/memory/YYYY-MM-DD.md` (or `daily_memory_dir`) |

- Both are **markdown files** in all cases.
- Paths are resolved with `system_user_id`: when it is set and not `"system"`/`"companion"`, per-user paths above are used; otherwise global paths are used.
- Tools `append_agent_memory` and `append_daily_memory` use `context.system_user_id`. Bootstrap injection uses `request.system_user_id`. Vector search and `agent_memory_get` filter or resolve by user.

---

## No information leak between users

- Each user's appends go to their own markdown file(s). Search and bootstrap only see that user's content (or global when no user).
- Company app continues to use a single global AGENT_MEMORY and global daily memory directory.

---

## Implementation notes

- **Paths:** `base/workspace.py`: `get_agent_memory_file_path`, `get_daily_memory_dir`, and helpers take optional `system_user_id`; per-user layout is `agent_memory/{user_id}.md` and `daily_memory/{user_id}/YYYY-MM-DD.md` (all markdown).
- **Indexing:** `base/agent_memory_index.py`: chunks are stored with payload `system_user_id` ("" for global); search filters by that key. Startup sync indexes global + all users from `user.yml`; re_sync after append indexes only that user.
- **Companion without user:** When `system_user_id` is None, `"system"`, or `"companion"`, global paths and global index scope are used.
