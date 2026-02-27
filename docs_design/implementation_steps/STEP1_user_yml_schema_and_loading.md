# Step 1: user.yml schema and loading — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) §2 (user.yml structure), Implementation step 1.

**Goal:** Extend user.yml to support a **friends** list and optional **username**/**password**. Parse and serialize without changing routing yet. Keep Core and Companion stable; never crash on bad data.

---

## 1. What was implemented

### 1.1 New type: `Friend` (base/base.py)

- **Friend** dataclass: `name` (str, required), `relation` (optional str or list), `who` (optional dict), `identity` (optional str).
- **name** = friend_id (used later for paths and storage). **identity**: `None` = do not read any file; `""` or `"identity.md"` = read default file; `"other.md"` = read that filename in friend root (per design: empty or one .md filename; default when present but empty = identity.md).

### 1.2 User extended (base/base.py)

- **username**: optional str (for Companion login).
- **password**: optional str (stored as in yaml; hashing can be added later).
- **friends**: optional `List[Friend]`. If missing or empty after parsing, defaults to `[Friend(name='HomeClaw')]`. **HomeClaw is always first:** if the first friend’s name is not `"HomeClaw"`, we insert `HomeClaw` at index 0.

### 1.3 Parsing (User.from_yaml)

- Read **username**, **password**, **friends** from each user dict.
- **friends**: `User._parse_friends(raw)`:
  - Input: list of dicts (or non-list → treated as empty).
  - For each dict: **name** required (skip if missing/empty). **relation**, **who** (dict only), **identity**:
    - **identity**: missing → `None`. Boolean `True` → `"identity.md"`, `False` → `None`. String: stripped; if empty → `"identity.md"`, else use as filename.
  - If no valid friends after parsing → return `[Friend(name='HomeClaw')]`.
  - If list non-empty but first friend name (lower) ≠ `"homeclaw"` → insert `Friend(name='HomeClaw')` at 0.
- **Never raises:** `from_yaml` still returns `[]` on any top-level error. Per-user try/except unchanged. Inside `_parse_friends`, invalid entries are skipped; only valid `Friend` objects are appended.

### 1.4 Serialization (User.to_yaml)

- **username**, **password**: written only if present and non-empty.
- **friends**: `User._friends_to_dict_list(friends)` → list of dicts with keys `name`, and optionally `relation`, `who`, `identity` (only if set). Order preserved (HomeClaw first).

### 1.5 Config API (core/routes/config_api.py)

- **GET /api/config/users**: Response for each user includes **username** (if set). **friends** included as list of `{ name, relation, who, identity }`. **Password is never returned.**
- **POST /api/config/users**: Body may include **username**, **password**, **friends**. If **friends** omitted, new user gets `[Friend(name='HomeClaw')]`. Otherwise `User._parse_friends(body["friends"])` (same normalization as from_yaml).
- **PATCH /api/config/users/{user_name}**: Body may include **username**, **password**, **friends**. If a key is omitted, existing value is kept (e.g. `found.username`, `found.friends`).

### 1.6 Util.create_default_user (base/util.py)

- Replaced `User()` (invalid: `name` required) with `User(name="HomeClaw", email=[], phone=[], im=[])` so default user creation does not crash.

---

## 2. Files touched

| File | Change |
|------|--------|
| **base/base.py** | Added `Friend`; `User` + `username`, `password`, `friends`; `_parse_friends`, `_friends_to_dict_list`; `from_yaml` / `to_yaml` extended. |
| **core/routes/config_api.py** | GET: include `username`, `friends`; POST/PATCH: accept and persist `username`, `password`, `friends`; import `Friend`. |
| **base/util.py** | `create_default_user()`: use `User(name="HomeClaw", ...)` instead of `User()`. |

---

## 3. Backward compatibility and safety

- **Existing user.yml without `friends`:** Each user gets `friends = [Friend(name='HomeClaw')]` so every user has at least HomeClaw.
- **Existing user.yml with `friends` (e.g. HomeClaw, Sabrina, Gary):** Parsed as-is; HomeClaw is enforced first only if the first entry is not already HomeClaw.
- **Missing or invalid `username`/`password`:** Stored as `None`; no crash.
- **Malformed friend entry (e.g. missing `name`):** That entry is skipped; rest of list is still parsed.
- **GET /api/config/users:** New fields are additive; old clients that ignore `username` and `friends` are unchanged.
- **POST/PATCH:** If `friends` is not sent, POST uses default `[HomeClaw]`; PATCH keeps existing `found.friends`. So existing callers that don’t send `friends` remain valid.

---

## 4. Logic summary for review

1. **Friend identity field**  
   - Stored as `None` (no file), or a single filename string (e.g. `"identity.md"`).  
   - YAML: omitted → no file; present and empty or `true` → `"identity.md"`; present and non-empty string → that string.  
   - No other types (e.g. list) used for identity.

2. **HomeClaw first**  
   - After parsing, if the friends list is empty we set `[HomeClaw]`.  
   - If the list is non-empty and the first friend’s name (case-insensitive) is not `"HomeClaw"`, we insert `HomeClaw` at position 0. So channel/Companion can assume “first friend = HomeClaw” in later steps.

3. **No routing changes**  
   - Step 1 only adds schema and loading/saving. No `friend_id` in request context, no change to session/chat/memory keys. Those are Step 2 and beyond.

4. **Stability**  
   - `User.from_yaml` still returns `[]` on file/config error.  
   - `_parse_friends` skips bad entries and never raises.  
   - Config API GET/POST/PATCH use try/except and return 4xx/5xx on failure; no uncaught exception to crash Core.

---

## 5. What is *not* in Step 1

- No login endpoint; no auth using username/password (later step).
- No request context `friend_id`; no routing by friend.
- No memory/profile/sandbox path changes.
- No Companion app code changes.

---

---

## 6. Review (logic and robustness)

- **from_yaml:** Top-level try/except returns `[]`; per-user try/except skips bad users. `_parse_friends` is only called with `u.get('friends')` (safe). **Never raises.**
- **_parse_friends:** `raw` can be anything; non-list treated as empty. Per-entry try/except; invalid entries skipped. **identity** only accepts `None`, `bool`, or `str` (any other type → `None`). Empty result → `[HomeClaw]`; first friend not HomeClaw → insert HomeClaw at 0. **Never raises.**
- **_friends_to_dict_list:** Per-friend try/except; `isinstance(f, Friend)`; getattr with defaults. **Never raises.**
- **to_yaml:** Per-user try/except; both write paths in try/except. **Never raises** (doc: logs and returns on write failure; implementation uses pass).
- **Util.get_users:** Catches all exceptions (including `validate_no_overlapping_channel_ids` ValueError) and sets `self.users = []`. **Never raises.**
- **Util.save_users:** try/except around `User.to_yaml`; never raises.
- **Config API GET/POST/PATCH:** All in try/except; return 4xx/5xx on failure. POST/PATCH always assign a valid `friends` list (default `[HomeClaw]` when missing). **Never crash Core.**
- **create_default_user:** Uses `User(name="HomeClaw", email=[], phone=[], im=[])` so required args are always provided.

**Step 1 reviewed and confirmed.** Proceed to Step 2 (request context: user_id + friend_id).
