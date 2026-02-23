# Companion feature design (combined with one user)

This doc describes how a **companion** feature (girlfriend/boyfriend/parent/friend/children persona) should be **combined with one user**: chat history and memory are scoped to that user only — no mixing with other users.

---

## 1. Principle: one user per companion conversation

- **Companion is combined with one user.** Each user has their own companion conversation, chat history, and (optionally) companion-specific memory.
- **Do not mix** that user’s companion data with other users’ chat history or memories. Use the same user identity (user_id / user_name) everywhere for that companion thread.

---

## 2. Chat history (per user)

- **Key:** Conversation is keyed by **sender** (user) and **responder** (companion name).
- **When combined (picker = a user from user.yml):** All companion chats go into **that user's memory and chat histories**; the channel is **companion**. So storage is the main user DB (memory + chat history), not a separate companion-only store. One unified history per user, with channel distinguishing assistant vs companion.
- **When not combined (picker = "System"):** Use current behavior (e.g. companion-specific storage or default "companion" user). See §7.
- So: when combined, one thread per (user, companion) in the user's main chat/memory; when System, behavior as today.

---

## 3. Memory (RAG, per user)

- **When combined (picker = user):** Companion uses the **same** user's memory and chat history as the main assistant; RAG and chat are scoped to that user, with channel = companion for companion traffic. So one user, one memory/chat store; channel distinguishes assistant vs companion.
- **When not combined (picker = System):** Use current behavior (e.g. dedicated companion store or default user scope). See §7.
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

These clients send **target** or **session** (e.g. `conversation_type=companion`, `session_id=companion`) so we know the chat is for the companion without inspecting message content.

**Separation from existing logic:** The companion feature is implemented as an **external plugin**, not inside core request flow. Existing channels and logic stay unchanged. The plugin is invoked only when the entry point (bridge, WebChat, app) has determined “this request is for the companion” (by target/session or by keyword on other channels). So core and other plugins remain untouched.

**Other channels (e.g. WhatsApp, Telegram):** If we want a channel that **cannot** send target/session to support the companion, we use a **configurable keyword** (e.g. the companion’s name). Examples: *“Veda, how are you today?”*, *“Veda, good night”*. The keyword (e.g. `Veda`) is a **configurable string** (per user or global). When the message starts with (or clearly addresses) that keyword, we treat the chat as for the companion. This is opt-in for those channels and documented so users know the trigger.

**Companion name = unique identity and keyword:** The companion has a **unique name** (e.g. "Veda"). That name is the companion's identity — the companion feature **knows** its name. On other channels, that **same name is the key** to find and route to the companion (e.g. "Veda, how are you today?"). So one configurable string serves as both the companion's identity and the routing trigger. Document this so users know the trigger on channels that don't send target/session.

---

## 7. Data separation and combined mode

**When the client is combined with a user (picker = a user from user.yml):** All companion chats go into **that user's memory and chat histories**; the channel is **companion**. So there is no separate companion-only store for that case — the user's main memory and chat history include both assistant and companion traffic, with channel distinguishing them. This gives one unified history per user.

**When the client is not combined (picker = "System"):** Use current behavior: no per-user binding; companion may use a default user (e.g. "companion") or plugin-specific storage as today. So "System" = no combination; data handling remains as before (e.g. separate or default store).

**Summary:** Combined → user's memory and chat, channel = companion. Not combined (System) → works like now. Companion app, WebChat, and control UI provide a picker (users from user.yml + "System") and request location permission on their platforms.

---

## 8. Future: multiple companions

The design should allow running **multiple companions** with different names (e.g. "Veda", "Maya"). Each companion has its own **unique name** (and thus its own keyword on other channels) and its **own separate data** (chat history, messages, storage) — keyed by companion name and user_id. Routing and storage are keyed by **companion name** so multiple companions can coexist without mixing data.

---

## 9. How we know the user is talking with the companion (routing / disambiguation)

**Problem:** If the same channel identity (e.g. one WhatsApp number) is used for both the main assistant and the companion, we **cannot tell** from the message alone whether the user is talking to the **assistant** or to the **companion**. So we need a clear way to know “this message is for the companion.”

**Options (prefer 1 or 2; use 3 only as fallback):**

| Option | How it works | Pros / cons |
|--------|----------------|-------------|
| **1. Client / channel sends target** | The client (WebChat, bridge, app) lets the user choose “Assistant” vs “Companion” (e.g. two chats or tabs) and sends a **flag** with the request: e.g. `conversation_type=companion` or `target=companion`, or a distinct **session_id** for the companion thread (e.g. `session_id=companion` vs `session_id=main`). Core routes to the companion when that flag/session is present. | **Best:** No guessing, no keywords. Requires client/channel to support two “conversations” and send the right metadata. |
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
- **Location permission:** The **Companion app** must request **location permission on all platforms** (iOS, Android, desktop). **WebChat** and **homeclaw-browser control UI** must also ask for location permission when running in a context that supports geolocation (e.g. browser). So when the user grants it, these clients can send location to Core for latest-location-per-user (see SystemContextDateTimeAndLocation.md).

**Linking the app to a user in user.yml (multi-user / family):** When multiple people use the same Companion app (or WebChat, homeclaw-browser), each person uses the **picker** to select their identity (a user from user.yml). The client sends that **user_id** with every request. Core resolves it via `check_permission` and sets `system_user_id`; when combined, all storage (memory, chat history, profile, latest location) is for that user, channel = companion where applicable. **"System"** in the picker means no combination and current behavior.

**Implementation note:** The entry point (bridge, WebChat, companion app, homeclaw-browser) decides “this request is for the companion” (using `conversation_type` / `session_id` for in-scope clients, or the configurable keyword for other channels), then invokes the **companion plugin** only. Core/main flow is not involved.

---

## 10. Implementation path

The companion is **dedicated to one user** per conversation. Suggested order of work:

1. **External plugin**  
   Implement as an **external plugin** (separate from core and other channels). The plugin receives `user_id` / `user_name` with every request and uses them for all chat, memory, and delivery. Entry points (companion app, WebChat, homeclaw-browser) send target/session; for other channels, the bridge or adapter detects the configurable keyword (e.g. companion name “Veda”) and routes to the plugin.

2. **Per-user identity**  
   Every companion call (reactive and proactive) must have a **dedicated user** (user_id). No “global” or anonymous companion; always pass the user this companion is for.

3. **Chat**  
   Use `get_latest_chats_by_role(sender_name=user_name, responder_name=companion_name)` and `add_chat_history_by_role(...)` so the thread is **dedicated** to that user.

4. **Memory (RAG)**  
   Use Core/memory search with `user_id` (and filters if needed) so companion context is **dedicated** to that user.

5. **Proactive + delivery**  
   Persist last channel per user (e.g. when the user sends a message, save key `app_id:user_id:session_id` or similar). For proactive messages, call `send_response_to_channel_by_key(key_for_that_user, response)` so the message is **dedicated** to that user.

6. **Config**  
   All companion settings live on the **plugin side**, not in Core. Core only stores routing: `enabled`, `plugin_id`, `session_id_value`, `keyword` (for message-prefix routing on channels that can't send session_id). Name, character (girlfriend/boyfriend/wife/husband/sister/brother/child/friend/parent), language, response length, and idle-nudge behaviour are **configurable and dedicated** in the plugin: plugin config file (e.g. `examples/external_plugins/companion/config.yml`) for defaults; per-user overrides in the companion store (`database/companion_store/{user_id}_settings.json`) or via the plugin API `GET/POST .../settings/{user_id}`. The plugin merges per-user overrides with plugin config and uses them in the system prompt.
