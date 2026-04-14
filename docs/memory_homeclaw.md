# HomeClaw memory system

This document describes **what** HomeClaw stores, **where** it is configured, and **in what order** memory is read and written at runtime. For Cognee-specific env mapping and database details, see [Memory and database](../docs_design/MemoryAndDatabase.md). For session/dual-memory design, see [SessionAndDualMemoryDesign.md](../docs_design/SessionAndDualMemoryDesign.md).

---

## 1. Overview: layers of memory

| Layer | Role | Typical storage |
|--------|------|-----------------|
| **Chat / sessions** | Conversation history, session IDs, runs | Relational DB (`database:` in `memory_kb.yml`) — SQLite by default |
| **RAG (conversation memory)** | Retrieve past turns relevant to the current query | **Cognee** (default), **Chroma** (in-house), **MemOS** (HTTP), or **composite** (e.g. Cognee + MemOS) |
| **Knowledge base (KB)** | User documents, URLs, notes; chunked retrieval | Same backend family as `knowledge_base.backend` (often `auto` = same as memory) |
| **Agent memory** | Curated long-term notes in `AGENT_MEMORY.md` (+ optional Chroma chunks for search) | Workspace files + optional vector collection |
| **Daily memory** | Dated notes (`memory/YYYY-MM-DD.md`) | Workspace under `workspace_dir` / `daily_memory_dir` |
| **Profile** | Learned facts about the user (name, preferences, …) | JSON under `profile.dir` |

These are **not** one database: RAG uses **vector + graph** stores (Cognee or in-house); chat history uses **relational**; agent/daily are **files** unless you use agent-memory search tools.

---

## 2. Where to configure

### 2.1 Main merge

- **`config/core.yml`** — Points at the merged memory/KB file and may duplicate a few keys.  
  Look for **`memory_kb_config_file`** (often `memory_kb.yml`). Paths are relative to the directory containing `core.yml` (usually `config/`).

### 2.2 Memory, KB, database, session (`config/memory_kb.yml`)

This is the single place for most **memory and KB** settings:

| Section | What it controls |
|---------|------------------|
| **`use_memory`** | Master switch for RAG add/search |
| **`memory_backend`** | `cognee` \| `chroma` \| `memos` \| `composite` — `composite.backends` lists backends |
| **`memory_check_before_add`** | Extra LLM call “should we store?” before add (default false) |
| **`memory_add_after_reply`** | If true (default), enqueue **after** the assistant reply so cognify/embed does not compete with the main LLM |
| **`memory_context_order`** | `relevance` (default) or `newest_first` for RAG snippets in the prompt |
| **`memory_summarization`** | Optional batch summarization of old RAG memories (TTL, schedule) |
| **`session.*`** | DM scoping, pruning, idle session, API |
| **`profile.*`** | Per-user profile JSON |
| **`use_agent_memory_file`**, **`agent_memory_path`**, **`agent_memory_max_chars`**, **`use_agent_memory_search`**, **`agent_memory_bootstrap_*`**, **`use_daily_memory`**, **`daily_memory_dir`** | Agent + daily file memory |
| **`knowledge_base.*`** | KB enable, backend, chunking, retrieval threshold, folder sync |
| **`database.*`** | **Core** relational DB (chats, sessions, runs) — always used for Core history |
| **`vectorDB`** / **`graphDB`** | Used only when **`memory_backend: chroma`** (in-house RAG). **Not** used for Cognee memory |
| **`cognee:`** | When **`memory_backend: cognee`** (or composite includes Cognee), relational/vector/graph/LLM/embedding for Cognee |

### 2.3 LLM / embedding servers (`config/llm.yml`)

- **`embedding_llm`**, **`embedding_host`**, **`embedding_port`** — Used by Core (and auto-filled into Cognee when `cognee.embedding` is empty) so **RAG** and **KB** embedding calls hit your local or cloud OpenAI-compatible endpoint.

### 2.4 Friend presets (`config/friend_presets.yml` — or per-friend in `user.yml`)

- **`memory_sources`** — Restricts which layers are injected for that friend: e.g. `cognee`, `agent_memory`, `daily_memory`, `md` (agent + daily). See `config/friend_presets.yml` comments.

### 2.5 Tools / long output (`config/skills_and_plugins.yml`)

- Unrelated to RAG storage, but **`tools.long_document_output`** affects how **daily-brief / web_search** results are presented (Markdown vs VMPrint preview). See [Response output policy](response-output-policy.md).

---

## 3. RAG backends (short)

| `memory_backend` | Configure via |
|------------------|----------------|
| **cognee** | `cognee:` in merged config + optional Cognee `.env`. `vectorDB`/`graphDB` in `core.yml` **do not** apply. |
| **chroma** | `database:`, `vectorDB:`, `graphDB:` in merged config. |
| **memos** | MemOS HTTP URL and related keys (see `memory/` initialization). |
| **composite** | `composite.backends: [cognee, memos]` (example) — **add** goes to both; **search** merges. |

