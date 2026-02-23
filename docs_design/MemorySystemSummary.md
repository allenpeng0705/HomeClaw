# Memory system summary (agent, daily, RAG memory, knowledge base)

This doc summarizes HomeClaw’s memory systems and how they are kept **stable and robust** so Core never crashes due to memory code.

---

## 1. Four distinct memory/context systems

| System | What it is | Where it lives | Config / backend |
|--------|------------|----------------|------------------|
| **Agent memory** | Long-term curated facts, preferences, decisions (markdown). | Single file: `AGENT_MEMORY.md` (default `config/workspace/AGENT_MEMORY.md`, or `agent_memory_path`). | `use_agent_memory_file`, `use_agent_memory_search`, `agent_memory_path`, etc. |
| **Daily memory** | Short-term notes, yesterday + today (markdown). | One file per day: `memory/YYYY-MM-DD.md` under workspace. | `use_daily_memory`, `daily_memory_dir` |
| **RAG memory** | **Conversation-derived** semantic memory: past user/assistant content that was ingested and searched by relevance. | Vector store (Chroma when `memory_backend: chroma`, or Cognee when `memory_backend: cognee`). Backed by `mem_instance` (MemoryBase). | `memory_backend`, `vectorDB`, `database` (when chroma). Written via `memory_queue` → `mem_instance.add()`; searched by `_fetch_relevant_memories()` → injected as “RelevantMemory” / context. |
| **Knowledge base** | **User’s saved documents, web clips, URLs, manual notes** — not conversation stream. | Separate store: Chroma collection (e.g. `homeclaw_kb`) or Cognee KB. Backed by `knowledge_base` (KnowledgeBase). | `knowledge_base` (enabled, backend, collection_name, …). Written via `knowledge_base_add` and file-upload auto-add; searched by `kb.search()` → injected as “## Knowledge base (from your saved documents/web/notes)”. |

**Agent** and **daily** = curated .md files. **RAG memory** = conversation recall (semantic search over what was said/ingested). **Knowledge base** = document/saved-content store. They are different; agent memory is treated as **authoritative** over both RAG memory and Knowledge base when the system prompt mentions conflict (see §5).

---

## 2. How agent and daily memory are used

### Reading (recall)

- **When `use_agent_memory_search: true` (default):** A **capped bootstrap** of AGENT_MEMORY + daily is injected (OpenClaw-style); the model can also use **agent_memory_search** and **agent_memory_get** for more. Indexing runs at startup and after each append (re-sync).
- **When `use_agent_memory_search: false` (legacy):** The last `agent_memory_max_chars` (default 5k) of AGENT_MEMORY.md is injected as “## Agent memory (curated)”. Yesterday + today daily files are injected as “## Recent (daily memory)”.

### Writing

- **Primary path (default):** When **memory_flush_primary** is true (default under `compaction`), memory is written only in a **dedicated flush turn** before context compaction: one extra turn with the prompt “Store durable memories now…” where the model calls **append_agent_memory** and **append_daily_memory**. The main turn is not asked to call append_* (avoids duplicate writes).
- **Legacy path:** When **memory_flush_primary** is false, the main prompt tells the model to “when useful, write to memory” using append_agent_memory / append_daily_memory during the normal turn.

Tools: **append_agent_memory**, **append_daily_memory**, **agent_memory_search**, **agent_memory_get**. See `tools/builtin.py` and `config/core.yml` (compaction.memory_flush_primary, memory_flush_prompt).

---

## 3. RAG memory vs Knowledge base (both separate from .md)

- **RAG memory** = conversation-based recall. Content comes from the **conversation stream** (e.g. `memory_queue` → `mem_instance.add`). It is searched by `_fetch_relevant_memories(query, …)` and injected as “RelevantMemory” / context in the prompt. Backend: Chroma (when `memory_backend: chroma`) or Cognee (when `memory_backend: cognee`). Reset: `/memory/reset` clears this plus agent/daily .md when enabled.
- **Knowledge base** = user’s **saved documents, web, URLs, manual** content. Content is added only via the **knowledge_base_add** tool (or file-upload auto-add). It is searched by `kb.search(query, …)` and injected as “## Knowledge base (from your saved documents/web/notes)”. Backend: `knowledge_base.backend` (auto / cognee / chroma), often a separate collection (e.g. `homeclaw_kb`). Reset: `/knowledge_base/reset` (does not clear RAG memory or .md files).

