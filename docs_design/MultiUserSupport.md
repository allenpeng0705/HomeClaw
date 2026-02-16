# Multi-user support: how it works today

This doc explains **how multiple users are handled**: the allowlist in `config/user.yml`, how the Core matches requests to users, and which data is per-user vs global. No code changes here — confirmation and reference only.

---

## Summary (implemented)

**Behaviour:**
- Channels send **email, IM id, or phone** as the request identifier (`user_id` in the request = channel identity).
- We look up **which user** in `config/user.yml` by matching that value against each user’s `email` / `im` / `phone` and get that user’s **name** and **system user id** (and permissions).
- **Different users must have different** email/im/phone: at load time we validate that no email/im/phone value is shared between two users (see **§1**).
- **All data** (chat history, sessions, memory, KB) is keyed by our **system user id** (from user.yml `id` or `name`), not by the channel identity. Channel identity is only used for permission check and for sending the reply to the right channel.

**Flow:** Channel sends email/im/phone → Core resolves to one user in user.yml → we set `request.system_user_id = user.id or user.name` → all storage (chatDB, memory, KB, tool context) uses that system user id.

---

## 1. Allowlist: `config/user.yml`

**Purpose:** Decide **who** can talk to the Core via channels (IM, Email, Phone). Not used for routing logic inside the Core; only for **permission check** and **display name**.

**Format:**

```yaml
users:
  - id: HomeClaw                      # Unique system user id (used for all storage); defaults to name if omitted
    name: HomeClaw                    # Display name (used as user_name when this user is matched)
    email: []                         # Channel identities for Email (must not overlap with other users)
    im: ['matrix:@pengshilei:matrix.org']   # Channel identities for IM: "<channel>:<id>"
    phone: []                         # Channel identities for Phone/SMS
    permissions: []                   # e.g. [IM, EMAIL, PHONE]; empty = allow all channel types
```

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

**So “multi-user” at the gate:** You add one entry per person (or per identity) in `user.yml`, each with its own `name` and list of IDs (`im`, `email`, `phone`). Each channel must send a `user_id` that appears in one of those lists. One person can have multiple IDs (e.g. same person on Matrix and Telegram) by listing both under one `users` entry or splitting into two entries.

**Where `user_id` comes from:** The **channel** sets it when building the `PromptRequest`, e.g.:
- Matrix: `user_id = 'matrix:' + message.sender` (e.g. `matrix:@pengshilei:matrix.org`).
- Webhook/WebSocket: client sends `user_id` in the JSON payload.
- So `user_id` is **stable per channel identity** and is what we use everywhere below.

---

## 2. What is per-user (keyed by system user id and usually `app_id`)

All of these scope data by **system user id** (from user.yml `id` or `name`) and where relevant by app/session, so multiple users each have their own data:

| Component | Scoping | Where |
|-----------|---------|--------|
| **Chat history** | `(app_id, system_user_id, session_id)` | DB table `homeclaw_chat_history`. |
| **Sessions** | `(app_id, system_user_id, session_id)` | DB table `homeclaw_session_history`. |
| **Runs** (memory runs) | `(agent_id, system_user_id, run_id)` | DB table `homeclaw_run_history`. |
| **Memory (RAG)** | Keyed by `(system_user_id, agent_id)` | Each user has their own memory sandbox; add/search use system user id. |
| **Knowledge base** | `system_user_id` | Each user has their own KB sandbox; builtin tools use context’s system user id. |
| **User profile** | `system_user_id` | One JSON file per user under `database/profiles/` (or `profile.dir`); see docs/UserProfileDesign.md. |
| **Tool context** | `ToolContext` has `app_id`, `user_id` (storage id), `system_user_id`, `user_name`, `session_id`, `run_id`, `request`. | Tools use these for per-user storage. |

So: **chat, sessions, runs, memory, and KB are all per-user.** Multi-user is supported for storage and for the **direct reply** to a message (see below).

---

## 3. Direct reply: sent to the right user

When a user sends a message through the **request queue**:

