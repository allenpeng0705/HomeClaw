# Step 11: Channels: route to (user_id, HomeClaw) — done

**Design ref:** [UserFriendsModelFullDesign.md](../UserFriendsModelFullDesign.md) implementation step 11.

**Goal:** When a channel request is matched to a user, set **friend_id = "HomeClaw"** for that request. All channel traffic uses (user_id, HomeClaw). No change to channel delivery; only scoping so storage, memory, and reply use the correct (user_id, friend_id).

---

## 1. What was implemented

### 1.1 Channel entry points

- **POST /process:** Used by channels (email, matrix, etc.) via `transferTocore`. After permission check, Core sets **request.user_name**, **request.system_user_id**, then **request.friend_id = "HomeClaw"** (all in try/except so invalid types do not crash). **friend_id is set before _persist_last_channel** so the persisted last channel and get_session_id use (user_id, HomeClaw). Request is then put on the queue; when processed, all storage and memory use (user_id, HomeClaw).
- **POST /local_chat:** Same: after permission check, request.user_name, system_user_id, and **request.friend_id = "HomeClaw"** (try/except). **_persist_last_channel** wrapped in try/except so a persist failure does not crash the handler. Sync processing uses that request for process_text_message, so all data is scoped to (user_id, HomeClaw).

### 1.2 POST /inbound (Companion / WebChat)

- **Unchanged.** Inbound already normalizes friend_id from the body: `inbound_friend_id = ((str(_fid).strip() if _fid is not None else "") or "HomeClaw")`. Companion sends friend_id; channels do not use /inbound (they use /process). So /inbound behavior is correct.

### 1.3 Robustness

- **/process:** request.user_name, request.system_user_id, request.friend_id assignments wrapped in try/except (TypeError, AttributeError); _persist_last_channel in try/except so persist failure does not crash. friend_id set before persist so last_channel/session key are correct.
- **/local_chat:** Same try/except for user_name, system_user_id, friend_id; _persist_last_channel in try/except. Core never crashes from bad user fields or persist.

---

## 2. Summary

- **Channels** (telegram, matrix, email, etc.) call Core via **/process** (or /local_chat). Core explicitly sets **friend_id = "HomeClaw"** for those requests so all downstream storage, memory, chat, and session use **(user_id, HomeClaw)**.
- **Companion** uses **/inbound** and sends friend_id in the body; Core uses that value (default "HomeClaw" when omitted).
- No change to how replies are delivered to channels; only the **scoping** of data is now correct.

---

## 3. Files touched

| File | Change |
|------|--------|
| **core/core.py** | POST /process: set user_name, system_user_id, friend_id before _persist_last_channel; try/except on each and on _persist_last_channel. POST /local_chat: same try/except; friend_id before persist. |

---

## 4. Review

- **Logic:** Channel requests get friend_id = "HomeClaw"; data and reply are scoped to (user_id, HomeClaw). ✓
- **Robustness:** try/except on friend_id assignment; no new raises. ✓

**Step 11 is complete.** Next: Step 12 (Companion app: login, friends, push routing, settings).
