# Step 12: Companion app — login, friends API (Core) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 12 and §3.

**Goal (Core part):** Provide login (username/password → user_id + token) and an API that returns **only the current user’s friends** (no full user list). Companion app uses these for login screen and friends list; push routing and settings are app-side. Never crash Core.

---

## 1. What was implemented (Core)

### 1.1 POST /api/auth/login

- **Auth:** Same as other protected routes (X-API-Key or Bearer API key when auth_enabled).
- **Body:** `{ "username": string, "password": string }`.
- **Validation:** Find user in user.yml where `user.username == username`; compare password (plain; no hash in this implementation). On failure return 401 with `{"detail": "Invalid username or password"}`.
- **Success:** Create a session token (UUID hex), store in memory with `user_id` and expiry (7 days). Return 200 with `{ "user_id", "token", "name", "friends" }`. `friends` is the list of `{ name (friend_id), relation?, who?, identity? }` for that user (HomeClaw first). Never log password.

### 1.2 GET /api/me

- **Auth:** `Authorization: Bearer <session_token>` (token from login). No API key required when using session token.
- **Returns:** `{ "user_id", "name", "friends" }` for the user identified by the token. 401 if token missing, invalid, or expired.

### 1.3 GET /api/me/friends

- **Auth:** Same Bearer session token.
- **Returns:** `{ "friends": [ ... ] }` for that user only. 401 if token invalid or expired.

### 1.4 Token store and safety

- **Storage:** In-memory dict `token -> { user_id, expires_at }`. Expired entries removed on each token lookup. No persistence across Core restart (user must log in again).
- **Robustness:** All handlers in try/except; login returns 500 with generic message on unexpected error; token dependency raises 401 on any resolve failure. `_user_to_friends_list` and `_clean_expired_tokens` never raise (debug log only). No full user list is ever returned to Companion from these endpoints.
- **Review (never crash):** Login: JSON parse in try/except (400 on invalid JSON); username/password normalized with str() in try/except; get_users() in try/except; per-user lookup in for-loop with try/except; user_id/name extraction in try/except. Token lookup: _clean_expired_tokens uses list(items) and pop in try/except; get_users() in try/except; user resolution by for-loop with try/except. /api/me and /api/me/friends: name extraction in try/except. Core never crashes.

---

## 2. Companion app (out of scope for this step)

- **Login screen:** Call POST /api/auth/login with username/password; store user_id and token; show friends list (from response or GET /api/me/friends).
- **Friends list / selection:** Use friend_id from friends; send user_id + friend_id on every POST /inbound and WebSocket message (already supported by Core).
- **Push routing:** App reads `from_friend` from push payload and routes to the correct friend chat; on tap open that friend’s chat (implementation in Flutter).
- **Settings:** User info, change password (Core endpoint can be added later), default friend, Core URL, notifications (app-side).

Companion must **not** call GET /api/config/users (which returns all users); it uses only /api/auth/login, /api/me, and /api/me/friends with the session token.

---

## 3. Files touched

| File | Change |
|------|--------|
| **core/routes/companion_auth.py** | New: token store, get_companion_token_user dependency, POST /api/auth/login, GET /api/me, GET /api/me/friends. |
| **core/routes/__init__.py** | Export companion_auth (and companion_push_api). |
| **core/core.py** | Register /api/auth/login (verify_inbound_auth), /api/me and /api/me/friends (get_companion_token_user). |

---

## 4. Review

- **Logic:** Login validates username/password; returns token + user_id + friends. Me and me/friends resolve token to one user and return only that user’s data. ✓
- **Security:** No full user list; password not logged; token TTL 7 days. ✓
- **Robustness:** Try/except everywhere; 401/500 with safe messages; Core never crashes. ✓

**Step 12 (Core APIs) is complete.** Companion UI, push routing, and settings are implemented in the Flutter app. Next: Step 13 (Core endpoints and WebSocket: per-user and per-(user_id, friend_id)).
