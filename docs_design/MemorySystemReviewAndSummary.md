# Memory System: How It Works & Composite Mode Benefits

## 1. How the memory system works

### 1.1 Role of memory

- **RAG memory** = semantic recall of past conversation (what the user said, what was discussed). Used to inject relevant past context into the LLM so replies are personalized and consistent.
- **Separate from:** Chat history (exact turns) is stored in **chatDB** (relational). Memory is for *retrieval* (search by meaning), not for replaying exact messages.

### 1.2 Write path (when we store)

| Step | Where | What happens |
|------|--------|--------------|
| 1 | `core/llm_loop.py` | After the LLM replies (and any tool calls), we build **full-turn data**: `user_message`, `assistant_message`, `tool_messages` (tool name + truncated result per tool). Return value is `(response, memory_turn_data)`. |
| 2 | `core/core.py` | If memory is enabled and `memory_add_after_reply` is true, the request (with `memory_turn_data` attached) is put on **`memory_queue`**. |
| 3 | `process_memory_queue()` | A background task dequeues the request. If `memory_turn_data` is present and has `user_message`, it builds a **list of messages** (user, assistant, tool). Otherwise it uses the **user message string** only. Then it calls **`mem_instance.add(add_data, ...)`** once. |

So a **single** `add()` call receives either:

- A **list** of messages: `[{ role, content [, toolName] }, ...]` (full turn), or  
- A **string** (user message only, legacy/fallback).

### 1.3 What each backend does with `add(data, ...)`

- **Cognee:** If `data` is a list, builds one string: `User: … Assistant: … Tool (name): …` (assistant capped 4000 chars, each tool 2000), then adds that string to the dataset and runs **cognify** (LLM extracts entities/relations → graph + vector). If `data` is a string, stores it as-is.
- **Memos:** If `data` is a list, sends `messages` to MemOS `POST /memory/add` (chunk, dedup, embed; task boundary detection and task summaries run on the MemOS side). If `data` is a string, sends one user message.

So **both Cognee and Memos can store the full turn** when Core passes a list, giving better context for graph extraction and task/skill evolution.

### 1.4 Read path (when we retrieve)

| Step | Where | What happens |
|------|--------|--------------|
| 1 | `core/llm_loop.py` | Before calling the LLM, we call `core._fetch_relevant_memories(query, messages, ..., limit=10)`. |
| 2 | `core/core.py` | `_fetch_relevant_memories` calls **`mem_instance.search(query, user_id=..., agent_id=..., limit=...)`** (and optionally a second search over recent message text). |
| 3 | Results | Returned memories are injected into the LLM context (e.g. as system or user block) so the model can use them to personalize the reply. |

So **one** `search()` call from Core; the backend (or composite) decides how to run that search and what to return.

### 1.5 Config (memory_kb.yml)

- **`use_memory`**: turn RAG memory on/off.
- **`memory_backend`**: `cognee` | `memos` | **`composite`**.
- **`memory_add_after_reply`**: if true (default), enqueue add only after the main LLM reply is ready (avoids cognify competing with the main LLM).
- **`memory_check_before_add`**: if true, one extra LLM call decides “should we store?” before add; default false = store every message.

Cognee and Memos each have their own blocks (`cognee`, `memos`). Composite uses `composite.backends` and `composite.search_merge`.

---

## 2. Composite mode: what it is

**Composite** = one logical memory backend that uses **multiple backends together** (in our case Cognee + Memos).

- **Config:** `memory_backend: composite`, then `composite.backends: [cognee, memos]` (both need their config in the same file). Optional: `composite.search_merge: union_by_score` (default) or `primary_only`.

---

## 3. How composite mode works

### 3.1 Add (write)

- Core still does **one** call: `mem_instance.add(add_data, ...)` with `add_data` = list of messages (full turn) or string (user only).
- **CompositeMemory** receives that and **fans out** to **every** backend in `backends`:
  - **Cognee:** same `add_data` → full-turn string → add → cognify (graph + vector).
  - **Memos:** same `add_data` → POST /memory/add with messages.