So: **RAG memory** and **Knowledge base** are different stores and different use cases (conversation recall vs saved documents). Neither uses AGENT_MEMORY.md or daily .md files.

---

## 4. When is memory written? (.md vs RAG memory vs Knowledge base)

| Target | When it is written | How |
|--------|--------------------|-----|
| **AGENT_MEMORY.md** | When the model or user calls **append_agent_memory**, or during the **memory flush turn** (before compaction when `memory_flush_primary` is true). | Tool writes to file; after append, agent memory index is re-synced so search sees new content. |
| **Daily .md** (`memory/YYYY-MM-DD.md`) | When the model or user calls **append_daily_memory**, or during the **memory flush turn**. | Tool appends to today’s file; index re-synced after append. |
| **RAG memory** (conversation recall) | When **use_memory** is true and the request is put on the memory queue: Core calls **mem_instance.add(**user message, …**)** so that past conversation content is embedded and stored for later semantic search. | `memory_queue` → `process_memory_queue()` → `mem_instance.add(...)`. Backend is Chroma or Cognee (vector store for conversation memories). |
| **Knowledge base** | (1) When the model calls **knowledge_base_add** (e.g. user says “save this to my knowledge base”). (2) **Auto-add on file upload:** when the user sends only file(s) (no or minimal text) and `file_understanding.add_to_kb_max_chars` is set, Core can add the extracted document text to the KB. | `kb.add(...)`. Separate from RAG memory; no .md files. |

So: **.md** is written only via append_* tools (and the flush turn). **RAG memory** is written from the conversation stream (mem_instance.add). **Knowledge base** is written via knowledge_base_add and optionally file-upload auto-add. The three write paths are independent.

---

## 5. Duplicate information (md vs RAG memory vs Knowledge base): what we do

We can have **three** kinds of recalled context in the prompt: (1) agent/daily .md bootstrap, (2) **RAG memory** (conversation recall from mem_instance.search), (3) **Knowledge base** (saved documents from kb.search). The same or similar information can appear in more than one (e.g. “User prefers dark mode” in AGENT_MEMORY, in a past conversation in RAG memory, and in a saved note in the KB).

**Current policy: we do not remove duplication.**

- We **use all of them** when applicable: the bootstrap block (agent + daily), the RAG memory context (“RelevantMemory” / given context), and the “## Knowledge base (from your saved documents/web/notes)” block are each injected when enabled and when there are results. If the same fact appears in two or three places, the model may see it more than once.
- We **set priority**: the system prompt states that **“This curated agent memory is authoritative when it conflicts with RAG context below.”** So when agent/daily memory and **either** RAG memory **or** Knowledge base mention the same fact, the model is instructed to prefer agent/daily memory. That avoids wrong answers from conflicting sources; duplication is a matter of token use and clarity, not correctness.

**Could we remove duplication (e.g. filter RAG or KB chunks that are too similar to agent memory)?**

- **Possible but not implemented.** We could, before injecting RAG or KB results, drop chunks above a similarity threshold to the current agent/daily bootstrap. That would reduce tokens but adds complexity and risk of over-filtering. For now we **do not** auto-dedup; we rely on **authoritative** wording and accept that all three may be present when applicable.

---

## 6. When and how: RAG memory and Knowledge base (logic review)

### RAG memory (conversation recall)