1. Core gets a `PromptRequest` with that user’s `user_id`, `request_id`, `host`, `port`, `channel_name`, etc.
2. After permission check and `process_text_message`, the **reply** is sent with that **same request’s** channel info: `AsyncResponse(request_id=request.request_id, host=request.host, port=request.port, ...)`.
3. So the **direct response** goes back to the **channel that sent the message** — i.e. to the correct user.

So for normal chat, **multi-user is correct**: each user gets their own reply on their own channel.

---

## 4. What is not per-user today: “latest channel” and TAM

**Last-channel store (`latest_channel.json` + DB `homeclaw_last_channel`):**

- There is a **single** “last channel” key: `_DEFAULT_KEY = "default"`.
- On **every** incoming request, Core calls `save_last_channel(..., key=_DEFAULT_KEY, ...)`, so the stored “last channel” is **overwritten** by whoever sent the most recent message.
- So at any time there is only **one** “latest” channel (one request_id, host, port, channel_name).

**Where “latest channel” is used:**

- **`send_response_to_latest_channel(response)`** is used when we need to send a message **without** a specific `PromptRequest`, e.g.:
  - TAM: when a **reminder** or **cron** job fires, it calls `send_reminder_to_latest_channel(message)` → `send_response_to_latest_channel(message)`.
  - Plugins/orchestrator when they don’t have the request and fall back to “latest”.
- So **reminders and cron messages** are sent to whichever channel was **last** to send a message to the Core — **not** to the user who created that reminder/cron.

**TAM storage (cron and one-shot reminders):**

- DB tables `homeclaw_tam_cron_jobs` and `homeclaw_tam_one_shot_reminders` do **not** have a `user_id` (or app_id) column.
- So **reminders and cron jobs are global**: they are not associated with a specific user. When they run, they always use “latest channel.”

**Summary:**

- **Data** (chat, sessions, memory, KB): **per-user** — multi-user supported.
- **Direct reply** to a user message: **per-request** — goes to the right user.
- **Reminders and cron:** Stored globally; delivery is to **one** “latest” channel. So with multiple users, reminders/cron do **not** target a specific user; they go to whoever was last. If you need “User A’s reminders only to User A,” that would require adding `user_id` (and possibly per-user last-channel key) and changing TAM and last-channel logic.

---

## 5. Summary table

| Aspect | Per-user? | Notes |
|--------|-----------|--------|
| **Allowlist** | Yes (multiple users in `user.yml`) | Channel identity must match one user’s `email`/`im`/`phone`; each value must be unique across users. |
| **Chat history** | Yes | `(app_id, system_user_id, session_id)`. |
| **Sessions / runs** | Yes | Same. |
| **Memory (RAG)** | Yes | Keyed by system user id (and agent_id). |
| **Knowledge base** | Yes | System user id in builtin tools. |
| **Direct reply** | Yes | Reply uses the request’s channel → correct user. |
| **Last channel** | No (single “default”) | One global “latest”; overwritten on every request. |
| **TAM reminders / cron** | No | No `user_id` in DB; delivery via “latest channel” only. |

So: **multi-user is supported for identity (user.yml), storage (chat/sessions/memory/KB), and direct replies.** It is **not** supported for **reminder/cron delivery** and **last-channel** — both are single-channel today. User profile (one JSON file per user) will naturally be **per-user** by user id and fits this model.

---

## 6. System user id (implemented)

- **user.yml:** Each user has an optional **`id`** (unique system user id); if omitted, it defaults to **`name`**. Different users must have **distinct** email/im/phone (validated on load).
- **After `check_permission`:** Core sets `request.system_user_id = user.id or user.name`. `request.user_id` stays as the channel identity (for reply delivery).
- **Storage:** Chat history, sessions, runs, memory, KB (and future user profile) all use **system_user_id** (when set) for keys; Core and ToolContext pass it through so tools and DB see the same id.
- **Delivery:** Replies still use `request.user_id` and request metadata to send to the correct channel. One person with multiple channel ids (e.g. Matrix + Telegram in one user entry) has one system user id and one set of data; which channel they use only affects where the reply is sent.
