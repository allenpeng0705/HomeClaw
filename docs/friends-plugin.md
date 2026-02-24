# Friends plugin (Companion persona)

The **Friends plugin** is a persona you can talk to from the **Companion app** or **WebChat**: a dedicated “Friend” chat (e.g. girlfriend/boyfriend/friend/parent) with its own conversation and memory, separate from the main **System** (Core) assistant. The Companion app shows a **friend list** with two entries: **System** and **Friend**. Choosing **Friend** routes your messages to the Friends plugin; choosing **System** talks to Core as usual.

**Design reference:** [docs_design/CompanionFeatureDesign.md](../docs_design/CompanionFeatureDesign.md).

---

## What is the Friends plugin?

- **Companion app:** Two chats — **System** (main assistant) and **Friend** (Friends plugin persona). Tapping **Friend** opens a dedicated chat; messages from that chat are sent with a routing signal so Core forwards them to the Friends plugin.
- **WebChat / control UI:** Same idea: dropdown **Assistant** vs **Friend**. When **Friend** is selected, the client sends **session_id** / **conversation_type** / **channel_name** = **friend** (Core config **companion.session_id_value**, default **"friend"**). Core routes those messages to the Friends plugin.
- **Friends plugin:** An external plugin (plugin_id **"friends"**) that implements the persona (name, character, language, etc.). It has its own chat store and can use Core’s memory APIs under a dedicated user_id so Friend memories don’t mix with the main assistant or other users.

So: **Companion app** = client; **Friend** = one of two chat targets; **Friends plugin** = backend that handles the Friend chat.

---

## Combine with one user (System only)

**“Combine with one user”** only affects **talking to System** (the main assistant), not the Friend chat.

- **Not combined (default):** When you talk to **System**, the app uses **user_id "companion"**. Chat history, memory, and sandbox (e.g. output folder) are scoped to **"companion"**.
- **Combined with a user:** In Companion Settings you can pick a **user from config/user.yml** (e.g. “Alice”). When you talk to **System**, the app then uses **that user’s user_id**. Chat history, memory, and sandbox are scoped to that user (e.g. **alice**). The **Friend** chat is unchanged; only System chat identity changes.

So: Friend list = System + Friend. Combine with one user → only changes **which user_id is used for System**; Friend is always a separate conversation with the Friends plugin.

---

## How to use

### Companion app

1. Open the app; you see the friend list (System, Friend).
2. **System** — Tap to chat with the main assistant. Identity is “companion” or the user you picked in Settings → “Identity when talking to System”.
3. **Friend** — Tap to chat with the Friends plugin. Messages from this chat go to the plugin; they are not stored in Core’s main chat DB. Friend memory is isolated (e.g. under **companion_friend** in RAG when not combined).

### WebChat / homeclaw-browser control UI

1. In the dropdown, choose **Assistant** (main chat) or **Friend** (Friends plugin).
2. **Assistant** — Same as main Core chat; **user_id** is the value in the user_id field (e.g. webchat_local).
3. **Friend** — Client sends **session_id=friend**, **conversation_type=friend**, **channel_name=friend**. Core routes to the Friends plugin.

### Core config

Under **companion:** in **config/core.yml** (or the config the Companion uses):

- **enabled** — Turn Companion/Friend routing on or off.
- **session_id_value** — Value the client sends for “Friend” chat (default **"friend"**). Client must send **session_id** / **conversation_type** / **channel_name** equal to this so Core routes to the Friends plugin.
- **plugin_id** — Plugin that implements the Friend (e.g. **"friends"**).

The Friends plugin itself is an external plugin (e.g. under **external_plugins/friends/**). It must be running and registered with Core so that when a message is routed to it, Core can call the plugin and return the reply.

---

## Naming (avoid mixing)

| Term | Meaning |
|------|---------|
| **Companion app** | The Flutter client (mobile/desktop). Product name. |
| **Friend** | The chat target in the app: “talk to the Friend persona”. |
| **Friends plugin** | The backend plugin (plugin_id **"friends"**) that implements the persona. |
| **session_id_value** | Config value (default **"friend"**) that tells Core “this message is for the Friends plugin”. |
| **user_id "companion"** | Used when Companion talks to **System** and is **not** combined with a user; sandbox and memory are under **"companion"**. |

---

## Summary

| Topic | Summary |
|-------|---------|
| **What** | Friends plugin = persona (Friend) you can chat with from Companion or WebChat; separate from the main System assistant. |
| **How** | In Companion: tap **Friend**. In WebChat/control UI: select **Friend** in the dropdown. Client sends session_id/conversation_type/channel_name = **friend**; Core routes to the Friends plugin. |
| **Combine with user** | Only affects **System** chat (which user_id is used). Friend chat is independent. |
| **Full design** | [docs_design/CompanionFeatureDesign.md](../docs_design/CompanionFeatureDesign.md) |
