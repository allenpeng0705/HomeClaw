# Companion feature design (combined with one user or system)

This doc describes how the **Companion app** works like a **friend list** (e.g. WhatsApp-style): who you talk to, and how **combine with one user** affects only **talking with System**. The **Friends plugin** (persona: girlfriend/boyfriend/friend/parent etc.) is one of the entries in that list.

**User-facing doc:** [docs/friends-plugin.md](../docs/friends-plugin.md) — summary for users (Friends plugin, Friend chat, combine with user).

---

## Companion app friend list and combine-with-user

The Companion app has a **friend list** (like WhatsApp's). Currently it has **two** entries:

1. **System** — talk with Core (the main assistant).
2. **Friend** — talk with the Friends plugin (the persona).

**Combine with one user** only affects **how the app talks with System**:

- **Nothing combined** (no user selected): the app uses **user_id "companion"** to talk with System (Core). Chat and memory for that System conversation are scoped to user **"companion"**; sandbox folder is **"companion"**.
- **Combined with one user** (user selected from config/user.yml, e.g. via picker): the app uses **that user's user_id** (e.g. alice) to talk with System (Core). Chat and memory for that System conversation are scoped to that user; sandbox is that user's folder.

**Friend** is the other entry. When the user opens the Friend chat and sends a message, the app sends data (e.g. session_id=friend, conversation_type=friend) so Core routes to the Friends plugin. Combine-with-user does **not** change who System or Friend are; it only changes **which identity (user_id) is used when talking to System**.

**Summary:** Friend list = System + Friend. Combine with one user → only affects talking with **System** (user_id = "companion" vs that user's id). Talking with **Friend** is separate (dedicated chat view, Core routes to Friends plugin).

---

## User design: combine with one user vs not (for System only)

When talking with **System** (Core):

1. **Combined with one user**  
   The user selects a **user from config/user.yml** (e.g. via a picker). All messages to System use **that user's user_id**. Chat history and memory are saved to **that user's** chat history and memories (main flow; channel = companion). Sandbox is that user's folder.

2. **Nothing combined (default)**  
   The user selects **"System"** or no user. The app uses **user_id "companion"** to talk with System. All data (chat, memory, delivery) for that System conversation is scoped to user **"companion"**; sandbox folder is **"companion"** (e.g. `workspace/companion/`).

### Single entry point: GET /api/config/users

Core exposes **one endpoint** for Companion "combine with user" options: **GET /api/config/users** (same auth as `/inbound` when `auth_enabled`). It returns users from **user.yml**:

- **Response:** `{ "users": [ { "id", "name", "email", "im", "phone", "permissions" }, ... ] }`
- **Use:** Companion Settings → "Identity when talking to System" loads this list; the user picks "System (default)" or one of these users. The same list can be shown or used on other settings pages (e.g. Manage Core uses it to view/edit user.yml). Add or edit users via Core **Manage Core (core.yml & user.yml)** or **POST/PATCH /api/config/users**; then refresh the picker to see updates.

---

## Friends plugin: the "Friend" entry in the list

The **Friend** in the Companion app's friend list is implemented by the **Friends plugin** — a persona (girlfriend/boyfriend/friend/parent etc.) with its own chat and behaviour. All communication is still **to or from Core**; the plugin is a **role** Core takes when the client says the message is for the Friend.

- The app has a **dedicated chat view** for the Friend (like opening a chat with a contact). When the user sends a message from that view, the app sends data (e.g. **`session_id=friend`**, **`conversation_type=friend`**, **`channel_name=friend`**) so **Core knows the message is for the Friends plugin** and routes to it.
- **How Core knows:** Core treats a message as "for the Friend" when the client sends **`conversation_type`**, **`session_id`**, or **`channel_name`** equal to the configured **`session_id_value`** (default **`"friend"`**), or when the message starts with the configured **keyword**. From the Friend chat view the app sends one of these; from the System (Assistant) chat it does not, and Core uses the main flow.
- **Plugin offline:** If the Friends plugin is **not running** (connection refused, timeout) or **not registered** (plugin not started or unregistered), Core responds with a short user-facing message: **"{name} is offline now."** where `{name}` is the plugin's display name (e.g. **Friends**). The client receives HTTP 200 and this text so the Companion app can show it in the Friend chat instead of an error or the main assistant reply.

---

## Naming: Companion vs Friends (avoid mixing)

| Term | Meaning |
|------|--------|
| **Companion app** | The client (mobile/desktop app). Product name; does not change. |
| **session_id_value** | Config value that means "this message is for the Friend". Client sends `conversation_type`, `session_id`, or `channel_name` equal to this; Core routes to the Friends plugin. Default **`"friend"`** so it is not confused with user_id `"companion"`. |
| **Friends plugin** | The external plugin (plugin_id `"friends"`) that implements the Friend role. Backend only. |
| **user_id "companion"** | The **system user** when not combined: sandbox folder, last-channel key, and (if we ever store Friend chat in Core) storage key. Used only for "System" / uncombined mode. |

So: **Companion app** = client name; **session_id_value** = routing signal ("Friend chat"); **Friends plugin** = backend role; **user_id "companion"** = system user for uncombined mode.

---

## Storage: chat history and memory (Companion app ↔ Friends plugin)

| Scenario | Chat history | Memory (RAG) |
|----------|--------------|--------------|
| **System mode** — Companion app **not** combined with a user; user talks to **Friend** (Friends plugin) | **Friends plugin only:** `database/friends_store/` (one thread per user_id + persona_name; Core sends user_id `"companion"` when app is in system mode). Core does **not** write to Core chat DB for this path; the request returns after calling the plugin. | **Core memory (RAG)** under **user_id `companion_friend`** (not `"companion"`): the Friends plugin calls Core **POST /api/plugins/memory/add** and **POST /api/plugins/memory/search** with user_id **`companion_friend`** when the app is in system mode (user_id "companion"), so Friend memories are **never mixed** with Assistant or other users. Same RAG backend as Core; isolated by user_id. |
| **Friend (combined with user)** — User selected in picker; Companion app sends that user_id and session_id_value | **Core only:** Same as main assistant — Core chat DB + Core memory, keyed by **that user_id**, with `channel=companion` in metadata. No Friends plugin store; request goes through main flow (`process_text_message`). | **Core memory** for that user_id; same as main assistant, scoped to that user. |
| **Assistant** — Companion app talks to main assistant (no session_id_value) | **Core only:** Core chat DB + Core memory, keyed by user_id (or "companion" if app did not send a user). | **Core memory** for that user_id. |

**Summary:** In **system mode** the Companion app talks to Core with **user_id "companion"**. When the user uses the **dedicated Friend chat view** and the app sends session_id=friend (or conversation_type=friend, channel_name=friend), Core routes to the Friends plugin; those messages are stored **only in the Friends plugin store** (`database/friends_store/`). Core does not duplicate them into Core chat history. Friend long-term memory is stored in **Core RAG under user_id `companion_friend`** (not `"companion"`), so it **cannot be mixed** with other users or with the Companion app talking to Core (Assistant). Messages between the Companion app and **Core** (Assistant or combined-with-user Friend) are stored in **Core chat DB and Core memory** per user (e.g. user_id `"companion"` when app is in system mode and not in the Friend chat view).

**Terminology:** **Friend list** = System + Friend (like WhatsApp). **Combine with one user** = only affects **talking with System** (user_id "companion" vs that user's id). **System** = Core (main assistant). **Friend** = Friends plugin (persona). When the user opens the Friend chat, the app sends session_id=friend (etc.) so Core routes to the Friends plugin.

**Isolation guarantee:** When the app is in system mode and the user uses the **dedicated Friend chat view** (app sends session_id=friend etc.), chat and memories for that Friend conversation are **not mixed** with (1) any other user (alice, bob, etc.), (2) the Companion app talking to Core (Assistant), or (3) combined-with-user Friend (which uses that user's Core chat/memory). Chat is in friends_store only; memory is in Core RAG under `companion_friend` only.

---

## 1. Principle: combine-with-user only affects System

- **Combine with one user** only affects **talking with System** (Core): if nothing combined → user_id **"companion"**; if combined with a user → that user's user_id. **Friend** is a separate entry in the friend list; the app signals (session_id=friend etc.) so Core routes to the Friends plugin.
- **Do not mix** chat/memory across users when talking with System. Use the same user_id for that System conversation.

---

## 2. Chat history (per user)

- **Key:** Conversation is keyed by **sender** (user) and **responder** (companion name).
- **When combined (picker = a user from user.yml):** All companion chats go into **that user's memory and chat histories**; the channel is **companion**. So storage is the main user DB (memory + chat history), not a separate companion-only store. One unified history per user, with channel distinguishing assistant vs companion.
- **When not combined (picker = "System"):** Chat is stored **only in the Friends plugin store** (`database/friends_store/`) under user_id `"companion"`; Core does not duplicate it to Core chat DB (see [Storage](#storage-chat-history-and-memory-companion-app--friends-plugin) above).
- So: when combined, one thread per (user, companion) in the user's main chat/memory; when System, chat lives only in Friends store.

---

## 3. Memory (RAG, per user)

- **When combined (picker = user):** Companion uses the **same** user's memory and chat history as the main assistant; RAG and chat are scoped to that user, with channel = companion for companion traffic. So one user, one memory/chat store; channel distinguishes assistant vs companion.
- **When not combined (picker = System):** Memory and chat are scoped to the **one special user "companion"** (see §7, §7a).
- **Scope:** When the companion uses RAG, **search memory for that user only** — pass `user_id` (and optionally channel filter). No mixing across users.

---

## 4. Proactive delivery (per user)

- **Goal:** When the companion sends a proactive message (e.g. after idle, or morning/night), it must go to **that user**, not to whoever was “latest” globally.
- **Mechanism:** Use a **per-user channel key** for delivery, not the global “latest” key.
  - **Persist last channel per user:** When a user talks (e.g. via WebChat or a channel), save the channel/key for that user (e.g. `app_id:user_id:session_id` or `user_id`) in the last-channel store.
  - **Proactive send:** When the companion runs a scheduled/idle task for user U, call `send_response_to_channel_by_key(key_for_user_U, response)` instead of `send_response_to_latest_channel(response)`.
- So: proactive companion messages are **combined with one user** by targeting that user’s channel key.

---

## 5. Summary

| Aspect | Combined (picker = user) | Not combined (picker = System) |
|--------|---------------------------|---------------------------------|
| **Chat / memory** | All chats go into the user's memory and chat histories; **channel = companion**. | Current behavior (e.g. companion store or default user). |
| **Picker** | User selects a user from user.yml; client sends that `user_id`. | User selects "System"; no per-user binding. |
| **Location** | Companion app, WebChat, control UI ask for location permission; when granted, send location → latest location per user. | Same clients can still send location if permitted; when System, stored for default user if applicable. |

When combined, the companion is implemented so that it receives **one user_id** (from the picker) and all storage (memory, chat history, profile, latest location) is for that user, with channel = companion where applicable.

---

## 6. Scope: companion app, WebChat, homeclaw-browser; external plugin

**In scope (first-class support):** We build and control the companion experience for:

- **Companion app** — dedicated app with Assistant vs Companion UI.
- **WebChat channel** — WebChat with tabs/sessions for Assistant and Companion.
- **homeclaw-browser** — UI control and session/target selection there.

These clients send **target** or **session** (e.g. `conversation_type=friend`, `session_id=friend`) so we know the chat is for the Friend without inspecting message content.

**Separation from existing logic:** The companion feature is implemented as an **external plugin** (the **Friends** plugin, `external_plugins/friends`), not inside core request flow. Existing channels and logic stay unchanged. The plugin is invoked only when the entry point (bridge, WebChat, app) has determined “this request is for the companion” (by target/session or by keyword on other channels). So core and other plugins remain untouched.

**Other channels (e.g. WhatsApp, Telegram):** If we want a channel that **cannot** send target/session to support the companion, we use a **configurable keyword** (e.g. the companion’s name). Examples: *“Veda, how are you today?”*, *“Veda, good night”*. The keyword (e.g. `Veda`) is a **configurable string** (per user or global). When the message starts with (or clearly addresses) that keyword, we treat the chat as for the companion. This is opt-in for those channels and documented so users know the trigger.

**Companion name = unique identity and keyword:** The companion has a **unique name** (e.g. "Veda"). That name is the companion's identity — the companion feature **knows** its name. On other channels, that **same name is the key** to find and route to the companion (e.g. "Veda, how are you today?"). So one configurable string serves as both the companion's identity and the routing trigger. Document this so users know the trigger on channels that don't send target/session.

---

## 7. Data separation and combined mode

**When the client is combined with a user (picker = a user from user.yml):** All companion chats go into **that user's memory and chat histories**; the channel is **companion**. So there is no separate companion-only store for that case — the user's main memory and chat history include both assistant and companion traffic, with channel distinguishing them. This gives one unified history per user.

**When the client is not combined (picker = "System"):** Core treats the Companion app as **one special user** with identity **"companion"** (e.g. `system_user_id = "companion"`). All messages between uncombined Companion and Core belong to this companion user: chat history, memory, workspace, and delivery are scoped to **"companion"**. So "System" = no per-human-user binding; one logical "companion" user for all uncombined Companion traffic.

**Summary:** Combined → user's memory and chat, channel = companion. Not combined (System) → one special user **"companion"**; all uncombined Companion data and delivery target that identity. Companion app, WebChat, and control UI provide a picker (users from user.yml + "System") and request location permission on their platforms (Android, iOS, macOS, Windows, Linux).

---

## 7a. Delivery to Companion app (uncombined)

- **Cron and LLM:** Messages from cron tasks (reminders, run_skill, run_plugin) or from the LLM that target the **companion user** are sent to the Companion app. Core uses the reserved channel key **"companion"** for delivery: `send_response_to_channel_by_key("companion", response)`.
- **Last channel for "companion":** When any uncombined Companion client sends a request, Core persists that channel under the key **"companion"** (in addition to the default/session keys). So the last Companion client that talked to Core is the delivery target for "companion". Cron/reminders created from the Companion app (System picker) use `channel_key = "companion"` so they deliver back to Companion.
- **Multi-platform channels:** The Companion app exists on multiple platforms (macOS, iOS, Android, Windows, Linux). Each platform is a **channel** of the companion user. Currently, delivery to "companion" goes to **one** channel (the last one that contacted Core). Any Companion client that is **connected** and has **recently sent** a request will receive messages targeted at the companion user when it is the last companion channel. Future: support broadcasting to **all** connected Companion channels (e.g. store multiple channel descriptors for key "companion" and send to each).

---

## 8. Future: multiple companions

The design should allow running **multiple companions** with different names (e.g. "Veda", "Maya"). Each companion has its own **unique name** (and thus its own keyword on other channels) and its **own separate data** (chat history, messages, storage) — keyed by companion name and user_id. Routing and storage are keyed by **companion name** so multiple companions can coexist without mixing data.

---

## 9. How we know the user is talking with the companion (routing / disambiguation)

**Problem:** If the same channel identity (e.g. one WhatsApp number) is used for both the main assistant and the companion, we **cannot tell** from the message alone whether the user is talking to the **assistant** or to the **companion**. So we need a clear way to know “this message is for the companion.”

**Options (prefer 1 or 2; use 3 only as fallback):**

| Option | How it works | Pros / cons |
|--------|----------------|-------------|
| **1. Client / channel sends target** | The client (WebChat, bridge, app) lets the user choose “Assistant” vs “Companion” (e.g. two chats or tabs) and sends a **flag** with the request: e.g. `conversation_type=friend` or `session_id=friend` (matching session_id_value). Core routes to the Friends plugin when that flag/session is present. | **Best:** No guessing, no keywords. Requires client/channel to support two “conversations” and send the right metadata. |
| **2. Separate channel or identity** | Companion is only available on a **different** channel (e.g. companion in WebChat only, assistant on WhatsApp) or a different “identity” (e.g. second WhatsApp number for companion). So **by channel or sender identity** we know it’s the companion. | Clear separation. User may prefer one number for everything. |
| **3. Keywords / trigger phrase** | User says a trigger at the start (e.g. “/companion”, “Hey [companion name]”, “talk to Maya”) → route to companion; otherwise route to assistant. Core (or plugin) inspects the message and switches mode. | Works when the channel **cannot** send a target. Fragile: false positives (“Hey Maya” to the assistant), and user must remember the trigger. |

**Recommendation:** Prefer **1 (client sends target or session)** so Core doesn’t have to guess. If the channel cannot send metadata (e.g. plain WhatsApp with one number), use **3 (keywords)** as fallback and document the trigger clearly. Option **2** is good when you can afford a separate channel or number for the companion.

**Companion app and WebChat:** We control these clients, so we can send target/session there (e.g. "Assistant" vs "Companion" tab → different `session_id` or `conversation_type`). We **do not need a new user** for the companion: the **same real user** (the human) is the `user_id` in both flows. The companion is a **conversation mode** for that user (distinguished by session or conversation_type), not a separate user identity. So: one user_id, two conversation types (assistant vs companion).

**User picker (combined vs System), storage when combined, and location permission:**

- **Picker:** The Companion app (and WebChat, homeclaw-browser) must provide a **picker list** to select which user to combine with. The list contains:
  - Every user defined in `config/user.yml` (e.g. from Core API that returns allowed users).
  - **"System"** — meaning **no combination**; when selected, the app works like today (current logic, no per-user binding).
- **When a user is selected (combined):** All companion chats for that session go into **that user's memory and chat histories**; the channel is **companion**. So when combined, we do **not** keep companion data in a separate companion-only store — we store in the main user's memory and chat history with channel = companion. The user gets one unified history (assistant + companion) keyed by that user.
- **When "System" is selected (not combined):** No combination; behavior stays as it is now (e.g. default "companion" user or plugin-specific storage, no per-user identity from the picker).
- **Location permission:** The **Companion app** must request **location permission on all platforms**: **Android**, **iOS**, **macOS**, **Windows**, and **Linux**. On Android/iOS/macOS we declare platform-specific permissions (manifest/Info.plist); on **Windows** and **Linux** the system may prompt or the user allows location in **Settings → Privacy → Location** (Windows) or the desktop environment’s location settings (Linux). **WebChat** (channels/webchat) and **homeclaw-browser control UI** (system_plugins/homeclaw-browser/control-ui) use the browser **Geolocation API** when available: before each send they call `navigator.geolocation.getCurrentPosition`; if the user grants permission, they add `location: "lat,lng"` to the payload so Core stores latest location per user (see SystemContextDateTimeAndLocation.md). If the browser does not support geolocation or the user denies, the message is sent without location.

**Linking the app to a user in user.yml (multi-user / family):** When multiple people use the same Companion app (or WebChat, homeclaw-browser), each person uses the **picker** to select their identity (a user from user.yml). The client sends that **user_id** with every request. Core resolves it via `check_permission` and sets `system_user_id`; when combined, all storage (memory, chat history, profile, latest location) is for that user, channel = companion where applicable. **"System"** in the picker means no combination and current behavior.

**Location: per-user vs shared.** When the Companion app sends location (e.g. "lat,lng"), Core stores it as **latest location** and uses it in system context (weather, scheduling, etc.). Storage key is **per-user when combined**: if the app sends user_id "alice", latest location is stored under "alice". When **not combined** (user_id "companion" or "system"), Core stores under a **shared key** ("companion") so it can be used as fallback for all users. So: combined → location is per that user; not combined → location is shared (one "companion" latest location).

**Implementation note:** The entry point (bridge, WebChat, companion app, homeclaw-browser) decides “this request is for the companion” (using `conversation_type` / `session_id` for in-scope clients, or the configurable keyword for other channels), then invokes the **Friends plugin** only. Core/main flow is not involved.

---

## 10. Implementation path

The companion is **dedicated to one user** per conversation. Suggested order of work:

1. **External plugin**  
   Implement as an **external plugin** (the **Friends** plugin, `external_plugins/friends`) — separate from core and other channels. The plugin receives `user_id` / `user_name` with every request and uses them for all chat, memory, and delivery. Entry points (companion app, WebChat, homeclaw-browser) send target/session; for other channels, the bridge or adapter detects the configurable keyword (e.g. companion name “Veda”) and routes to the plugin.

2. **Per-user identity**  
   Every companion call (reactive and proactive) must have a **dedicated user** (user_id). No “global” or anonymous companion; always pass the user this companion is for.

3. **Chat**  
   Use `get_latest_chats_by_role(sender_name=user_name, responder_name=companion_name)` and `add_chat_history_by_role(...)` so the thread is **dedicated** to that user.

4. **Memory (RAG)**  
   Use Core/memory search with `user_id` (and filters if needed) so companion context is **dedicated** to that user.

5. **Proactive + delivery**  
   Persist last channel per user (e.g. when the user sends a message, save key `app_id:user_id:session_id` or similar). For proactive messages, call `send_response_to_channel_by_key(key_for_that_user, response)` so the message is **dedicated** to that user.

6. **Config**  
   All companion settings live on the **plugin side** (Friends plugin), not in Core. Core only stores routing: `enabled`, `plugin_id` (e.g. `friends`), `session_id_value`, `keyword` (for message-prefix routing on channels that can't send session_id). Name, character (girlfriend/boyfriend/wife/husband/sister/brother/child/friend/parent), language, response length, and idle-nudge behaviour are **configurable and dedicated** in the plugin: plugin config file (e.g. `external_plugins/friends/config.yml`) for defaults; per-user overrides in the friends store (`database/friends_store/{user_id}_settings.json`) or via the plugin API `GET/POST .../settings/{user_id}`. The plugin merges per-user overrides with plugin config and uses them in the system prompt.
