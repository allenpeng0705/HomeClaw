# User and friends model: full design

This document is the **single master design** for the new user/friends model and all related changes: user.yml structure, Companion app login and friends list, data scoping (memory, profile, KB, cron, sandbox), channels, push, and friend identity. Implementation should follow this doc and the referenced docs **step by step**, with care for backward compatibility and data migration where needed.

**Related docs (reference only; this doc is authoritative for the new model):**
- [FolderSemanticsAndInference.md](FolderSemanticsAndInference.md) — folder semantics, "my documents" vs friend output, default path
- [FileSandboxDesign.md](FileSandboxDesign.md) — sandbox layout, file tools, links
- [MultiUserSupport.md](MultiUserSupport.md) — current multi-user (channel → user match)
- [SessionAndDualMemoryDesign.md](SessionAndDualMemoryDesign.md) — session keys, RAG + AGENT_MEMORY
- [UserProfileDesign.md](UserProfileDesign.md) — profile content and extraction
- [CompanionPushNotifications.md](CompanionPushNotifications.md) — push payload, APNs/FCM
- [MemoryFilesUsage.md](MemoryFilesUsage.md) — AGENT_MEMORY.md and daily memory usage

---

## 1. Overview

- **One login = one user.** The Companion app (and any client that authenticates) identifies a **single real user** (from `config/user.yml`) by username/password (or future auth). That user has a **friends list**: the first friend is **HomeClaw** (system; no persona), followed by named friends (e.g. Sabrina, Gary) with optional persona (`who`) and optional **identity file** (`identity.md` in that friend’s root folder).
- **No top-level "companion" user.** We do not treat "companion" as a separate user type. Instead, the **logged-in user** has friends; the Companion UI shows only **that user’s friends** and chats with them. Data is always scoped by **(user_id, friend_id)**.
- **Channels (Telegram, Matrix, etc.)** are treated as talking to **HomeClaw**. Incoming channel messages are routed to **(user_id, HomeClaw)**; channel data (chat, memory, last-channel) lives under that pair. So channels and Companion both use the same user/friend model; only the “friend” differs (HomeClaw for channels, or the user-selected friend in Companion).
- **Data is per (user_id, friend_id).** Chat history, sessions, MD memory (AGENT_MEMORY, daily), RAG/KB, cron/reminders, and (where applicable) profile are all keyed by **(user_id, friend_id)**. No sharing between (user, friend1) and (user, friend2).
- **Profile** is generated and used only by **HomeClaw**. It is stored under **(user_id, HomeClaw)**. For the logged-in user, the profile can be derived from that pair; we do not need a separate “user KB” embedding for profile.
- **Push notifications** are per user (one device can have one user’s pushes). Each push payload includes **from_friend** (which friend the message is from: friend_id or `"HomeClaw"`) so the app can show “From Sabrina” or “From HomeClaw”.
- **Sandbox folders** are created **automatically** for each user and each (user_id, friend_id). Each friend has a **root folder** containing `identity.md` (optional, for extra description) and subfolders `output/` and `knowledge/`.

---

## 2. user.yml structure

- **Users** are the real people who can log in (Companion) or be matched from channels (email/im/phone). Each user has:
  - **id** — unique system user id (used for all storage paths and keys). Required.
  - **name** — display name.
  - **username** — for Companion login (optional; if present, used with **password** for auth).
  - **password** — stored hash or plain (implementation choice; see Companion auth).
  - **email, im, phone** — channel identities for matching (same as today). Used when a message comes from a channel to resolve to this user.
  - **permissions** — as today.
  - **friends** — list of friends for this user. **Order matters:** first friend is always **HomeClaw** (system friend); the rest are named friends (e.g. Sabrina, Gary).

