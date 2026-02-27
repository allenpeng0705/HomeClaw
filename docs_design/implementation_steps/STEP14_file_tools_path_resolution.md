# Step 14: File tools and path resolution — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 14; [FolderSemanticsAndInference.md](../FolderSemanticsAndInference.md).

**Goal:** Path resolution already supports user_id (sandbox_root = homeclaw_root/{user_id}). Ensure **friend_id** paths work (e.g. `{friend_id}/output/`, `{friend_id}/knowledge/`) and default path = user root. Reject path traversal so Core never escapes the sandbox. Never crash Core.

---

## 1. What was implemented

### 1.1 Path resolution (already in place)

- **User sandbox root:** `sandbox_root = homeclaw_root/{user_id}/` (from sandbox_paths.json or get_sandbox_paths_for_user_key). All relative paths are resolved under this base.
- **Friend paths:** Relative paths like `Sabrina/output/report.pdf` or `HomeClaw/output/` resolve to `homeclaw_root/{user_id}/Sabrina/output/report.pdf`. No code change needed; base is user root, so `{friend_id}/output/` and `{friend_id}/knowledge/` already work.
- **Default path:** Empty or omitted path → user sandbox root (`.`). See _resolve_file_path (path_arg = "." when empty).
- **Share:** Path `share` or `share/...` → homeclaw_root/share/ (global).

### 1.2 Path traversal safety (Step 14)

- **_resolve_relative_to_absolute_via_sandbox_json:** After resolving `full = (base_absolute / rest).resolve()`, check `full.relative_to(base_absolute)`; on ValueError (escape) return None so caller returns a safe error message.
- **_resolve_file_path (fallback branch):** After resolving full, check `full.relative_to(effective_base.resolve())`; on ValueError return None.
- Ensures paths like `../../../etc/passwd` or `../other_user/` never resolve to a path outside the sandbox or share base.

### 1.3 Tool descriptions

- file_read, document_read, file_understand, file_write (and related) already describe per-friend paths: "User sandbox: ...; per friend: {FriendName}/output/, {FriendName}/knowledge/." No change.

### 1.4 Workspace

- **ensure_user_sandbox_folders** (base/workspace.py) already creates per (user_id, friend_id): `{user_id}/{friend_id}/`, `{friend_id}/output/`, `{friend_id}/knowledge/`. No change.

---

## 2. Summary

- **user_id:** Used to select sandbox root (homeclaw_root/{user_id}/).
- **friend_id paths:** Use relative path `{friend_id}/output/` or `{friend_id}/knowledge/` under that root; resolution already correct.
- **Default:** User root when path empty or ".".
- **Safety:** Path traversal rejected; _resolve_file_path and _resolve_relative_to_absolute_via_sandbox_json return None on escape.

---

## 3. Files touched

| File | Change |
|------|--------|
| **tools/builtin.py** | _resolve_relative_to_absolute_via_sandbox_json: after resolve, full.relative_to(base_absolute) → None on ValueError. _resolve_file_path (fallback): full.relative_to(effective_base.resolve()) → None on ValueError. |

---

## 4. Review

- **Logic:** Path resolution supports user_id and friend paths under user root; default = user root. ✓
- **Robustness:** Path traversal rejected via `full.relative_to(base)` (ValueError → None); same check in both primary and fallback resolution; cross-drive or invalid paths on Windows also yield ValueError and are rejected. No new code path raises; Core never crashes. ✓

**Step 14 is complete.** Next: [Step 15 (Docs and config examples)](STEP15_docs_config_examples.md).
