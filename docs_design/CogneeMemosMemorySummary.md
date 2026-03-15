# Cognee and MemOS: How They Work Together and What They Store

## Overview

HomeClaw’s **semantic / RAG memory** (recall of past user inputs) is handled by `core.mem_instance`. It can be:

- **Cognee only** (`memory_backend: cognee`) — default
- **Memos only** (`memory_backend: memos`)
- **Both together** (`memory_backend: composite`) — add to both, search over merged results

**Chat history** (exact user/assistant turns) is separate: it is stored in **chatDB** (relational DB), not in Cognee or Memos.

---

## 1. When is memory written?

- **Who:** A background task in Core: `process_memory_queue()` in `core/core.py`.
- **When:** After each user message is handled, the request is put on `memory_queue`; the task dequeues it and, if memory is enabled, calls `mem_instance.add(...)`.
- **What is passed to `add()`:** When the turn has completed and `memory_add_after_reply` is true, the request is enqueued with **`memory_turn_data`** (user message, assistant message, and tool messages). The queue consumer then passes either:
  - A **list of messages** (user + assistant + tool, each with `role`, `content`, and for tools `toolName`) when `memory_turn_data` is present, or
  - The **user message** string only when it is not (e.g. no reply yet or legacy path).
- **ChatDB:** The formatted assistant reply is always stored in **chatDB** (exact conversation turns).

So: **Cognee and Memos can receive the full turn** (user + assistant + tool) when available, for better context and knowledge extraction.

---

## 2. Standalone backends

### Cognee (`memory_backend: cognee`)

- **Stored:** When `add(data, ...)` receives a **list** of messages (full turn), Cognee builds a single string with role-prefixed segments and stores that: **User: … Assistant: … Tool (name): …** (assistant truncated to 4000 chars, each tool to 2000). When `data` is a string, that string is stored as-is (user-only path).
- **Why full turn:** Storing both user and assistant (and optionally tool) gives cognify the **conversational context** (e.g. assistant asked “What’s your favorite color?” → user said “Blue” → the graph can map Blue to “favorite color” correctly). User-only storage can fragment entities and lose provenance.
- **How:**
  1. **Add:** The (possibly combined) text is added to a Cognee **dataset** (per user/agent: `user_id` + `agent_id`).
  2. **Cognify:** Cognee runs an LLM pipeline (cognify) on that dataset to extract **entities and relationships** and fill:
     - A **graph** (e.g. Kuzu): entities and relations.
     - **Vector** store (e.g. Chroma): embedded chunks for semantic search.
- **Config:** `memory_kb.yml` → `cognee` (relational, vector, graph, llm, embedding). When empty, Core fills LLM/embedding from `main_llm` and embedding settings.
- **Scope:** One dataset per `(user_id, agent_id)` (e.g. per user and friend/agent).

### Memos (`memory_backend: memos`)

- **Stored:** When the full turn is available, **user + assistant + tool** messages are sent. Otherwise only the user message.
- **How:**  
  `memory/memos_adapter.py` calls MemOS `POST /memory/add` with:
  - `messages: [{ "role": "user", "content": "..." }, { "role": "assistant", "content": "..." }, { "role": "tool", "content": "...", "toolName": "..." }, ...]` when `data` is a list, or `[{ "role": "user", "content": data }]` when `data` is a string.
  - `sessionKey` = user_id (or "default"), `agentId` = derived from user_id + agent_id.
- **Config:** `memory_kb.yml` → `memos` (url, timeout, optional auto_start, viewer_port).
- **Scope:** MemOS manages its own storage and retrieval (vector/semantic) per session/agent.

---

## 3. Composite mode (`memory_backend: composite`)

- **Config:** `memory_kb.yml`:
  - `memory_backend: composite`
  - `composite.backends: [cognee, memos]` (order optional; both need their config).
  - `composite.search_merge: union_by_score` (default) or `primary_only`.

**Add (write):**

- One call to `mem_instance.add(human_message, ...)` is executed by `CompositeMemory`.
- Composite **fans out** to **every** backend in `backends`:
  - Cognee gets the user message → add + cognify (graph + vector).
  - Memos gets the same user message → POST /memory/add.
- If one backend fails, the other still runs; failures are logged and do not block the rest.

**Search (read):**

- One call to `mem_instance.search(query, user_id=..., agent_id=..., limit=...)` (e.g. from `_fetch_relevant_memories`) is executed by Composite.
- **If `search_merge` is not `primary_only`:**
  - Composite calls **search on all backends** in parallel.
  - Results are **merged**, **deduped by content** (same text counted once), and **sorted by score** (desc).
  - Top `limit` results are returned.
- **If `search_merge: primary_only`:**
  - Only the **first** backend in `backends` is searched (e.g. Cognee only if it is first).

So: **same user message is stored in both Cognee and Memos**; at read time you get a **single merged list** of relevant memories (or only from the first backend if `primary_only`).

---

## 4. What each system stores (summary)

| System            | User message      | AI response / tools | Where / how                                                                 |
|-------------------|-------------------|---------------------|-----------------------------------------------------------------------------|
| **chatDB**        | ✅ Original query | ✅ Formatted reply  | Relational DB (exact turns)                                                 |
| **Cognee**        | ✅ In full turn   | ✅ In full turn     | Single string "User: … Assistant: … Tool: …" → graph + vector (cognify)      |
| **Memos**         | ✅ In messages   | ✅ In messages      | MemOS server (list of role/content; vector/semantic, tasks, skills)         |
| **Composite**     | Same as above     | Same as above       | Writes to both; search merges/dedupes                                       |

“Formatted reply” = the final text shown to the user (Markdown, no raw JSON, optional route label). That is what chatDB keeps for the assistant. Cognee and Memos now receive the full turn (user + assistant + tool) when `memory_turn_data` is present, so cognify and MemOS can use assistant/tool context for better extraction.

---

## 5. Flow diagram (composite)

```
User sends message
       │
       ▼
Core handles request, enqueues to memory_queue
       │
       ▼
process_memory_queue() dequeues
       │
       ▼
mem_instance.add(human_message, user_id=..., agent_id=...)
       │
       ├──► Cognee: add text to dataset → cognify → graph + vector
       │
       └──► Memos:  POST /memory/add { messages: [{ role: "user", content: human_message }], ... }

Later, when answering a new query:

_fetch_relevant_memories(query, user_id, agent_id, limit)
       │
       ▼
mem_instance.search(query, user_id=..., agent_id=..., limit=...)
       │
       ├──► Cognee: search dataset (vector + graph)
       └──► Memos:  POST /memory/search
       │
       ▼
Composite: merge results, dedupe by content, sort by score → return top `limit`
       │
       ▼
Core injects these memories into the LLM context for the reply.
```

---

## 6. Config reference (memory_kb.yml)

- **Backend choice:** `memory_backend: cognee | memos | composite`
- **Cognee:** `cognee` (relational, vector, graph, llm, embedding)
- **Memos:** `memos` (url, timeout, auto_start, viewer_port)
- **Composite:** `composite.backends: [cognee, memos]`, `composite.search_merge: union_by_score | primary_only`

For more detail on Cognee (including cognify and fallbacks), see `docs_design/MemorySystemSummary.md` and `docs_design/CogneeLocalLLM.md`. MemOS standalone is documented under `vendor/memos` (e.g. HOMECLAW-STANDALONE.md).
