# How the Cognee-based memory system works (step by step)

This doc describes how **RAG memory** works when **memory_backend: cognee**: how content is **added** and how it is **searched** and used in the main LLM prompt. Two examples walk through the flow.

---

## Overview

- **Write path:** User messages are put on a **memory queue**; a background task takes them and calls **Cognee add → cognify** so they become searchable.
- **Read path:** When the main LLM is about to reply, we **search** Cognee with the current query and inject the top results as **"RelevantMemory"** (context) into the system prompt.
- **Scope:** Everything is scoped by **user_id** and **agent_id** (friend_id). The Cognee dataset name is `memory_{user_id}_{agent_id}` (e.g. `memory_AllenPeng_HomeClaw`).

---

## Part 1: Adding to memory (write path)

### Steps

1. **User sends a message**  
   Companion (or another channel) sends a message to Core via POST /inbound. Core builds a **PromptRequest** (user_id, friend_id, text, etc.) and calls **process_text_message**.

2. **Request is put on the memory queue**  
   Inside **process_text_message**, if **use_memory** is true, Core does:
   ```text
   await self.memory_queue.put(request)
   ```
   So the **same** request that will be used to generate the reply is also queued for memory. The reply is generated right after; the memory add runs **in the background** and does not block the response.

3. **Background task consumes the queue**  
   **process_memory_queue** runs in a loop:
   - Waits for a request: `request = await self.memory_queue.get()`
   - Extracts **user_id**, **friend_id** (agent_id for memory), and the **human message** text
   - Optionally, if **memory_check_before_add** is true, runs an LLM call to decide “should we store this?”; only if the answer is “yes” does it call **add**
   - By default (memory_check_before_add false), it always calls:
     ```text
     await self.mem_instance.add(human_message, user_name=..., user_id=..., agent_id=_fid, ...)
     ```
   - **mem_instance** is **CogneeMemory** when memory_backend is cognee.

4. **CogneeMemory.add (Cognee adapter)**  
   For each call, **CogneeMemory.add** does:
   - **Dataset name:** `dataset = memory_{user_id}_{agent_id}` (e.g. `memory_AllenPeng_HomeClaw`).
   - **Step 1 — add:** `await self._cognee.add(data, dataset_name=dataset)`  
     Raw text is stored in Cognee’s dataset (relational/vector as per Cognee config).
   - **Step 2 — cognify:** `await self._cognee.cognify(datasets=[dataset])`  
     Cognee runs its **LLM/graph pipeline** on the new data (entities, relationships, etc.). This step uses **cognee.llm** (or main_llm if empty). If cognify fails with a template/local error and **cognee.llm_fallback** is set, we retry once with the fallback LLM; otherwise add is skipped for that message. Chat and tools are unaffected.
   - On success, the dataset is marked as “has graph” so later **search** can run on it.

5. **Result**  
   The user’s message is now in Cognee’s graph for that user/friend and can be retrieved by **search** for later queries.

### Example 1: “Can you summarize my resume and convert to PDF?”

1. User sends: *“Can you help me summarize Allen_Peng_resume_en.docx using MarkDown format and convert it to PDF file?”*
2. Core handles the request: **memory_queue.put(request)** and then **answer_from_memory(...)** runs to produce the reply.
3. In the background, **process_memory_queue** gets the request, takes:
   - `user_id = AllenPeng`, `agent_id = HomeClaw`, `human_message = "Can you help me summarize ..."`
4. It calls **mem_instance.add(human_message, user_id=AllenPeng, agent_id=HomeClaw, ...)**.
5. **CogneeMemory.add**:
   - `dataset = "memory_AllenPeng_HomeClaw"`
   - **add(data, dataset_name=dataset)** → raw text is stored.
   - **cognify(datasets=[dataset])** → Cognee’s LLM builds/updates the knowledge graph for that dataset. If this fails (e.g. InstructorRetryException with local LLM), the step is logged and memory add is skipped for that message; the user still got their reply from step 2.

---

## Part 2: Searching memory (read path)

### Steps

1. **User sends a new message**  
   Same as before: POST /inbound → **process_text_message** → **answer_from_memory(query=..., messages=..., user_id=..., request=...)**.

