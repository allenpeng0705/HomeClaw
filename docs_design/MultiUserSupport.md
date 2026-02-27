# Multi-user support: how it works today

This doc explains **how multiple users and friends are handled**: the allowlist in `config/user.yml`, **friends list** and **identity** per friend, how the Core matches requests to users, and which data is per-user vs per-(user, friend) vs global. See also [UserFriendsModelFullDesign.md](UserFriendsModelFullDesign.md) and the implementation steps in `docs_design/implementation_steps/`.

---

## Summary (implemented)

**Behaviour:**
- Channels send **email, IM id, or phone** as the request identifier (`user_id` in the request = channel identity).
- We look up **which user** in `config/user.yml` by matching that value against each user’s `email` / `im` / `phone` and get that user’s **name** and **system user id** (and permissions).
- **Different users must have different** email/im/phone: at load time we validate that no email/im/phone value is shared between two users (see **§1**).
- **All data** (chat history, sessions, memory, KB, TAM one-shot reminders) is keyed by **system user id** and optionally **friend_id** (from the user’s **friends** list). **HomeClaw** is always the first friend; channel traffic uses `friend_id = HomeClaw`. Companion app can use any friend from the user’s list.
- **Companion login:** Optional **username** / **password** in user.yml; Companion authenticates and gets only that user’s data and friends (no full user list).

**Flow:** Channel sends email/im/phone → Core resolves to one user in user.yml → we set `request.system_user_id`, `request.friend_id` (e.g. HomeClaw for channels) → storage (chatDB, sessions, memory, TAM one-shot, file paths) uses (user_id, friend_id) where applicable.

---

## 1. Allowlist: `config/user.yml`

**Purpose:** Decide **who** can talk to the Core via channels (IM, Email, Phone). Not used for routing logic inside the Core; only for **permission check** and **display name**.

**Format:**

```yaml
users:
  - id: AllenPeng                     # Unique system user id (used for all storage); defaults to name if omitted
    name: AllenPeng                   # Display name
    username: pengshilei              # Optional: for Companion app login
    password: secret                  # Optional: plain text; hashing can be added later
    email: []
    im: ['matrix:@pengshilei:matrix.org']
    phone: []
    permissions: []
    friends:                          # Optional; if omitted, defaults to [HomeClaw]
      - name: HomeClaw                # Always first; channel traffic uses this
      - name: Sabrina
        relation: girlfriend
        who:                          # Injected into system prompt for this friend
          gender: female
          roles: ['girlfriend']
          personalities: [gentle, supportive]
          language: zh
          response_length: medium
        identity: identity.md         # Optional: markdown file in {user_id}/{friend_id}/identity.md
```

- **friends:** List of companions; **HomeClaw** is always first. Each friend has `name` (friend_id), optional `relation`, `who` (dict for prompt), and optional `identity` (filename in that friend’s folder, e.g. `identity.md`). See [STEP6_friend_identity.md](implementation_steps/STEP6_friend_identity.md) and [config/examples/friend_identity.md](../../config/examples/friend_identity.md).

**Validation:** On load, we require that no two users share the same email, im, or phone value (overlap would make “which user” ambiguous). If overlap is detected, `get_users()` raises `ValueError` with a clear message.

**Matching logic (Core `check_permission`):**

1. Each incoming request has a **`user_id`** set by the channel (e.g. email address for Email, `matrix:@user:domain` for Matrix, `telegram:<chat_id>` for Telegram).
2. Core loads `user.yml` via `Util().get_users()` (from `User.from_yaml(config/user.yml)`).
3. For the request’s **channel type** (Email, IM, or Phone):
   - Core loops over each user in `users`.
   - If **`user_id` is in** that user’s list (`email`, `im`, or `phone`) **or** that list is **empty**, that user is considered a match.
   - If the matched user’s `permissions` include this channel type (or `permissions` is empty), the request is **allowed**.
4. The **first** matching user wins. If a match is found, Core can set `request.user_name = user.name` (so the display name comes from `user.yml`).
5. If no user matches, the request is **denied** (“Permission denied”).

**Empty list = allow all:** If a user’s `im`, `email`, or `phone` list is **empty** for that channel type, that user is still a match — i.e. **allow all** senders for that channel. We encourage setting permission lists correctly (non-empty when you want to restrict access).

**So “multi-user” at the gate:** You add one entry per person (or per identity) in `user.yml`, each with its own `name` and list of IDs (`im`, `email`, `phone`). Each channel must send a `user_id` that appears in one of those lists. One person can have multiple IDs (e.g. same person on Matrix and Telegram) by listing both under one `users` entry or splitting into two entries.

**Where `user_id` comes from:** The **channel** sets it when building the `PromptRequest`, e.g.:
- Matrix: `user_id = 'matrix:' + message.sender` (e.g. `matrix:@pengshilei:matrix.org`).
- Webhook/WebSocket: client sends `user_id` in the JSON payload.
- So `user_id` is **stable per channel identity** and is what we use everywhere below.

---

## 2. What is per-user and per-(user_id, friend_id)

Data is keyed by **system user id** and, where implemented, by **friend_id** (from the user’s friends list). Channels use `friend_id = HomeClaw`; Companion can select any friend.

