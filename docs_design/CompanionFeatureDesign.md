# Companion feature design (unified users, no Friends plugin)

This doc describes how the **Companion app**, **WebChat**, and **homeclaw-browser control UI** work with **users** from **user.yml**. All users (normal and companion type) use the same logic: per-user sandbox, md memory, RAG memory, chat history, and knowledge_base. There is **no Friends plugin**; persona/identity is expressed via user **type** and optional **who** in user.yml.

---

## Logic: normal vs companion (with or without who)

1. **Normal user**  
   Works as before. No **who** field. Uses workspace bootstrap (IDENTITY.md, AGENTS.md, TOOLS.md) as the system-prompt identity/agents/tools. Same memory, chat, KB per user.

2. **Companion user without who**  
   Behaves like a normal user except they can **only** be used in companion app, WebChat, and homeclaw-browser control UI (no channels). Uses the same workspace bootstrap (default assistant description). Same memory, chat, KB per user.

3. **Companion user with who**  
   Core uses **one pre-defined prompt template** filled with all fields in **who** (including **description**) to form a single **Identity** block. This block is injected as the **only** assistant identity for that user: the **default assistant description** (workspace IDENTITY.md) is **not** included, so "who" fully describes the AI assistant. Agents and Tools from workspace are still included. Everything else is the same as a normal user: their own memory, chat history, knowledge base.

---

## User types in user.yml

Each user has a **type** field:

| Type | Meaning |
|------|--------|
| **normal** | Can use channels (email, im, phone) and can be combined with companion app. Has channel identities (im, email, phone) and permissions. No **who** field. |
| **companion** | Dedicated to companion app / WebChat / control UI only. No channels. Optional **who** dict: when present, defines the AI assistant identity (replaces default); when absent, uses default identity like a normal user. |

- **All users** (normal and companion) have: their own **sandbox folder** (`base/{user_id}/`), **share folder** access, **AGENT_MEMORY** and **daily memory** (md), **RAG memory**, **chat history**, and **knowledge_base** (when per-user KB is supported). Everything is per-user.
- **Companion-type users** do not have channel identities; they are matched by **id** or **name** when the client sends `user_id` (e.g. from companion app, WebChat, control UI).
- **Normal-type users** are matched by id/name or by channel identity (im, email, phone) for channel requests.

### **who** (companion-type users only; optional)

When a companion-type user has a **who** dict, Core builds a single **## Identity** section from it (pre-defined template; **no LLM call**). That section **replaces** the workspace Identity (IDENTITY.md) for this user. Supported keys:

| Key | Meaning |
|-----|--------|
| **description** | Optional free-text paragraph describing the companion (injected first in the identity block). |
| **gender** | e.g. female, male. |
| **roles** | List of roles, e.g. `['girlfriend', 'teacher']` — friend, girlfriend, boyfriend, wife, husband, sister, brother, child, parent, teacher, student, etc. |
| **personalities** | List, e.g. `['funny', 'sarcastic', 'humorous', 'knowledge']`. |
| **language** | Reply language: en, zh, ja, ko, es, fr, de, pt, it, etc. |
| **response_length** | short, medium, long. |
| **idle_days_before_nudge** | Reserved for future use: 0 = disabled; after N days without message, a future proactive/TAM feature may nudge. **Not injected** into the system prompt; Core does not use this value today. |

---

## Companion app / WebChat / control UI: list all users, chat with each

- **No "combine with one user"** — the client lists **all users** from user.yml (names shown: WebChat, System, Sabrina, AllenPeng, etc.).
- When the user **selects one user**, the client goes to the **chat page for that user** and sends `user_id` = that user's id (e.g. `webchat_user`, `system`, `Sabrina`, `AllenPeng`).
- **Same logic for every user:** per-user md memories, RAG memory, chat history, sandbox folder, knowledge_base. No special "System" or "Friend" flow; no plugin routing.
- **GET /api/config/users** returns all users with **id**, **name**, **type**, **who** (if present), **email**, **im**, **phone**, **permissions**. The client uses this list to show the user list and to send the chosen `user_id` with each message.

---

## Client changes (Companion app, WebChat, control UI)

1. **User list**  
   Load **GET /api/config/users** and show **all users** by **name** (e.g. WebChat, System, Sabrina, AllenPeng). Do not separate "System" and "Friend"; do not offer "combine with one user".

2. **Chat per user**  
   When the user selects a user (e.g. Sabrina), open the chat view for **that user** and send every message with **user_id** = that user's id (e.g. `Sabrina`). Same for WebChat and control UI: one conversation = one user_id.

3. **Remove**  
   - Any logic that sends `session_id=friend` or `conversation_type=friend` to route to the Friends plugin.  
   - Any "combine with one user" picker or flow; identity is chosen by **which chat** the user opens (each chat is one user).

4. **Optional**  
   Use **type** and **who** from the user object to show a subtitle or icon (e.g. companion-type users with **who** can show roles or language).

---

## Storage (per user)

| Data | Scope |
|------|--------|
| Chat history | Core chat DB, keyed by **user_id** (system_user_id). |
| RAG memory | Core memory, keyed by **user_id**. |
| AGENT_MEMORY / daily memory | Per-user paths: `agent_memory/{user_id}.md`, `daily_memory/{user_id}/YYYY-MM-DD.md`. |
| Sandbox | `base/{user_id}/` (and share folder for all). |
| Knowledge base | Per-user when supported; keyed by **user_id**. |

All users (normal and companion type) use the same storage model; no separate plugin store.

### File sandbox under homeclaw_root

When **homeclaw_root** is set (e.g. `D:/homeclaw` in core.yml):

- **Every user has its own folder**: `{homeclaw_root}/{user_id}/` (e.g. `D:/homeclaw/Sabrina/`, `D:/homeclaw/AllenPeng/`, `D:/homeclaw/webchat_user/`). The `user_id` is the sanitized id or name from user.yml. Requests set `system_user_id` so file tools resolve paths under that user’s folder.
- **All users can access the share folder**: `{homeclaw_root}/share/`. Paths like `share/...` in file tools (file_read, folder_list, etc.) resolve to this directory for any user. Use it for files that should be visible across users.

---

## check_permission and inbound

- For **IM** (companion app, WebChat, control UI): Core matches **user_id** to a user in user.yml by **id** or **name**. So when the client sends `user_id: Sabrina`, Core finds the user with id or name "Sabrina" and sets `system_user_id = Sabrina`. Companion-type users have no im/email/phone; they are matched only by id/name. There is no special case: if **user_id** does not match any user in user.yml (by id or name), the request is **permission denied**. So "companion" and "system" must be defined in user.yml if the client sends those ids.
- **Normal-type users** can still be matched by channel identity (im, email, phone) for channel requests.

---

## References

- **user.yml:** `type` (normal | companion), optional **who** dict. See config/user.yml.
- **Core:** No Friends plugin; no companion config routing. All inbound requests with a valid user_id go through the main flow (process_text_message) for that user.
- **System prompt:** When the current user is companion-type and has **who**, Core skips workspace Identity (IDENTITY.md) and injects a single **## Identity** block built from **who** (description, name, gender, roles, personalities, language, response_length). All other behavior (memory, chat, KB) is the same as for normal users.
