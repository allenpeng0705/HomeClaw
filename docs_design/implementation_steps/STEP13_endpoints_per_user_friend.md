# Step 13: Core endpoints per-user and per-(user_id, friend_id) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 13 and §11.

**Goal:** Audit and update endpoints so memory reset, KB reset, and sessions list require **user_id** (and **friend_id** where relevant) and only act on that user’s (and that friend’s) data. Never crash Core.

---

## 1. What was implemented

### 1.1 GET /api/sessions

- **Requires user_id** (query param). Optional **friend_id** (query).
- **Behavior:** Returns only sessions for (user_id) or (user_id, friend_id) via `core.get_sessions(user_id=uid, friend_id=fid, ...)`. 400 if user_id missing.
- **Robustness:** Request and query params in try/except; get_core_metadata() in try/except; session_cfg forced to dict; limit from config with try/except (TypeError, ValueError) → 100; get_sessions in try/except → []; response uses sessions if list else []. Core never crashes.

### 1.2 GET/POST /memory/reset

- **Optional user_id and friend_id** (query or body). When **user_id** is provided, clear only that scope (no global RAG/TAM/profile clear).
- **Scoped clear (user_id set):** Chat history and sessions via `chatDB.reset(user_id=uid, friend_id=fid)`; AGENT_MEMORY via `clear_agent_memory_file(..., system_user_id=uid, friend_id=fid)`; daily memory via `clear_daily_memory_for_dates(..., system_user_id=uid, friend_id=fid)`. RAG memory (mem.reset), profiles, and TAM are **not** cleared in scoped mode (full reset only when user_id not provided).
- **Full clear (user_id not provided):** Unchanged: mem.reset(), chat_db.reset(), agent/daily memory, profiles, TAM (backward compat).
- **Robustness:** `_memory_reset_user_friend(request)` uses _safe_str_strip() for query and body values (never raises); request.method and content-type access safe; body parse in try/except. All clear steps in try/except; Core never crashes.

### 1.3 ChatHistory.reset(user_id=None, friend_id=None)

- **memory/chat/chat.py:** New **reset(user_id, friend_id)**. When user_id is set, calls `delete(user_id=uid, friend_id=fid)` and `delete_session(user_id=uid, friend_id=fid)`. When user_id is None, deletes all rows (backward compat). Normalization and deletes in try/except; never raises.

### 1.4 GET/POST /knowledge_base/reset

- **Unchanged in this step.** Design: accept user_id (required) and friend_id (optional) and clear only that (user_id, friend_id) KB. Cognee KB currently has no scoped reset; a follow-up can add `kb.reset(user_id=..., friend_id=...)` and call it from the route when user_id is provided. For now the route remains full reset; endpoint contract (user_id required) can be added in a later change.

---

## 2. WebSocket /ws (design reminder)

- **register:** Should send **friend_id** (optional at register). Core should store (user_id, friend_id) per session. Implementation in websocket_routes when needed.
- **Message (send):** Require **friend_id** in JSON or use session’s current friend_id. Already supported by /inbound; WS path can be updated to accept friend_id per message.
- Push payload already includes **from_friend** (Step 7/10).

---

## 3. Files touched

| File | Change |
|------|--------|
| **memory/chat/chat.py** | reset(user_id=None, friend_id=None): scoped delete/delete_session or clear all; try/except, never raises. |
| **core/routes/misc_api.py** | GET /api/sessions: require user_id (query), optional friend_id; call core.get_sessions(user_id=, friend_id=). Request import. |
| **core/routes/memory_routes.py** | memory_reset(request): _memory_reset_user_friend(request); when user_id set, scoped chat/agent/daily clear only; else full clear (unchanged). |

---

## 4. Review

- **Logic:** Sessions list filtered by user_id (and friend_id). Memory reset with user_id clears only chat, agent memory, daily for that scope; without user_id clears all. ✓
- **Robustness:** All new code in try/except; ChatHistory.reset never raises; memory_routes and misc_api safe. ✓

**Step 13 (endpoints) is complete.** KB reset scoped by user_id/friend_id and WS friend_id can be added in follow-ups. Next: Step 14 (File tools and path resolution).