- **Each friend** in `friends` is an object:
  - **name** (required) — display name and **friend_id** for paths and storage (e.g. `"HomeClaw"`, `"Sabrina"`, `"Gary"`). Sanitized for use in paths (no `/`, `\`, etc.).
  - **relation** (optional) — e.g. `girlfriend`, `friend`, `wife`. For display and optional prompt hints.
  - **who** (optional) — persona for this friend (only for non-HomeClaw friends). Same shape as today: `description`, `gender`, `roles`, `personalities`, `language`, `response_length`, etc. **HomeClaw** has no `who` (system friend; no persona).
  - **identity** (optional) — filename of a single Markdown file in the friend’s root folder to load as extra description. **Empty or omitted:** do not read any file. **One .md filename** (e.g. `"identity.md"`): path relative to friend root; **default is `identity.md`** if the field is set but empty. Core tries to read the file; if it’s not there, skip silently. Content is injected into the **same prompt block that uses personalities** (the “who” / companion identity section). Example: see **config/examples/friend_identity.md**; user can copy that to `homeclaw_root/{user_id}/{friend_id}/identity.md` to use it.

- **Backward compatibility:** This is a **new design**; we do not promise backward compatibility with the old “companion as user” or “one who per user” model. Migration path: existing users can be converted so that each current “user” becomes a user with a single friend “HomeClaw” and optional additional friends from config.

---

## 3. Companion app: detailed changes

Companion app changes are not only UI and push routing; they include auth, friends handling, settings, and consistent (user_id, friend_id) in all requests and WebSocket messages.

### 3.1 Login and auth

- **Login screen:** User enters **username** and **password**. App calls Core (e.g. `POST /api/auth/login` or equivalent) with credentials. Core validates against `user.yml`: find user where `user.username == username` and password matches (plain or hashed per implementation).
- **On success:** Core returns **user_id** (system user id) and a **session token** (or JWT) for subsequent requests. Optionally return the **friends list** for this user in the same response so the app can show the friend list without a second call.
- **On failure:** Return 401; app shows “Invalid username or password.”
- **No “list all users”:** Companion never shows or fetches all users in the system. Only the logged-in user and their friends are visible.

### 3.2 Friends: fetch, display, select

- **Fetching friends:** After login, app has **user_id**. Call an endpoint that returns **only this user’s friends** (e.g. `GET /api/users/me/friends` with auth, or include friends in login response). Response: list of `{ friend_id, name, relation?, ... }` in order (HomeClaw first, then others).
- **Display:** Show a friends list (sidebar or tab). HomeClaw first; then each other friend. No “switch user” to another system user—only switch between **friends** of the current user.
- **Selection:** When the user taps a friend, set **current_friend_id** in app state. Every message and every request to Core uses **(user_id, friend_id)** where user_id is from login and friend_id is the selected friend.
- **Persistence:** Optionally persist “last selected friend” per user in local storage so the app reopens on the same friend.

### 3.3 Sending messages and receiving replies

- **Outgoing:** Every message (POST /inbound or WebSocket) must include **user_id** (from login) and **friend_id** (selected friend). Core uses these for storage and prompt building.
- **WebSocket:** On connect, send **register** with **user_id** and optionally **friend_id** (or send friend_id with each message). Core stores session → (user_id, friend_id) so push and reply routing are correct.
- **Incoming reply:** Sync response (inbound or WS) is for the same (user_id, friend_id) as the request. Display in that friend’s chat thread.

### 3.4 Push notifications: receive and route to friend chat

- **Receive:** When the app receives a push (foreground handler or tap on notification), read from the payload: **user_id**, **from_friend**, **source**, and body/title.
- **Route to friend:** Use **from_friend** to decide which chat the message belongs to. If **from_friend** is `"Sabrina"`, add the notification content to **Sabrina’s** chat thread (and optionally show a in-app badge or banner for “Sabrina”). If **from_friend** is `"HomeClaw"`, add to HomeClaw’s thread.
- **On tap:** When the user taps the notification, open the app and **navigate to that friend’s chat** (so the conversation with Sabrina or HomeClaw is visible). Do not open a generic “messages” view without friend context.
- **Badges / list:** If the app shows a list of friends with unread counts, update the count for the friend indicated by **from_friend** when a push is received.

### 3.5 Settings page

- **What to show (per user):**
  - **Current user:** Display name (from login or from Core), username. No option to “switch to another user” unless we add explicit “logout and login as another user.”
  - **Change password:** If Core supports it, add “Change password” (current password + new password); call Core endpoint that updates user.yml or auth store for this user_id.
  - **Default friend (optional):** Which friend to open by default when the app starts (e.g. “HomeClaw” or “last used”). Store in app local state or user preference.
  - **Core URL / connection:** Existing “Core URL” and API key (if any) for connecting to HomeClaw Core. Scoped to the app/device; no need to be per user if one device = one user.
  - **Notifications:** Enable/disable push, permission status. Optional: per-friend “mute” (do not show notification for this friend) — can be app-only or sent to Core later.
- **Logout:** Clear local session/token and user_id; return to login screen. Optionally call Core to invalidate token if we add token invalidation.

### 3.6 Channels (Companion does not manage them)

- Companion does **not** configure or manage Telegram, Matrix, or other channels. Channels are set up on the Core/server side. When a message comes from a channel, Core resolves it to (user_id, HomeClaw). Companion only shows the logged-in user’s friends and chats with them over the app; channel traffic is separate (same user can use both).

---

## 4. Data scoping: per (user_id, friend_id)

All of the following are keyed by **(user_id, friend_id)**. friend_id is the **name** of the friend (e.g. `HomeClaw`, `Sabrina`), sanitized for paths.

| Data | Scope | Where / notes |
|------|--------|----------------|
| **Chat history** | (user_id, friend_id) | DB or storage key includes both. Session key can be e.g. `(app_id, user_id, friend_id, session_id)` or derived. |
| **Sessions** | (user_id, friend_id) | Same as chat; list sessions per (user_id, friend_id). |
| **MD memory** | (user_id, friend_id) | One directory per pair: e.g. `memories/{user_id}/{friend_id}/` with `agent_memory.md`, `daily.md` (or `memory/YYYY-MM-DD.md` under that). See §5. |
| **RAG / Cognee** | (user_id, friend_id) | Namespace or filter by (user_id, friend_id). Each pair has its own vector space / index. |
| **Knowledge base** | (user_id, friend_id) | Folder: `homeclaw_root/{user_id}/{friend_id}/knowledge/`. RAG/Cognee use it when chatting with that friend. No separate “user KB” for profile; profile is under (user_id, HomeClaw). |
| **Profile** | (user_id, HomeClaw) only | Only **HomeClaw** generates and uses the user profile. Stored under (user_id, HomeClaw), e.g. `database/profiles/{user_id}/HomeClaw.json` or `profiles/{user_id}_HomeClaw.json`. See UserProfileDesign.md for content. |
| **Cron / reminders** | (user_id, friend_id) | Stored and keyed by (user_id, friend_id). When a reminder fires, delivery is to **user_id**; payload includes **friend_id** (and **from_friend** in push) so UI can show which friend the reminder is for. |
| **Sandbox files** | user_id (+ friend_id for friend output/knowledge) | See §6. |
| **Last channel** | user_id (and optionally friend_id) | For channels, we store last channel per user (and treat as HomeClaw). For Companion, no “channel”; reply goes over WebSocket/push. |

---

## 5. Memory (MD): paths and usage

- **Path layout:** One directory per (user_id, friend_id):
  - `memories/{user_id}/{friend_id}/agent_memory.md` — long-term curated memory for this pair.
  - `memories/{user_id}/{friend_id}/daily.md` or `memories/{user_id}/{friend_id}/memory/YYYY-MM-DD.md` — daily/short-term notes.

- **Loading:** When building the prompt for a request with (user_id, friend_id), Core loads **only** the memory for that pair (agent_memory + daily for yesterday/today). No cross-friend memory.
- **Tools:** `append_agent_memory` and `append_daily_memory` (and any memory search tools) operate on the (user_id, friend_id) for the current request. Context must carry user_id and friend_id so tools know which files to read/write.
- **Global / system:** If we need a “system” or “global” memory for the user (e.g. shared across friends), that can be defined later; for this design, memory is strictly per (user_id, friend_id).

---

## 6. Sandbox folders: auto-creation and layout

- **All folders are created automatically** at startup (or when a user/friend is first used), so file tools and RAG never fail for missing directories.

- **Layout under homeclaw_root:**
  - `homeclaw_root/share/` — global share (all users).
  - `homeclaw_root/{user_id}/` — user sandbox root (default when path is unspecified).
  - `homeclaw_root/{user_id}/downloads/` — user’s downloads (Core/Companion-saved; see FolderSemanticsAndInference.md).
  - `homeclaw_root/{user_id}/documents/` — user’s documents (“my documents”).
  - `homeclaw_root/{user_id}/output/` — user’s own generated output.
  - `homeclaw_root/{user_id}/work/` — work-related.
  - `homeclaw_root/{user_id}/share/` — shared among that user’s friends only.
  - For **each friend** of that user: `homeclaw_root/{user_id}/{friend_id}/` — friend root folder:
    - `identity.md` (or filename from friend’s `identity` in user.yml) — optional; extra description (see §7).
    - `output/` — friend’s generated files (reports, PPTs; Core writes here and sends link).
    - `knowledge/` — that friend’s KB (RAG/Cognee use when chatting with that friend).

- **Auto-creation:** On startup (or on first access), for each user in user.yml and for each friend in that user’s friends list, create:
  - `homeclaw_root/{user_id}`, `downloads`, `documents`, `output`, `work`, `share`;
  - `homeclaw_root/{user_id}/{friend_id}`, `{friend_id}/output`, `{friend_id}/knowledge`;
  - `homeclaw_root/share`.
  We do **not** auto-create `identity.md` (user can add it manually); we only create the directories.

- **Folder semantics and default path:** See [FolderSemanticsAndInference.md](FolderSemanticsAndInference.md). Default path when nothing specified: **user root** `homeclaw_root/{user_id}/`.

---

## 7. Friend identity (identity.md)

- **Purpose:** Give a friend more description than fits in user.yml (e.g. long backstory, style notes). Stored in the friend’s root folder so it can be edited without changing user.yml.
- **Config:** In user.yml, under the friend, **identity** is optional and must be **empty or one .md filename** (relative to the friend’s root folder). **Default:** if the field is present but empty, use `identity.md`. So:
  - Omitted or not set: do not read any file.
  - `identity: ""` or `identity: "identity.md"`: read `homeclaw_root/{user_id}/{friend_id}/identity.md`.
  - `identity: "other.md"`: read `homeclaw_root/{user_id}/{friend_id}/other.md`.
- **Reading:** Core tries to read the file. If the file is not there, skip silently (no error, no inject). Never crash Core. Read as UTF-8. Cap length (e.g. 8k–16k chars) to avoid blowing the context window.
- **Injection:** The file content is injected into the **same prompt block that uses personalities** (the “who” block: description, gender, roles, personalities, language, response_length). So identity file content is merged with or appended after the structured `who` fields—one coherent “Identity” section for the friend. Do not create a separate section that feels disconnected from the persona.
- **Example file:** An example identity file is shipped as **config/examples/friend_identity.md**. Users can copy it to `homeclaw_root/{user_id}/{friend_id}/identity.md` (or the filename they set in `identity`) to use it. The example is named `friend_identity.md` in the repo so it is clearly an example; in the friend root the user typically names it `identity.md` and sets `identity: "identity.md"` or leaves identity as default.

---

## 8. Push notifications

- **Target:** Push is sent to **user_id** (the user who owns the device/token). Messages are per user; one device can have one user’s tokens.
- **Payload:** In addition to **user_id** and **source** (e.g. `reminder`, `inbound`), every push includes **from_friend**: either the friend_id (e.g. `"Sabrina"`) or `"HomeClaw"`. So the app can show “From Sabrina: …” or “From HomeClaw: …” and open the correct chat.
- **deliver_to_user:** Signature includes `from_friend: str = "HomeClaw"`. Callers (TAM reminder, cron, inbound fallback) pass the appropriate friend_id or `"HomeClaw"`. See [CompanionPushNotifications.md](CompanionPushNotifications.md); update that doc to include **from_friend** in APNs and FCM payloads.

---

## 9. Channels (Telegram, Matrix, etc.)

- **Routing:** When a message arrives from a channel (Telegram, Matrix, Email, etc.), Core matches the channel identity (e.g. `matrix:@user:domain`) to a **user** in user.yml (email/im/phone). The conversation is always with **HomeClaw** for that user. So:
  - Request → resolve user from channel id → set **friend_id = "HomeClaw"** for this request.
  - All storage and memory for that channel conversation use **(user_id, HomeClaw)**.
- **Last channel:** Stored per user (and implicitly HomeClaw). When we send a reply back to the channel, we use the saved last channel for that user.
- **Companion vs channel:** Same user can use both Companion (chat with Sabrina or HomeClaw) and channels (chat with HomeClaw only). Data is isolated by (user_id, friend_id); channel data does not mix with (user_id, Sabrina).

---

## 10. Profile (HomeClaw only)

- **Who uses profile:** Only **HomeClaw** generates and uses the user profile (extraction from chat, storage, injection into prompt). Other friends do not read or write profile.
- **Where stored:** Under (user_id, HomeClaw), e.g. `database/profiles/{user_id}/profile.json` or `profiles/{user_id}_HomeClaw.json`. Exact path is implementation-defined; key point is one profile per user, owned by HomeClaw.
- **When used:** When the active friend is **HomeClaw** (e.g. channel or user chose HomeClaw in Companion), load profile for that user and inject into the prompt. When the active friend is Sabrina, do not inject profile (unless we later add a “profile visible to all friends” option).

---

## 11. Core endpoints and WebSocket: per-user and per-(user_id, friend_id)

Many Core endpoints and all WebSocket message flows must be **per user** and, where applicable, **per (user_id, friend_id)**. Implementations must require **user_id** (and **friend_id** when relevant) so one user cannot clear or read another user’s data. Below is an audit; each endpoint/flow should be updated to accept and enforce these parameters (e.g. via auth token → user_id, and query/body for friend_id when needed).

### 11.1 Endpoints that must be per-user (and where relevant per-friend)

| Endpoint | Current behavior | Required change |
|----------|------------------|------------------|
| **GET/POST /memory/reset** | Clears all: RAG memory, chat, AGENT_MEMORY, daily memory, profiles, recorded events, cron jobs, one-shot reminders. | Accept **user_id** (required). Optionally **friend_id** or “all friends.” Clear only that user’s data (and that friend’s if friend_id given). If friend_id omitted, clear all (user_id, *) for that user. |
| **GET/POST /knowledge_base/reset** | Clears entire KB (all users). | Accept **user_id** (required) and **friend_id** (optional). Clear only that (user_id, friend_id) KB. If friend_id omitted, clear all friends’ KB for that user. |
| **GET /api/sessions** | Returns sessions (no user filter). | Accept **user_id** (required) and **friend_id** (optional). Return only sessions for (user_id) or (user_id, friend_id). Auth: token identifies user_id; do not return other users’ sessions. |
| **POST /api/skills/clear-vector-store** | Clears skills vector store (global). | If this store is per-user or per-friend, add **user_id** (and optionally **friend_id**). Otherwise document as global admin-only. |
| **POST /api/testing/clear-all** | Unregisters plugins and clears skills vector store. | Typically admin/test; can remain global or require user_id for a “clear my data” variant. |
| **GET /api/config/users** | Returns all users (for Control UI / config). | For **Companion:** add a separate endpoint or mode that returns **only the current user** (from auth) and **that user’s friends**. Companion must never receive the full user list. |
| **POST /api/companion/push-token**, **DELETE /api/companion/push-token** | Already take **user_id** in body/query. | Ensure token is stored and removed only for that user_id; no cross-user access. |
| **GET /api/sandbox/list** | Takes `scope` (user_id or companion) and `path`. | **scope** = user_id; optionally **friend_id** in path (e.g. list `Sabrina/output`). Ensure scope is the authenticated user only. |
| **POST /inbound** | Takes user_id, text, etc. | Must accept **friend_id** (or default HomeClaw). All downstream storage uses (user_id, friend_id). |
| **GET /files/out** | Token-based; scope in token. | Token encodes (user_id, path); path can be under user or under user/friend_id. No change if scope is already per-user. |

### 11.2 WebSocket /ws

| Message / flow | Current behavior | Required change |
|----------------|------------------|------------------|
| **Connect** | Auth (API key). | Same; auth identifies the client (and optionally the user if we pass user in token or first message). |
| **register** | Sends `user_id`; Core stores `_ws_user_by_session[session_id] = user_id`. | Also send **friend_id** (optional at register). Store (user_id, friend_id) per session so that when we push to this session we know which friend’s chat to associate. If friend_id not sent at register, require it on each **message** (so each message has user_id + friend_id). |
| **Message (send)** | InboundRequest with user_id, text, ... | Require **friend_id** in the JSON (or use session’s current friend_id). Core uses (user_id, friend_id) for chat history, memory, and reply. |
| **Push (inbound_result / event push)** | Core sends to sessions where _ws_user_by_session[sid] == user_id. | Payload already includes **from_friend**. App uses from_friend to route to the correct chat. No change if from_friend is set. |
| **Reply** | Same connection gets reply. | Reply is for the (user_id, friend_id) of the request; app shows in that friend’s thread. |

### 11.3 Summary

- **Clear / reset endpoints:** Memory reset, KB reset, and any “clear my data” must take **user_id** (from auth or body) and optionally **friend_id**, and must only clear that user’s (and that friend’s) data.
- **List endpoints:** Sessions list (and any “list my X”) must filter by **user_id** (from auth) and optionally **friend_id**.
- **Config / users:** Companion must never get the full user list; only “current user + friends” endpoint.
- **WebSocket:** Register and every message must carry **user_id** and **friend_id** so Core and app stay in sync for which chat thread is active and which friend a push is from.

---

## 12. Implementation steps (order and care)

Implement in the following order, with tests and backward-compatibility checks where needed.

1. **user.yml schema and loading**
   - Extend user.yml to support **friends** list (name, relation, who, identity). Ensure User dataclass or loader can read friends. Keep existing user fields (id, name, username, password, email, im, phone, permissions). Validate: first friend may be required to be HomeClaw (or auto-add if missing).
   - No change yet to routing; only config and parsing.

2. **Request context: user_id + friend_id**
   - Ensure every request that goes through Core has **user_id** (system user id) and **friend_id** (which friend this conversation is with). For channels, set friend_id = "HomeClaw". For Companion, client sends friend_id (or default HomeClaw). Thread (user_id, friend_id) through ToolContext and all storage keys.

3. **Memory (MD) paths**
   - Switch MD memory paths to per (user_id, friend_id): `memories/{user_id}/{friend_id}/agent_memory.md` and daily. Update load/write for agent_memory and daily to use these paths. Ensure append_* tools and bootstrap injection use the same paths. Migrate existing data if needed (e.g. copy old single-path memory to (user_id, HomeClaw)).

4. **Profile path and scope**
   - Store profile under (user_id, HomeClaw). Update profile load/save to use that path. Ensure only HomeClaw uses profile in the prompt.

5. **Sandbox: auto-create all folders**
   - Extend `ensure_user_sandbox_folders` (or equivalent) to create: for each user, user-level folders (downloads, documents, output, work, share) and for each (user_id, friend_id) the friend root, output, knowledge. Call this at startup after loading user.yml. Ensure no crash on mkdir failure; log only.

6. **Friend identity (identity.md)**
   - **identity** in user.yml: empty or one .md filename; default `identity.md`. Read from friend root; if file missing, skip. Inject content into the **same prompt block that uses personalities** (who). Cap length. Add example file **config/examples/friend_identity.md** (see §7).

7. **Push: from_friend**
   - Already added in code: deliver_to_user(..., from_friend=...), push_send and APNs/FCM payload include from_friend. Ensure TAM/cron and inbound fallback pass the correct from_friend. Update CompanionPushNotifications.md.

8. **Chat and sessions: (user_id, friend_id)**
   - Change chat history and session storage keys to include friend_id. Update get_session_id and all DB/file keys. Ensure sessions_list and history APIs filter by (user_id, friend_id).

9. **RAG / Cognee: namespace by (user_id, friend_id)**
   - Add (user_id, friend_id) to RAG namespace or filter. KB path is already per-friend under sandbox; ensure Cognee/embedding use the same scope.

10. **Cron / reminders: (user_id, friend_id)**
    - Store reminder/cron with (user_id, friend_id). On fire, deliver to user_id with from_friend = friend_id. Payload includes friend_id for UI.

11. **Channels: route to (user_id, HomeClaw)**
    - When a channel request is matched to a user, set friend_id = "HomeClaw" for that request. All channel traffic uses (user_id, HomeClaw). No change to channel delivery; only scoping.

12. **Companion app: login, friends, push routing, settings**
    - Implement login (username/password) → user_id + token (§3.1). API for “my friends” only (§3.2). Every request and WS message: user_id + friend_id (§3.3). Push: read from_friend and route to correct friend chat; on tap open that friend’s chat (§3.4). Settings: user info, change password, default friend, Core URL, notifications (§3.5). No “all users” list.

13. **Core endpoints and WebSocket: per-user and per-(user_id, friend_id)**
    - Audit and update endpoints (§11): /memory/reset, /knowledge_base/reset, /api/sessions, config/users (Companion gets only current user + friends), sandbox/list, inbound — all require user_id (from auth) and friend_id where relevant. WS: register and messages carry friend_id; push payload already has from_friend.

14. **File tools and path resolution**
    - Path resolution already supports user_id; add friend_id where needed (e.g. friend output path `{friend_id}/output/`, friend knowledge `{friend_id}/knowledge/`). Default path = user root. See FolderSemanticsAndInference.md.

15. **Docs and config examples**
    - Update README and config examples for user.yml (friends, identity). Update MultiUserSupport.md and related docs to describe the new model. Add a short “Migration” section if we support migrating from old config.

---

## 13. Summary table

| Area | Key decision |
|------|----------------|
| **user.yml** | Users have friends list; each friend: name (friend_id), relation, who, identity (file in friend root). HomeClaw first, no who. |
| **Companion** | Login, friends list/select, user_id + friend_id on every request/WS; push: from_friend → route to friend chat; settings: user, password, default friend, Core URL. Endpoints per-user; no full user list. |
| **Channels** | Resolve channel → user; friend_id = HomeClaw. Data under (user_id, HomeClaw). |
| **Data** | All data per (user_id, friend_id): chat, sessions, memory, KB, cron, profile (profile only for HomeClaw). |
| **Memory (MD)** | memories/{user_id}/{friend_id}/agent_memory.md, daily. |
| **Profile** | Only HomeClaw; stored under (user_id, HomeClaw). |
| **Sandbox** | Auto-create user + per-friend folders; friend root has identity.md (optional), output/, knowledge/. |
| **identity** | Empty or one .md filename (default identity.md) in friend root; read and inject into same block as personalities; missing file = skip. Example: config/examples/friend_identity.md. |
| **Push** | Payload includes from_friend (friend_id or "HomeClaw"). |
| **Endpoints / WS** | Memory/KB reset, sessions, config/users, sandbox, inbound: require user_id (and friend_id where relevant). WS register + message: friend_id; push: from_friend. |
| **Implementation** | 15 ordered steps; config first, storage paths, identity, push, chat/sessions, RAG, cron, channels, Companion, endpoints/WS, file tools, docs. |

This document is the single source of truth for the user/friends model. Implement step by step and update this doc if the design evolves.