| | Logic | Code / config |
|--|--------|----------------|
| **Gate** | Used only when **use_memory** is true (`core_metadata.use_memory`). | `Util().has_memory()` → `core_metadata.use_memory`. |
| **Write** | Each incoming request is put on **memory_queue** (if use_memory). A background task **process_memory_queue** consumes it and calls **mem_instance.add(human_message, …)**. When **memory_check_before_add** is true and (`main_llm_size <= 8` or (`main_llm_size <= 14` and has_gpu)), an extra LLM call (“should this be added to memory?”) runs first; only if the answer contains “yes” is it added. **Default** (memory_check_before_add: false): every message is added; retrieval (top-k, score) filters at read time. | `core.py`: queue put, process_memory_queue; config: **memory_check_before_add** (default false). |
| **Read (automatic)** | When building the system prompt in **answer_from_memory**, if **use_memory** is true we call **_fetch_relevant_memories(query, …)** (limit 10). The result is formatted as “1: … 2: …” into **context_val** and injected via the response prompt template (“Here is the given context: {context}” or prompt_manager “chat”/“response”). So RAG memories appear in the **system** message. | `core.py`: 4017–4030, 4079/4086 (context_val in prompt). |
| **Read (tools)** | The model can call **memory_search**(query, limit) and **memory_get**(memory_id) to search or fetch by id. These use **core.search_memory** and **core.get_memory_by_id** (same mem_instance). | `tools/builtin.py`: _memory_search_executor, _memory_get_executor. |

**Quirk:** RAG memory **read** (inject + tools) and **write** (queue) are both gated by **use_memory**. The “should we add?” LLM check runs only when **memory_check_before_add** is true and the model is small/local; by default we store every message and rely on retrieval quality.

### Refining RAG write (avoiding garbage without an extra LLM call)

We want to avoid filling RAG memory with low-value messages (greetings, one-off questions) so that search stays useful. Options:

| Approach | Pros | Cons |
|----------|------|------|
| **Store everything (default)** | No extra latency or cost; retrieval (top-k, similarity) naturally surfaces relevant chunks; junk is often not in the top results. | Store grows; very noisy corpora can dilute relevance. |
| **memory_check_before_add: true** | Reduces what gets stored by asking the LLM “should we store?” for small/local models. | One extra LLM call per user message; small models may be inconsistent; adds latency. |
| **Heuristic filter (future)** | No LLM: e.g. skip messages shorter than N chars, or that are only “?” or greetings. Fast and predictable. | Crude; may drop useful short messages or keep long junk. |
| **Tool-based (future)** | Main turn decides: model or pipeline calls e.g. “add_to_memory(content)” only for facts worth storing. Single turn, no separate “check” call. | Requires tool or structured output and discipline in prompts. |

**Current choice:** Default is **store everything** (**memory_check_before_add: false**). Set **memory_check_before_add: true** in config only if you explicitly want the extra LLM gate for small/local models. Heuristic or tool-based refinements can be added later without changing this flag.

### Knowledge base (saved documents)

| | Logic | Code / config |
|--|--------|----------------|
| **Gate** | KB is **created** only when **knowledge_base.enabled** is true. **Injection** into the prompt happens only when **use_memory** is true (same block as RAG memory). So if use_memory is false, KB is not injected even if KB is enabled. | `core.py`: 723–724 (_create_knowledge_base), 4017 + 4032–4051 (inject when use_memory). |
| **Write** | (1) **knowledge_base_add** tool: model (or user) calls it with content, source_type, source_id. (2) **File-upload auto-add:** when the user sends **only** file(s) (no or negligible text), and **file_understanding.add_to_kb_max_chars** > 0, and KB is enabled and user_id is set, Core extracts document text and calls **kb.add(user_id, content, source_type="document", source_id=path, …)** for each doc under the size limit. | `core.py`: 2909–2938 (auto-add). `tools/builtin.py`: _knowledge_base_add_executor. |
| **Read (automatic)** | When **use_memory** is true and **kb** is not None and (user_id or user_name), we call **kb.search(user_id, query, limit=5)**. Results are filtered by **knowledge_base.retrieval_min_score** if set. Top chunks are injected as “## Knowledge base (from your saved documents/web/notes)” into **system_parts**. | `core.py`: 4032–4055. |
| **Read (tools)** | The model can call **knowledge_base_search**(query, limit) to search the KB. | `tools/builtin.py`: _knowledge_base_search_executor. |