- If one backend **fails**, the other still runs; the failure is logged and does not block the other. Return value is built from whichever backend(s) succeeded (or a safe fallback).

So: **same content is written to both Cognee and Memos** in one logical “add.”

### 3.2 Search (read)

- Core still does **one** call: `mem_instance.search(query, user_id=..., agent_id=..., limit=...)`.
- **If `search_merge` is not `primary_only`** (default `union_by_score`):
  - Composite runs **search on all backends in parallel** (e.g. Cognee + Memos).
  - Results are **merged**, **deduped by content** (same text counted once), **sorted by score** (desc), then **top `limit`** returned.
- **If `search_merge: primary_only`**:
  - Only the **first** backend in `backends` is searched (e.g. Cognee only if it’s first).

So: with default merge, **one** search from Core becomes a union of Cognee and Memos results, ranked by score, with no duplicate text.

### 3.3 Other operations

- **get / get_all / update / delete:** Composite delegates (e.g. get tries each backend until one returns a value; update/delete go to first that supports it).
- **reset:** Composite calls reset on each backend.
- **Memos-specific (tasks/skills):** `CompositeMemory.get_memos_adapter()` returns the MemOS backend if present, so tools like task summary or skill search can still talk to Memos directly.

---

## 4. How composite mode benefits us

| Benefit | Explanation |
|--------|-------------|
| **Two retrieval models in one search** | Cognee gives **graph-based** retrieval (entities, relations). Memos gives **chunk + task/skill** retrieval (FTS, vector, RRF, MMR, recency). One `search()` returns a **merged, scored list** so the LLM sees both kinds of signal. |
| **Resilience** | If Cognee is down or cognify fails, Memos still stores and still serves search (and the other way around). Add and search do not all-or-nothing fail. |
| **Full turn in both** | Same full-turn data (user + assistant + tool) is sent to both backends. Cognee’s cognify gets full context for the graph; Memos gets full context for task boundaries and summaries (and eventually skill evolution). |
| **Single config surface** | You choose `memory_backend: composite` and list backends once; Core and the rest of the app keep using a single `mem_instance` for add/search. No duplicate “when to add” or “when to search” logic. |
| **Tunable search** | With `union_by_score` you get the best of both backends in one result set. With `primary_only` you can force “only Cognee” or “only Memos” for search without changing add behavior. |
| **Future-proof** | Adding another backend (e.g. another vector store) would mean adding it to `composite.backends` and implementing the same `add`/`search` interface; composite continues to fan out add and merge search. |

---

## 5. Short flow summary

```
User message → LLM (with optional tools) → reply
       ↓
memory_turn_data = { user_message, assistant_message, tool_messages }
       ↓
Request (with memory_turn_data) enqueued to memory_queue
       ↓
process_memory_queue: add_data = list of messages (or user string)
       ↓
mem_instance.add(add_data, ...)
       │
       ├─ [Composite] → Cognee.add(...)  and  Memos.add(...)  (both get same add_data)
       │
       └─ [Single backend] → only that backend

Later, new user query:
       ↓
mem_instance.search(query, ...)
       │
       ├─ [Composite, union_by_score] → Cognee.search(...) ∥ Memos.search(...)
       │                                  → merge, dedupe by content, sort by score → top N
       │
       └─ [Single backend] → that backend’s search only
       ↓
Memories injected into LLM context → personalized reply.
```

---

## 6. References

- **Backend behavior and full turn:** `docs_design/CogneeMemosMemorySummary.md`
- **Cognee vs Memos capabilities and roadmap:** `docs_design/CogneeAndMemosBenefits.md`
- **Config:** `config/memory_kb.yml` (use_memory, memory_backend, composite.backends, composite.search_merge, cognee, memos)
