# Step 6: Friend identity (identity.md) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) §7 and implementation step 6.

**Goal:** When the current request is for a **friend** (not HomeClaw) that has optional **identity** set in user.yml, Core reads the friend’s identity Markdown file from `homeclaw_root/{user_id}/{friend_id}/{identity_filename}` and injects it into the **same prompt block as “who”** (the companion identity section). If the file is missing or invalid, skip silently; never crash Core. Cap length (e.g. 12k chars). Backward compatibility: legacy companion user with only `User.who` (no friends-based identity) still uses the existing who block.

---

## 1. What was implemented

### 1.1 base/workspace.py

- **_sanitize_identity_filename(name)** — Returns a safe filename for the identity file (no path separators). Default `identity.md`. Never raises.
- **load_friend_identity_file(homeclaw_root, user_id, friend_id, identity_filename=None, max_chars=12000)** — Loads the friend identity markdown from `homeclaw_root/{user_id}/{friend_id}/{identity_filename}`. Uses existing _sanitize_system_user_id and _sanitize_friend_id for path segments; identity_filename sanitized with _sanitize_identity_filename. If file missing or any error, returns `""`. Content read as UTF-8 (errors="replace"), stripped, and capped at max_chars (clamped 500–50000). Never raises; logs debug on exception.

### 1.2 core/core.py

- **Import:** `load_friend_identity_file` from base.workspace.
- **Resolve current friend:** After resolving _current_user_for_identity, resolve _current_friend from request: normalize request.friend_id (default "homeclaw"); from _current_user_for_identity.friends find the friend whose name (normalized) matches. If _current_friend exists and is not HomeClaw and (friend.who is a non-empty dict or friend.identity is not None), set _companion_with_who = True so the identity block is built from the friend (and workspace Identity is skipped). Else legacy: if user type is companion and user.who is set, _companion_with_who = True as before.
- **Identity block:** When _companion_with_who and _current_user_for_identity:
  - Prefer friend: if _current_friend and not HomeClaw, use friend.who and friend name for the block; else use user.who and user name (legacy).
  - Build the same “who” template as before (description, name, gender, roles, personalities, language, response_length, stay-in-character line). If friend has no who dict but has identity file, build a minimal block (name + stay-in-character line).
  - If _current_friend and friend.identity is not None, call load_friend_identity_file(homeclaw_root, system_user_id, friend.name, friend.identity, max_chars=12000) and append the returned content to the same Identity block (after a blank line). Empty or missing file is skipped.

### 1.3 Example and config

- **config/examples/friend_identity.md** — Example content already present; users copy to `homeclaw_root/{user_id}/{friend_id}/identity.md` (or the filename set in user.yml `identity`).

---

## 2. Robustness and safety

- **load_friend_identity_file:** All inputs sanitized; path built from sanitized segments; file read in try/except; returns "" on any failure; max_chars converted with try/except (TypeError/ValueError → default 12000) so None or invalid types never raise; cap clamped 500–50k; never raises.
- **Friend resolution:** _current_friend is resolved inside the same try/except as _current_user_for_identity; invalid or missing friends list is skipped; no new code path raises.
- **Identity injection:** Wrapped in try/except; debug log on failure; system_parts still appended only when content was built successfully.

---

## 3. Files touched

| File | Change |
|------|--------|
| **base/workspace.py** | _sanitize_identity_filename; load_friend_identity_file. |
| **core/core.py** | Import load_friend_identity_file; resolve _current_friend; build identity from friend.who + optional identity file; legacy user.who preserved. |

---

## 4. Review (logic + robustness)

- **Logic:** Friend identity is read from homeclaw_root/{user_id}/{friend_id}/{filename}; content is appended to the same “who” block; “share” and path resolution unchanged; legacy companion user who block unchanged. ✓
- **Robustness:** Loader never raises; friend resolution and block building in try/except; missing file or empty identity = skip; cap length applied. ✓

**Step 6 is complete.** Next: Step 7 (Push from_friend, etc., per design).
