# Session (Built-in vs Plugin) and Dual Memory (RAG + AGENT_MEMORY.md)

This doc analyzes (1) whether session-related features should live in **built-in tools** or a **plugin**, and (2) how **RAG memory** and **plain markdown memory (AGENT_MEMORY.md)** can coexist and work together.

---

## Part 1: Session — Built-in vs Plugin

### What “session” covers

- **Session identity:** Which conversation is this request part of? (Today: `app_id` + `user_id` → `session_id`;)
- **Session store:** List of sessions, metadata (updatedAt, channel, etc.), optional token counts.
- **Session lifecycle:** When to start a “new” session (daily reset, idle reset, explicit `/new`/`/reset`).
- **Session tools:** `sessions_list`, `sessions_history`, `sessions_send`, `sessions_spawn` (already built-in).
- **Secure multi-user:** Isolate DM context per channel+sender so users don’t see each other’s context (e.g. `dmScope: per-channel-peer`).

### dmScope and identityLinks

Use **session.dm_scope** and **session.identity_links** in `config/core.yml` to control how direct messages are grouped. 

- **main (default):** All DMs share one session per app for continuity (`<app_id>:main`).
- **per-peer:** Isolate by sender id across channels; same person on Telegram and Discord gets one session if **identity_links** maps both to the same canonical id.
- **per-channel-peer:** Isolate by channel + sender (recommended for multi-user inboxes). Same person on two channels gets two sessions.
- **per-account-channel-peer:** Isolate by account + channel + sender (for multi-account inboxes).

**identity_links** maps a canonical id to a list of provider-prefixed peer ids so the same person shares a DM session across channels when using per-peer. Example: `identity_links: { "alice": ["telegram:123", "discord:456"] }`.

Session key format: `main` → `<app>:main`; per-peer → `<app>:dm:<peer_id>`; per-channel-peer → `<app>:<channel>:dm:<peer_id>`; per-account-channel-peer → `<app>:<channel>:<account>:dm:<peer_id>`. Core passes `channel_name` (and optional `account_id` in request_metadata) into `get_session_id` so the derived key is used for chat history and storage.

### Why session should be **built-in** (Core), not a plugin

1. **Session resolution is core to every request.**  
   Before the agent can do anything, Core must decide: “Which session is this?” That determines which chat history to load, which RAG/memory scope to use, and which session_id to pass to tools. That resolution depends on Core’s own store (DB, in-memory map) and config (e.g. future dmScope). A plugin cannot own this without Core delegating “give me the session for this request” to the plugin on every message — which would make Core dependent on the plugin for basic operation.

2. **Session tools already depend on Core.**  
   `sessions_list`, `sessions_send`, `sessions_spawn`, and history-style tools call Core APIs (`get_sessions`, `send_message_to_session`, `run_spawn`, chat DB). The **source of truth** for sessions and chat is Core (SQLite). Moving “session management” to a plugin would either (a) duplicate state (plugin has its own session store → sync and consistency issues) or (b) plugin just being a proxy to Core (then the logic is still in Core).

3. **Plugins are for optional capabilities; session is scaffolding.**  
   Per ToolsSkillsPlugins.md: tools = common building blocks; plugins = dedicated features (Weather, News, browser, etc.). Session is not a “feature” the user turns on for one kind of task — it’s the mechanism that defines *which conversation* the agent is in. That fits “built-in” not “plugin.”

4. **Where a plugin *does* fit:**  
   - **Session UI:** A Control UI or dashboard plugin can **consume** Core’s session API (`GET /api/sessions` or similar) to show session list, token counts, “reset session,” export transcript. The **data and rules** stay in Core; the plugin is view/UI only.  
   - **Optional sync/export:** A plugin could export Core’s sessions/transcripts to JSON or another format for interoperability. Again, Core remains source of truth.

**Do you need a new Node.js plugin in system_plugins for Session UI or sync?** No. (1) **Extend the existing homeclaw-browser plugin:** it already provides Control UI and dashboard; add a Sessions page or tab there that calls `GET /api/sessions` and shows list, reset, export. (2) Or add a minimal session list to Core's GET /ui (Core serves a simple HTML list from its own `get_sessions()`). A **dedicated** Node.js plugin is only useful if you want a standalone Session UI app separate from the browser plugin; it is optional.

### Recommendation

- **Implement session-related behavior (store, keys, lifecycle, secure DM) and session tools in Core as built-in.**  
  That includes: session key model (e.g. extend to support channel + peer for multi-user), session list/store API, optional daily/idle reset and reset triggers, and any config for `dmScope`-style isolation. Session tools stay in the tool registry and call Core.
- **Optionally add a session API** (e.g. `GET /api/sessions`) so that **plugins** (e.g. Control UI) can display sessions without reading DB/files.
- **Do not** move session *management* (which session, where history lives, lifecycle) into a plugin; keep that in Core and treat a plugin as a **consumer** of session data for UI or export.

---

## Part 2: Dual Memory — RAG vs AGENT_MEMORY.md

### Two memory layers (proposed)

| Layer | What it is | Where it lives | How it’s used |
|-------|------------|----------------|---------------|
| **RAG memory** | Vector store (Chroma); semantic search over ingested content. | Chroma + embeddings; content from conversation (memory_queue) and optionally tools. | On each request: `_fetch_relevant_memories(query, …)` → top‑k snippets → inject “Here is the given context: …” into system prompt. |
| **AGENT_MEMORY.md** | Single plain Markdown file (curated, long-term). Optional: `memory/YYYY-MM-DD.md` for daily notes. | e.g. `config/workspace/AGENT_MEMORY.md` (or a dedicated `memory/` dir under workspace). | On each request: read file from disk → inject as “## Agent memory (curated)” (or similar) into system prompt. Human- and model-editable. |

