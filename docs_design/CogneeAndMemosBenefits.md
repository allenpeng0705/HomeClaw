# Getting the Benefits of Both Cognee and MemOS

When using **composite** memory (Cognee + MemOS together), each system contributes different strengths. This doc explains what you get today, what runs under the hood, and how to get **full** benefit from MemOS’s task summarization and skill evolution.

---

## 1. What Each System Contributes

| Capability | Cognee | MemOS |
|------------|--------|--------|
| **Storage** | Graph + vector + relational (entities, relationships) | SQLite + FTS5 + vector (chunks, tasks, skills) |
| **Add** | Raw data → cognify (LLM extracts graph) → graph + vector | Messages → chunking, dedup, embed → chunks; then **task boundary detection** and **task summaries** |
| **Search** | Graph completion, triplets, semantic over graph | Hybrid FTS + vector, RRF, MMR, recency; can return chunk + task_id |
| **Structured semantics** | Entities and relations (knowledge graph) | **Tasks** (Goal, Key Steps, Result, Key Details) and **Skills** (SKILL.md, scripts, evals) |
| **Evolution** | — | **Skill evolution**: task completion → evaluate → create/upgrade skill, versioning, quality score |
| **Multi-agent** | — | Owner isolation, **public memory**, **skill visibility** (private/public), skill_search, publish/unpublish |

With **composite** (add to both, search merged):

- **Cognee** gives graph-based retrieval and entity/relation semantics.
- **MemOS** gives chunk search plus **internal** task segmentation and summaries; skill evolution is wired in the standalone server (completed tasks → create/upgrade skills). Exposing tasks and skills to the agent still requires the API and tools below.

---

## 2. What Works Today (Composite + Standalone MemOS)

**Add (to both)**  
Every message is sent to Cognee and to MemOS (POST /memory/add). So:

- **Cognee**: receives the **full turn** (user + assistant + tool) as a single formatted string (`User: … Assistant: … Tool (name): …`), then runs add → cognify. Storing both user and assistant gives cognify **conversational context** (e.g. assistant asked “What’s your favorite color?” → user said “Blue” → the graph can map Blue to favorite color correctly); user-only storage can fragment entities and lose provenance. Assistant text is truncated to 4000 chars, each tool to 2000.
- **MemOS**: runs IngestWorker (chunk, dedup, embed, store). The worker also calls **TaskProcessor.onChunksIngested**, so:
  - **Task boundary detection** (SAME/NEW + idle timeout) runs.
  - **Task summaries** (Goal, Key Steps, Result, Key Details) are generated when a task completes.
  - **Skill evolution** runs in the standalone server: `worker.getTaskProcessor().onTaskCompleted(...)` is registered with SkillEvolver, so completed tasks trigger skill creation/upgrade (see §4 for exposing tasks/skills to the agent).

**How MemOS does this with user messages only**  
HomeClaw currently sends only **user** messages to MemOS (one per `add`: `messages: [{ role: "user", content: "<user text>" }]`). MemOS can still run the pipeline as follows:

- **Chunking / ingest:** Each user message is chunked, deduped, embedded, and stored. No assistant text is required.
- **Task boundary detection:** Boundaries are driven by **time and sequence**, not by assistant turns. MemOS uses heuristics such as:
  - **Idle timeout:** No new message for a configured period → current task is closed (task “completes”).
  - **SAME/NEW (or similar) logic:** Semantic or temporal shift between consecutive **user** messages can start a “new” task (e.g. topic change or new request).
  So a “task” is a segment of the **user’s** conversation (one or more user messages) until a boundary is detected.
- **Task summaries:** When a task is closed (e.g. after idle timeout), MemOS generates a summary from the **chunks it has** for that task — i.e. from **user content only**. So:
  - **Goal** and **Key Steps** can be inferred from the user’s requests and follow-ups.
  - **Result** and **Key Details** are missing or only guessed (e.g. from the user’s last message), since the assistant’s reply is not stored.
  Summaries are therefore **user-side only**; they describe what the user asked or did, not what the agent did or returned.
- **Skill evolution:** SkillEvolver runs on **completed tasks** (same boundaries as above). Skills are created/upgraded from the task summary and chunks — again **user content only**. So skills reflect “what the user wanted” or “what the user said,” not the actual assistant behavior or output. Richer skills (e.g. that include the assistant’s steps or result) would require sending **user + assistant** messages to MemOS (see §3 and roadmap).

**Search (merged)**  
HomeClaw calls composite search → Cognee search + MemOS search → merge by score, dedupe by content. So you get:

- Graph-based results (Cognee).
- Chunk/task-linked results (MemOS). MemOS hits can include `task_id`; we don’t yet expose “get task summary” or “search skills” to the agent.