**Scope:** RAG adds/searches are scoped by **system user id** and **friend_id** (dataset name), so each user (and friend persona) stays isolated.

**Reset:** `GET /memory/reset` (RAG), `GET /knowledge_base/reset` (KB) — see comments in `memory_kb.yml`.

---

## 4. Runtime sequence

### 4.1 One user message → prompt assembly (read path)

Order is built in **`answer_from_memory`** (`core/llm_loop.py`) as **`system_parts`** (then merged into the system message). Approximate **order of injection**:

1. **Workspace bootstrap** — `IDENTITY.md` / `AGENTS.md` / `TOOLS.md` (if `use_workspace_bootstrap`), unless Companion “who” replaces identity.
2. **Companion / friend identity** — `who`, friend `identity` file, or default assistant line.
3. **Agent memory directive + bootstrap** (if enabled and preset allows) — `use_agent_memory_search` true: **directive** + capped **AGENT_MEMORY** + **daily** bootstrap; tools `agent_memory_search` / `agent_memory_get` / `append_*` for more detail.
4. **Legacy path** if `use_agent_memory_search` is false — **bulk** `AGENT_MEMORY.md` (capped) and optional **daily** block.
5. **Intent router** (if enabled) — runs early to classify query (affects **skills** / **tools** filtering).
6. **Skills** listing (optional RAG on skills).
7. **RAG** (Cognee/composite/etc.) — `_fetch_relevant_memories` → formatted as numbered lines; **`memory_context_order`** may sort by newest.
8. **Knowledge base** — `kb.search(...)` for top chunks; **optional** `retrieval_min_score` filter.
9. **Profile** — “About the user” when profile enabled and friend is default HomeClaw (see code).
10. **Chat response template** — `RESPONSE_TEMPLATE` or prompt manager `chat/response` with **`{context}`** = RAG text (or “None.”).
11. **Response language / format** hints.
12. **Plugins** (if unified orchestrator).
13. **Tools** definitions (OpenAI tool list).
14. **System context** (date/time/location) — often **appended late** for KV-cache stability — see [System context, date/time, location](../docs_design/SystemContextDateTimeAndLocation.md).

**Precedence note:** Agent memory directives state that **curated agent memory** overrides **RAG** when they conflict.

**Friend preset:** If `memory_sources` omits `cognee`, RAG injection is skipped; if it omits `agent_memory` / `md`, agent/daily bootstrap is reduced accordingly.

### 4.2 After the assistant reply (write path)

1. **`memory_add_after_reply`** (default **true**): After the model returns, Core puts the request on **`memory_queue`** (async queue).
2. **`process_memory_queue`** (background loop in `core/core.py`, ~2s sleep between items): For each item, if **`memory_check_before_add`** is true and the model is “small” enough, Core may ask a **yes/no** LLM whether to store; otherwise it calls **`mem_instance.add(...)`** with the user message or full **`memory_turn_data`** (user + assistant + tool messages when provided).
3. **MemOS vs Cognee:** When `memory_turn_data` is present, **`messages_for_memory`** can include the full turn; Cognee path may still use **user-only** text depending on adapter (see `process_memory_queue` comments).

### 4.3 Other background jobs (not every message)

- **KB folder sync** — If `knowledge_base.folder_sync.enabled` and `schedule` set, periodic scan of user `knowledge/` folders.
- **RAG memory summarization** — If `memory_summarization.enabled`, scheduler batches old memories per `schedule` / `next_run`.

---

## 5. Quick reference: keys that affect “order” in the prompt

| Key | Effect |
|-----|--------|
| `memory_context_order` | RAG snippets: relevance vs newest first |
| `use_agent_memory_search` | Bootstrap + tools vs legacy bulk inject |
| `memory_add_after_reply` | Store **after** reply (default) vs before |
| Friend `memory_sources` | Which of cognee / agent / daily is active |

---

## 6. Related documentation

- [Memory and database](../docs_design/MemoryAndDatabase.md) — Cognee vs Chroma, `vectorDB`/`graphDB` rules, relational DB
- [User profile](../docs_design/UserProfileDesign.md) — profile store
- [Multi-user support](../docs_design/MultiUserSupport.md) — system user id and scoping
- [RAG memory summarization design](../docs_design/RAGMemorySummarizationDesign.md) — summarization job
- [Response output policy](response-output-policy.md) — Markdown vs VMPrint for long tool output

---

*Generated for HomeClaw Core; behavior follows `core/llm_loop.py` and `core/core.py` as of the repo version you are reading.*