| Component | Scoping | Where |
|-----------|---------|--------|
| **Chat history** | `(app_id, system_user_id, session_id, friend_id)` | DB: `homeclaw_chat_history`. |
| **Sessions** | `(app_id, system_user_id, session_id, friend_id)` | DB: `homeclaw_session_history`. |
| **Runs** (memory runs) | `(agent_id, system_user_id, run_id)` | DB: `homeclaw_run_history`. |
| **Memory (RAG)** | Keyed by `(system_user_id, friend_id)` (Cognee namespace) | Per-user, per-friend memory. |
| **Knowledge base** | `system_user_id` (friend_id in path optional) | Per-user KB; friend-specific path `{friend_id}/knowledge/` under user sandbox. |
| **User profile** | `(system_user_id, friend_id)`; profile only for HomeClaw | See UserProfileDesign.md. |
| **AGENT_MEMORY / daily** | `(system_user_id, friend_id)` | Paths: `memories/{user_id}/{friend_id}/agent_memory.md`, daily under same. |
| **TAM one-shot reminders** | `(user_id, friend_id)` in DB | Stored and delivered per user/friend; push includes `from_friend`. |
| **Last channel** | Per `(system_user_id)` (key in store) | So reminders/cron for that user go to that user’s last channel. |
| **File workspace** | `homeclaw_root/{user_id}/` | Sandbox root per user; paths like `{friend_id}/output/`, `{friend_id}/knowledge/` under that root. `share` = global share. |
| **Tool context** | `ToolContext`: `app_id`, `user_id`, `system_user_id`, `friend_id`, `user_name`, `session_id`, `run_id`, `request`. | Tools use these for scoped storage and paths. |

So: **chat, sessions, memory (RAG + markdown), TAM one-shot, and file paths are per-user and per-friend where applicable.** Direct reply uses the request’s channel; TAM delivery uses the user’s last channel key.

---

## 3. Direct reply: sent to the right user

When a user sends a message through the **request queue**:

1. Core gets a `PromptRequest` with that user’s `user_id`, `request_id`, `host`, `port`, `channel_name`, etc.
2. After permission check and `process_text_message`, the **reply** is sent with that **same request’s** channel info: `AsyncResponse(request_id=request.request_id, host=request.host, port=request.port, ...)`.
3. So the **direct response** goes back to the **channel that sent the message** — i.e. to the correct user.

So for normal chat, **multi-user is correct**: each user gets their own reply on their own channel.

---

## 4. Last channel and TAM (per-user / per-friend)

**Last-channel store:** The store key is **per system_user_id** (and optionally session). Each user has their own last channel; reminders and cron for that user are delivered to that user's last channel.

**TAM one-shot reminders:** DB table `homeclaw_tam_one_shot_reminders` has **user_id** and **friend_id**. When a reminder fires, delivery uses the stored user and `from_friend` in the push payload.

**TAM cron jobs:** One-shot reminders are scoped per (user_id, friend_id); cron jobs may be global or per-user depending on implementation.

**AGENT_MEMORY and daily memory:** Paths are **per (user_id, friend_id)** (e.g. `memories/{user_id}/{friend_id}/agent_memory.md`). When there is no user, global paths are used.
---

## 5. Summary table

| Aspect | Per-user / per-friend? | Notes |
|--------|-------------------------|--------|
| **Allowlist** | Yes (multiple users in `user.yml`) | Channel identity must match one user's `email`/`im`/`phone`; each value unique. Optional `username`/`password`, **friends** list with **identity**. |
| **Chat history** | Yes, per (user_id, friend_id) | DB includes friend_id. |
| **Sessions / runs** | Yes | Sessions per (user_id, friend_id). |
| **Memory (RAG)** | Yes | Keyed by (system_user_id, friend_id) where implemented. |
| **Knowledge base** | Yes | Per user; friend path `{friend_id}/knowledge/` under user sandbox. |
| **Direct reply** | Yes | Reply uses the request's channel. |
| **Last channel** | Yes (per user) | Keyed by system_user_id so reminders go to that user's last channel. |
| **TAM one-shot** | Yes | user_id and friend_id in DB; delivery and push include from_friend. |
| **AGENT_MEMORY / daily** | Yes, per (user_id, friend_id) | Paths under `memories/{user_id}/{friend_id}/`. |
| **File sandbox** | Yes | `homeclaw_root/{user_id}/`; friend paths `{friend_id}/output/`, `{friend_id}/knowledge/`. |

So: **multi-user and per-friend are supported** for identity (user.yml + friends), storage (chat/sessions/memory/KB), AGENT_MEMORY, daily memory, TAM one-shot, last-channel (per user), and file paths. User profile is per (user_id, HomeClaw).

---

## 6. Migration from older config

- **Existing `user.yml` without `friends`:** Each user gets a default `friends: [HomeClaw]`. No change required; behaviour stays correct (all traffic is treated as HomeClaw).
- **Adding friends:** Add a `friends` list under any user; put **HomeClaw** first, then other companions with optional `relation`, `who`, and `identity`. See the format in **§1** and [STEP1_user_yml_schema_and_loading.md](implementation_steps/STEP1_user_yml_schema_and_loading.md).
- **Companion login:** Add `username` and `password` (plain text) to a user to enable Companion app login for that user. Existing config without these fields continues to work (e.g. Control UI / API key only).

---

## 7. System user id (implemented)

- **user.yml:** Each user has an optional **`id`** (unique system user id); if omitted, it defaults to **`name`**. Different users must have **distinct** email/im/phone (validated on load).
- **After `check_permission`:** Core sets `request.system_user_id = user.id or user.name`. `request.user_id` stays as the channel identity (for reply delivery).
- **Storage:** Chat history, sessions, runs, memory, KB (and future user profile) all use **system_user_id** (when set) for keys; Core and ToolContext pass it through so tools and DB see the same id.
- **Delivery:** Replies still use `request.user_id` and request metadata to send to the correct channel. One person with multiple channel ids (e.g. Matrix + Telegram in one user entry) has one system user id and one set of data; which channel they use only affects where the reply is sent.