**Multi-agent / owner**  
We pass `agentId` (from user_id/agent_id) to MemOS add and search, so **memory isolation by owner** works. Public memory and skill sharing would need extra API and tools (§4).

---

## 3. How to Get Full Benefit (Roadmap)

### 3.0 Send user + assistant + tool messages to MemOS (implemented)

Today only the **user** message is sent to MemOS. To get **full** task summaries (including Result, Key Details) and skills that reflect what the **assistant** did (not only what the user asked), Core should send **user + assistant** (and optionally tool) messages per turn, matching how the MemOS OpenClaw plugin does it.

**How MemOS is used in OpenClaw**  
The [MemOS OpenClaw plugin](https://github.com/MemTensor/MemOS/tree/main/apps/memos-local-openclaw) wires memory via an **`agent_end`** event (after each successful agent turn):

1. **When:** On `api.on("agent_end", ...)` — once per completed turn.
2. **What:** The event carries `event.messages` = the full conversation; the plugin takes only **new** messages since the last cursor (incremental): `newMessages = allMessages.slice(cursor)`.
3. **Shape:** Each message has `role` (`user` | `assistant` | `tool`), `content` (string or array of blocks), and for tools `toolName`/`name`. Consecutive **assistant** messages are merged into one. System messages are skipped; the plugin’s own memory tool results are skipped to avoid feedback loops.
4. **Capture:** `captureMessages(msgs, sessionKey, turnId, evidenceTag, log, owner)` builds an array of `{ role, content, timestamp, turnId, sessionKey, toolName?, owner }`. It strips OpenClaw-specific metadata from user messages and evidence wrappers from assistant/tool content.
5. **Ingest:** `worker.enqueue(captured)` — the same IngestWorker used by the standalone server. Chunking, dedup, embed, and **TaskProcessor.onChunksIngested** (task boundaries + summaries) all run over this **user + assistant + tool** stream. So task summaries get **Goal, Key Steps, Result, Key Details** from the full exchange, and skill evolution sees what the assistant actually did.

The standalone server’s `POST /memory/add` already accepts `messages: Array<{ role: string; content: string }>` and forwards them to the same `captureMessages` + `worker.enqueue` pipeline. So the **API contract** supports multiple messages per request; HomeClaw currently sends only one (user).

**What HomeClaw should do**  
To align with OpenClaw and get full task/skill benefit:

1. **When to add:** After the turn is done and the final **formatted** response is known (same moment you today write to chatDB). Either:
   - **Option A:** Enqueue to `memory_queue` a **single** item that contains both `user_message` and `assistant_message` (and optionally tool results). The consumer (`process_memory_queue` or a dedicated MemOS path) then calls MemOS **once per turn** with `messages: [{ role: "user", content: user_message }, { role: "assistant", content: assistant_message }]`.
   - **Option B:** Keep enqueuing the user message as today for Cognee (and for MemOS if you want Cognee unchanged). **Additionally**, after the reply is written to chatDB, enqueue a second “memory add” that carries `(user_message, assistant_message)` and is handled only for MemOS (or composite): one `mem_instance.add()` is not used; instead, call the MemOS HTTP API directly with the two-message payload so Cognee still receives only the user message and MemOS receives the full turn.

2. **Payload shape:** For MemOS (and composite when the backend is MemOS), send one `POST /memory/add` per turn with body:
   - `messages: [{ role: "user", content: "<user query>" }, { role: "assistant", content: "<formatted reply>" }]`
   - Same `sessionKey`, `agentId` as today. Optional: include tool calls/results as `role: "tool"` with `content` (and `toolName` if the standalone server type is extended) so MemOS can chunk them too.

3. **Adapter change:** In `memory/memos_adapter.py`, today `add(data, ...)` sends `messages: [{"role": "user", "content": data}]`. To support “user + assistant” without breaking the existing single-string `mem_instance.add(data)` contract, either:
   - Add a second entry point (e.g. `add_turn(user_message, assistant_message, ...)`) that POSTs `messages: [{ role: "user", content: user_message }, { role: "assistant", content: assistant_message }]`, and have Core call that when MemOS/composite is in use and the turn is complete; or
   - Allow `data` to be a list of `{ "role", "content" }` when the backend is MemOS: if `isinstance(data, list)`, send it as `messages: data`, else keep current behavior `messages: [{ role: "user", content: data }]`. Then Core enqueues a payload that carries either a string (user only) or a list of messages (user + assistant) and the consumer passes it through accordingly.

**Implementation (HomeClaw):** After each turn, `answer_from_memory` returns `(response, memory_turn_data)`. When `memory_add_after_reply` is true, the request is enqueued with `request.memory_turn_data` set to `{ user_message, assistant_message, tool_messages }`. `process_memory_queue` builds a messages list (user + assistant + tool, each tool with `role`, `content`, `toolName`) and calls `mem_instance.add(messages, ...)`. The MemOS adapter sends that list as `POST /memory/add` body `messages`; the Cognee adapter extracts only user content and passes a string. So MemOS receives the full turn (user + assistant + tool/skills); Cognee continues to receive user-only text. Once MemOS receives the full turn, its existing pipeline (same as OpenClaw) produces full task summaries and skills that reflect assistant behavior.

### 3.1 Wire skill evolution in the standalone server (done)

The standalone server registers `worker.getTaskProcessor().onTaskCompleted(...)` with **SkillEvolver**, so completed tasks trigger skill creation/upgrade. Task summarization and skill evolution both run when using the standalone server.

### 3.2 Expose task and skill APIs from the standalone server

To let HomeClaw (and the agent) use tasks and skills, add HTTP endpoints that mirror MemOS’s tools:

| Endpoint | Purpose |
|----------|---------|
| `GET /memory/tasks?agentId=` | List tasks (active/completed/skipped) for owner |
| `GET /memory/task/:id/summary` | Full task summary (Goal, Key Steps, Result, Key Details) |
| `POST /memory/skill_search` | Body: `{ query, scope?, agentId? }` → FTS + vector + LLM relevance, return skills |
| `GET /memory/skill/:id` | Get skill content (e.g. SKILL.md) by skill id or task id |
| `POST /memory/memory_write_public` | (Optional) Write a public memory for multi-agent sharing |

Implementation: call MemOS’s **store** and **RecallEngine** (e.g. `engine.searchSkills(...)`) and return JSON. No OpenClaw dependency.

### 3.3 HomeClaw tools that call MemOS tasks/skills

Once the standalone server exposes the above:

- **memory_task_summary** (or **memos_task_summary**): when the agent has a hit with `task_id`, it can call this tool with `task_id` to get the full structured summary (Goal, Key Steps, Result, Key Details).
- **memory_skill_search** (or **memos_skill_search**): query MemOS skills (FTS + vector + LLM); useful for “find a skill that does X” before running it.
- **memory_skill_get**: get full skill content by id (e.g. to run or show the user).
- Optional: **memory_write_public** to write shared knowledge for multi-agent.

These can be implemented as normal HomeClaw tools that HTTP-call the MemOS standalone (only when `memory_backend` is `memos` or `composite` and MemOS URL is configured). Search results from the composite adapter could optionally include `task_id` / `skill_id` when the hit came from MemOS so the agent knows when to call task_summary or skill_get.

### 3.4 Memory Viewer (optional)

Run MemOS’s **ViewerServer** (e.g. on a second port) from the same process as the standalone server. Then humans can open the MemOS UI to browse memories, **tasks**, and **skills**, edit/delete, retry skill generation, and change visibility. The agent still uses the HTTP API and HomeClaw tools above.

---

## 4. Summary: What You Get When

| Feature | Today (composite + current standalone) | After wiring SkillEvolver | After adding task/skill API + tools |
|---------|----------------------------------------|----------------------------|-------------------------------------|
| Add to both (Cognee + MemOS) | Yes | Yes | Yes |
| Search merged (graph + chunks) | Yes | Yes | Yes |
| Task boundary detection | Yes (inside MemOS) | Yes | Yes |
| Task summaries (Goal, Steps, Result) | Yes (stored in MemOS) | Yes | Yes |
| Skill evolution (create/upgrade SKILL.md) | No | Yes | Yes |
| Agent can “get task summary” | No | No | Yes (tool → GET /memory/task/:id/summary) |
| Agent can “search skills” | No | No | Yes (tool → POST /memory/skill_search) |
| Multi-agent (owner + public memory/skills) | Owner only | Owner only | Full if we add write_public + skill APIs |
| Human UI for tasks/skills | No | No | Yes (optional ViewerServer) |

---

## 5. Recommended order of work

1. **Wire SkillEvolver in server-standalone.ts** so task completion triggers skill creation/upgrade (same behaviour as the MemOS plugin).
2. **Add GET /memory/task/:id/summary and POST /memory/skill_search** (and optionally GET /memory/skills, GET /memory/skill/:id) to the standalone server.
3. **Add HomeClaw tools** that call these endpoints when MemOS is configured (memos or composite), and optionally include `task_id` in composite search results when the hit is from MemOS.
4. **(Optional)** Start ViewerServer for the MemOS UI; **(optional)** add memory_write_public and skill publish/unpublish for full multi-agent use.

This way you keep **Cognee’s graph** and **MemOS’s task summarization and skill evolution** working together, and the agent (and users) can explicitly use tasks and skills instead of only merged chunk search.
