# Step 4: Profile path and scope — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) Implementation step 4 and §10.

**Goal:** Store profile under **(user_id, HomeClaw)**. Update profile load/save to use that path. Ensure **only HomeClaw** uses profile in the prompt (no profile injection when the active friend is Sabrina or another friend).

---

## 1. What was implemented

### 1.1 base/profile_store.py

- **Path:** Profile file is now **profiles/{user_id}/HomeClaw.json** (per (user_id, HomeClaw)). Legacy path **profiles/{user_id}.json** is still supported for migration.
- **_profile_path(dir_path, safe_id)** — Returns `dir_path / safe_id / "HomeClaw.json"`.
- **_legacy_profile_path(dir_path, safe_id)** — Returns `dir_path / "{safe_id}.json"` for migration.
- **get_profile(system_user_id, base_dir)** — Reads from _profile_path; if file missing, tries _legacy_profile_path and **migrates** (copy to new path) then returns data. Never raises; returns {} on error.
- **update_profile(...)** — Writes to _profile_path; ensures `path.parent.mkdir(parents=True, exist_ok=True)`. Wrapped in try/except so failures are logged and do not crash Core.
- **clear_all_profiles(base_dir)** — Removes both top-level `*.json` (legacy) and subdir `*/HomeClaw.json` (new). Returns count; never raises.
- **_safe_user_id** — Wrapped in try/except; returns "_unknown" on any error so path building never crashes.
- **get_profile_dir** — try/except with fallback to Util().data_path()/profiles so it never raises.

### 1.2 core/core.py

- **Profile injection into system prompt** — "## About the user" is appended **only when** the active friend is HomeClaw. Added:
  - `_fid_for_profile = (str(getattr(request, "friend_id", None) or "").strip() or "HomeClaw") if request else "HomeClaw"`
  - Condition: `... and _fid_for_profile == "HomeClaw"`.
- When the user is chatting with Sabrina (or any non-HomeClaw friend), profile is **not** injected. When with HomeClaw (or channel, or default), profile is injected as before.

### 1.3 Other callers

- **Location lookups** (profile_data.get("location")) in core still use `get_profile(user_id or "", base_dir=...)`; they read the same (user_id, HomeClaw) profile. No API change.
- **profile_update / profile_get tools** — Still call get_profile/update_profile with system_user_id; path change is internal to profile_store. No change needed.

---

## 2. Migration

- On first **get_profile** for a user, if **profiles/{user_id}/HomeClaw.json** does not exist but **profiles/{user_id}.json** exists, the file is read, written to the new path, and returned. Legacy file is left in place (caller can delete later or leave for backup).
- **clear_all_profiles** removes both legacy and new layout files.

---

## 3. Robustness and safety

- All profile_store functions that can fail are wrapped in try/except; get_profile and clear_all_profiles return empty/count and never raise. update_profile returns None and never raises.
- friend_id for profile injection is normalized with str() before .strip() so non-string never crashes Core.
- Profile is only injected when _fid_for_profile == "HomeClaw", so no cross-friend leakage.

---

## 4. Files touched

| File | Change |
|------|--------|
| **base/profile_store.py** | Path to profiles/{id}/HomeClaw.json; migration from legacy; _safe_user_id and get_profile_dir never raise; clear_all_profiles clears both layouts. |
| **core/core.py** | Profile block injected only when request.friend_id (normalized) is "HomeClaw". |

---

## 5. Review (logic + robustness)

- **Logic:** Profile path is (user_id, HomeClaw); only HomeClaw gets profile in the prompt; migration from legacy path on first read; clear removes both layouts. ✓
- **Robustness:** get_profile/update_profile empty-check use str(system_user_id or "").strip() so non-string never raises; get_profile_dir and _safe_user_id have try/except; clear_all_profiles checks dir_path.exists() and is_dir() before iterdir() so missing dir never crashes; format_profile_for_prompt guards against non-dict and safe max_chars parsing. ✓

**Step 4 is complete.** Next: Step 5 (Sandbox: auto-create all folders).