Naming: we use **AGENT_MEMORY.md** (not MEMORY.md) to avoid confusion with the `memory/` RAG/Chroma subsystem and to make it clear it’s the agent’s curated long-term memory file.

### Which one do we “follow”?

We **don’t choose one** — we **combine** both and give each a clear **role** so the model knows how to use them.

- **RAG:** “Recalled context” — things that were said or ingested that are semantically relevant to this query. Good for scale, no manual editing, fuzzy recall.
- **AGENT_MEMORY.md:** “Canonical long-term memory” — explicit facts, preferences, and decisions the user or agent have chosen to write down. Good for “this is definitely true,” human-editable, versionable (e.g. Git).

So we **follow both**: both are injected into the prompt. If they ever conflict (e.g. RAG says “user likes X,” AGENT_MEMORY.md says “user prefers Y”), we **don’t resolve it in code** — we inject both and tell the model in the system prompt that **AGENT_MEMORY.md is the authoritative long-term memory** and RAG is **additional recalled context**; in case of conflict, prefer AGENT_MEMORY.md. That keeps logic simple and lets the model handle edge cases.

### How they work together

**At request time (read path):**

1. **Workspace** (Identity, Agents, Tools) — as today.
2. **AGENT_MEMORY.md** — if the file exists and config enables it, read it and append a block, e.g. `## Agent memory (curated)\n\n<content>`.
3. **RAG** — `_fetch_relevant_memories(query, …)` → “Here is the given context: …” as today.
4. **Chat** — recent turns + current message.

Order in system prompt could be: **Workspace → AGENT_MEMORY.md → RAG block → guidelines**. So the model sees: identity/capabilities first, then curated memory, then semantic recall, then how to respond.

**Writing (write path):**

- **RAG:** Unchanged. Content is added via existing flow (e.g. `memory_queue` from conversation, or tools that call `add_user_input_to_memory` / equivalent). No change.
- **AGENT_MEMORY.md:** New. We need a way for the agent (or user) to write to it:
  - **Option A — Tool:** e.g. `append_agent_memory(content)` or `memory_write(target="AGENT_MEMORY.md", content="...")` that appends (or updates a section of) the file. The LLM can then “remember this” by calling the tool.
  - **Option B — Pre-compaction / periodic flush (optional):** When the session is about to be trimmed or context is long, run a silent or guided turn: “Write any lasting notes to AGENT_MEMORY.md” and let the model respond with content; Core (or a tool) appends it to the file. Optional and can be added later.

So they work together by **both being read** into the prompt with clear roles, and **both being writable**: RAG by existing ingestion, AGENT_MEMORY by a new tool (and optionally flush).

### Summary: which to follow, how they work together

- **Which to follow:** Both. We inject both; we define in the system prompt that AGENT_MEMORY.md is **authoritative long-term**, RAG is **recalled context**; on conflict, prefer AGENT_MEMORY.md.
- **How they work together:** (1) Read: workspace → AGENT_MEMORY.md → RAG → chat. (2) Write: RAG via current pipeline; AGENT_MEMORY.md via a new tool (and optionally a flush step). No single “winner” — they complement each other (curated vs semantic, editable vs automatic).

---

## Part 3: Implemented (config and behavior)

- **Session:** Implement session key/lifecycle and secure-DM options in Core (built-in); add `GET /api/sessions` (or equivalent) for plugin UIs; document behavior in a short “Session” section in the main design.
- **AGENT_MEMORY.md:** Config (e.g. `use_agent_memory_file: true`, `agent_memory_path: config/workspace/AGENT_MEMORY.md`). In `answer_from_memory()`, after workspace and before RAG, read the file (if present) and append “## Agent memory (curated)” to system_parts. Add a tool (e.g. `append_agent_memory` or `memory_write` for that file) so the model can write to it. In the system prompt, add one sentence: “AGENT_MEMORY.md is the canonical long-term memory; RAG results are additional recalled context; prefer AGENT_MEMORY when they conflict.”
- **Compaction:** Config: `compaction.enabled`, `compaction.reserve_tokens`, `compaction.max_messages_before_compact`, `compaction.compact_tool_results`. When enabled, messages are trimmed to the last `max_messages_before_compact`. When `compact_tool_results` is true, tool results over 4000 chars are truncated in the tool loop.
- **Skills/plugins selection:** Config: `skills_top_n_candidates` (10), `skills_max_in_prompt` (5), `plugins_top_n_candidates` (10), `plugins_max_in_prompt` (5). Top N candidates → threshold → cap to max_in_prompt. See `config/core.yml`.

- **Optional (future):** Pre-compaction or periodic “flush to AGENT_MEMORY.md” step; and/or optional `memory/YYYY-MM-DD.md` for daily notes (read today + yesterday) (optional).

**Comparison with OpenClaw:** OpenClaw uses short-term = `memory/YYYY-mm-dd.md` (load yesterday + today on start) and long-term = `MEMORY.md`. HomeClaw does **not** use that split: we have **no date-based markdown files** for short-term. Instead, short-term = recent **chat history** (SQLite) + **RAG** (vector store). Long-term = single **AGENT_MEMORY.md**. Same idea of curated long-term in one file; short-term is RAG + chat, not daily .md files.

This keeps session in Core, uses a plugin only for session UI/export, and makes RAG and AGENT_MEMORY.md work together with clear roles and a simple conflict rule.

For a concise summary of **when and how** AGENT_MEMORY.md vs daily memory (`memory/YYYY-MM-DD.md`) are used, and how to cap AGENT_MEMORY to avoid filling the context window, see **MemoryFilesUsage.md**.