**Quirk:** KB **injection** is tied to **use_memory**. So to get KB results in the prompt you must have use_memory: true. If you want KB without RAG memory, that would require a code change (e.g. a separate gate for KB injection).

### Summary: both correct as implemented

- **RAG memory:** Write = queue → process_memory_queue → mem_instance.add. By default every message is added; when memory_check_before_add is true and model is small/local, an LLM “should we add?” check runs first. Read = _fetch_relevant_memories when use_memory, plus memory_search / memory_get tools.
- **Knowledge base:** Write = knowledge_base_add tool + file-upload auto-add when conditions met. Read = kb.search when use_memory and kb exists, plus knowledge_base_search tool.
- Both are independent of agent/daily .md. The only coupling is that **prompt injection** for both RAG and KB is inside the same **if use_memory** block.

---

## 7. Stability and robustness (never break Core)

All memory code is written so that **failures are contained** and **Core never crashes** due to memory:

| Layer | Guarantees |
|-------|------------|
| **base/workspace.py** | `get_workspace_dir`, `get_agent_memory_file_path`, `get_daily_memory_dir` never raise; on error return safe defaults. `load_workspace`, `load_agent_memory_file`, `load_daily_memory_for_dates`, `append_daily_memory`, `ensure_*`, `clear_*` catch exceptions and return empty/false/count. |
| **base/agent_memory_index.py** | `chunk_text_with_lines`, `get_agent_memory_files_to_index`, `sync_agent_memory_to_vector_store` never raise; sync returns 0 on failure and logs. |
| **tools/builtin.py** | `_append_agent_memory_executor`, `_append_daily_memory_executor`, `_agent_memory_search_executor`, `_agent_memory_get_executor` wrap all work in try/except and return JSON or error strings; no exception propagates to the tool layer. |
| **core/core.py** | Agent memory directive and legacy injection blocks are inside try/except; on error we log and skip that block. Memory flush turn is fully wrapped in try/except/finally; compaction and main turn always continue. `/memory/reset` clears agent/daily in try/except and always returns a JSON response. `re_sync_agent_memory`, `search_agent_memory`, `get_agent_memory_file` never raise (return 0, [], None). Startup sync of agent memory to vector store is in try/except; failure is logged, Core continues. |

So: **memory system bugs or I/O errors result in logged failures and safe fallbacks (empty content, no write, 0 chunks), never in Core crashing.**

---

## 8. Config quick reference

```yaml
# config/core.yml (relevant keys)

use_memory: true
memory_check_before_add: false  # default: store every message; set true to gate with LLM “should we add?” for small/local models

use_agent_memory_file: true
use_agent_memory_search: true   # default: retrieval-first, no bulk inject
agent_memory_path: ""           # default: workspace_dir/AGENT_MEMORY.md
agent_memory_max_chars: 5000
agent_memory_vector_collection: homeclaw_agent_memory

use_daily_memory: true
daily_memory_dir: ""            # default: workspace_dir/memory

workspace_dir: config/workspace

compaction:
  enabled: false
  max_messages_before_compact: 30
  memory_flush_primary: true    # default: single flag for “flush is the only writer”
  memory_flush_prompt: "..."    # optional override for flush turn
```

**RAG memory** (conversation recall) uses `memory_backend`, `vectorDB` (when chroma), and `mem_instance`. **Knowledge base** (saved documents) uses the `knowledge_base` block and is separate.

---

## 9. See also

- **MemoryFilesUsage.md** — Format and usage of AGENT_MEMORY.md and daily files; when they are loaded; dedup and caps.
- **SessionAndDualMemoryDesign.md** — Session vs plugin; dual memory (RAG memory + AGENT_MEMORY); Knowledge base is a separate store.
- **OpenClawMemoryReadWrite.md** — How OpenClaw does memory read/write and how HomeClaw’s flush aligns with it.
- **RAGMemorySummarizationDesign.md** — Design for summarizing groups of RAG memories into long-term memory and handling originals (delete vs keep with TTL).