2. **Before calling the LLM, fetch relevant memories**  
   Inside **answer_from_memory**, if **use_memory** is true and the preset allows Cognee:
   ```text
   relevant_memories = await core._fetch_relevant_memories(
       query, messages, user_name, user_id, agent_id, run_id, filters, limit=10
   )
   ```
   **agent_id** here is the **memory scope** (e.g. friend_id like HomeClaw).

3. **_fetch_relevant_memories**  
   Core calls:
   ```text
   memories = await self.mem_instance.search(
       query=query,
       user_name=user_name,
       user_id=user_id,
       agent_id=agent_id,
       ...
       limit=limit,
   )
   ```

4. **CogneeMemory.search (Cognee adapter)**  
   For each search:
   - **Dataset name:** `dataset = memory_{user_id}_{agent_id}` (same as add).
   - **Skip if dataset not ready:** If the dataset doesn’t exist or has never had a successful **cognify**, we return [] (no “empty graph” search).
   - **Search:** `results = await self._cognee.search(query, datasets=[dataset], top_k=limit)`  
     Cognee runs semantic search (and graph retrieval) over that dataset.
   - Results are returned as a list of dicts with at least **memory** (text) and **score**.

5. **Inject into system prompt**  
   **answer_from_memory** builds:
   - `memories_text = "1: <snippet1> 2: <snippet2> ..."` from the search results (or `"None."` if none).
   - `context_val = memories_text`
   - This is passed into the **chat/response** prompt (e.g. RESPONSE_TEMPLATE or prompt manager) as **context**. So the main LLM sees a “RelevantMemory” / context block and can use it to answer.

6. **LLM and tools**  
   The rest of the flow (system prompt, tools, LLM call, tool loop, etc.) runs as usual; the model can use the injected memories when replying.

### Example 2: “What did I ask you to do with my resume?”

1. User sends: *“What did I ask you to do with my resume?”*
2. **answer_from_memory** is called with `query = "What did I ask you to do with my resume?"`, `user_id = AllenPeng`, `agent_id = HomeClaw` (or the current friend).
3. **_fetch_relevant_memories** calls **mem_instance.search(query=..., user_id=AllenPeng, agent_id=HomeClaw, limit=10)**.
4. **CogneeMemory.search**:
   - `dataset = "memory_AllenPeng_HomeClaw"`
   - If that dataset exists and has been cognified, **cognify.search(query, datasets=[dataset], top_k=10)** runs.
   - Cognee returns e.g. chunks or graph-backed snippets that mention the resume and “summarize … MarkDown … PDF”.
5. Those snippets are formatted as **memories_text** and injected as **context** into the system prompt.
6. The main LLM sees something like: *“Relevant context: 1: User asked to summarize Allen_Peng_resume_en.docx using MarkDown and convert to PDF …”* and can answer: *“You asked me to summarize your resume in MarkDown and convert it to PDF.”*

---

## Summary table

| Step | Where | What happens |
|------|--------|----------------|
| 1. Queue | process_text_message | memory_queue.put(request) so the same request is later used for add |
| 2. Consume | process_memory_queue | get request → extract user_id, friend_id, human_message → mem_instance.add(...) |
| 3. Add (raw) | CogneeMemory.add | dataset = memory_{user_id}_{agent_id}; _cognee.add(data, dataset_name=dataset) |
| 4. Cognify | CogneeMemory.add | _cognee.cognify(datasets=[dataset]); uses cognee.llm (or main_llm if not set) |
| 5. Search trigger | answer_from_memory | _fetch_relevant_memories(query, user_id, agent_id, limit=10) |
| 6. Search | CogneeMemory.search | dataset = memory_{user_id}_{agent_id}; _cognee.search(query, datasets=[dataset], top_k=limit) |
| 7. Inject | answer_from_memory | Build memories_text from results → context_val → system prompt (response template / context block) |

---

## Scope and config

- **Dataset = user + friend:** `memory_{user_id}_{agent_id}`. So each (user, friend) has its own Cognee dataset; switching friend changes the memory scope.
- **Cognee LLM:** Cognify uses **cognee.llm** from config (or main_llm if empty). For local-first: set **cognee.llm_fallback** to a cloud endpoint so cognify retries with cloud when local fails (see MemorySystemSummary §9).
- **Chat and tools** do not depend on memory add succeeding; if cognify fails, only that message is not added; the user still gets their reply from the main LLM.
