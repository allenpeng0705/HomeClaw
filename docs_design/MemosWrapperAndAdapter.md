# MemOS Wrapper & HomeClaw Adapter Design

This doc describes how to **reuse MemOS as much as possible** by adding a thin **HTTP wrapper** around MemOS’s core and a **HomeClaw memory adapter** that talks to it. You keep MemOS’s storage, ingest (chunking, dedup, task/skill pipeline), and recall logic; only the “transport” changes from OpenClaw hooks to HTTP.

---

## 1. Goal

- **Reuse MemOS:** Same SQLite store, IngestWorker, RecallEngine, TaskProcessor, SkillEvolver, embedding/summarizer config. No rewrite in Python.
- **Run without OpenClaw:** A small Node server that instantiates MemOS internals and exposes REST endpoints so any client (including HomeClaw) can add and search memory.
- **Local LLM:** MemOS already supports local embedding (`provider: "local"`) and summarizer/LLM via `openai_compatible` with a local endpoint; the wrapper reuses the same config.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  HomeClaw Core (Python)                                          │
│  memory_backend: memos  →  MemosMemoryAdapter                    │
└────────────────────────────┬────────────────────────────────────┘
                              │ HTTP (add / search / health)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  MemOS Wrapper (Node.js) — standalone server                     │
│  • Express/Fastify: POST /memory/add, POST /memory/search,       │
│    GET /health, optional GET /memory/tasks, POST /memory/flush   │
│  • Builds: buildContext(), SqliteStore, Embedder, IngestWorker,  │
│    RecallEngine, TaskProcessor, SkillEvolver (same as plugin)     │
│  • No OpenClaw API: no api.registerTool(), no api.on("agent_end")│
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  MemOS core (reused as-is)                                       │
│  storage/sqlite, ingest/worker, recall/engine, capture,          │
│  ingest/task-processor, skill/evolver, embedding, viewer (optional)│
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. MemOS Wrapper (New Piece)

A **new Node project** (e.g. `memos-standalone` or a folder under HomeClaw like `memos_wrapper/`) that:

1. **Depends on MemOS as a library**  
   Either:
   - Clone/copy MemOS’s `apps/memos-local-openclaw` and add a second entrypoint (e.g. `server-standalone.ts`) that does not call `api.registerTool` or `api.on`, or  
   - Publish MemOS core as a package (e.g. `@memtensor/memos-core`) and the wrapper depends on it.  
   For minimal change, the first approach is easier: same repo, new script.

2. **Loads config**  
   Same shape as the OpenClaw plugin: `embedding`, `summarizer`, `storage.dbPath`, `recall`, `dedup`, optional `skillEvolution`, etc. Source: env vars, or a config file (e.g. `config.json` / `memos-standalone.yml`), or both.

3. **Creates MemOS components** (same as `index.ts`):
   - `buildContext(stateDir, workspaceDir, config, log)`
   - `SqliteStore(ctx)`, `Embedder(ctx.config.embedding)`, `IngestWorker(store, embedder, ctx)`, `RecallEngine(store, embedder, ctx)`
   - Optional: `TaskProcessor`, `SkillEvolver`, `ViewerServer` if you want tasks/skills/UI.

4. **Exposes HTTP** (instead of OpenClaw hooks):

   | Method + Path | Request body / params | Behavior |
   |---------------|------------------------|----------|
   | `GET /health` | — | 200 if store/embedder ready. |
   | `POST /memory/add` | `{ messages: [{ role, content }], sessionKey?, agentId? }` | Build `ConversationMessage[]` (add `timestamp`, `turnId`, `sessionKey`, `owner`), run through `captureMessages()`, then `worker.enqueue(captured)`. Return 202 Accepted (async ingest). Optional: `POST /memory/add?flush=1` and call `worker.flush()` before returning. |
   | `POST /memory/search` | `{ query, maxResults?, minScore?, agentId? }` | `ownerFilter = ["agent:{agentId}", "public"]`, then `engine.search({ query, maxResults, minScore, ownerFilter })`. Return JSON: `{ hits: [...], meta }` (same shape as MemOS tool result details). |
   | `GET /memory/tasks` | optional `agentId` | If TaskProcessor/store exposed: list tasks for owner. Optional for v1. |
   | `POST /memory/flush` | — | Call `worker.flush()`, return when queue empty. Optional. |

   For **add**, message shape: `{ role: "user" | "assistant" | "tool", content: string }`. The wrapper generates `sessionKey` (default `"homeclaw"` or from body), `turnId` (e.g. UUID or timestamp), `owner = "agent:" + (body.agentId || "main")`. So HomeClaw can send a single message per `add()` call (e.g. one `{ role: "user", content: data }`).

5. **Does not** call `api.on("agent_end")` or `api.on("before_agent_start")`. Capture is **only** via `POST /memory/add`. Recall is **only** via `POST /memory/search`. So the wrapper is stateless from OpenClaw’s perspective and can serve multiple clients (e.g. HomeClaw, or a future OpenClaw “memory proxy” that forwards to this server).

6. **Optional:** Run MemOS’s **Memory Viewer** (ViewerServer) on another port so users can still open the UI (memories, tasks, skills). Same as in the plugin.

---

## 4. HomeClaw Adapter (Python)

A new backend in HomeClaw: **`memory/memos_adapter.py`** (or `memory/memos_http_adapter.py`).

- **Config:** In `config/memory_kb.yml` (or equivalent), add a `memos` section when `memory_backend: memos`, e.g.:
  - `memos.url` — base URL of the wrapper (e.g. `http://127.0.0.1:39201`)
  - `memos.timeout` — optional request timeout
  - Optional: same embedding/summarizer as MemOS (if the wrapper reads from a shared config file); or the wrapper has its own config and HomeClaw only needs the URL.

- **Implements `MemoryBase`:**
  - **add(data, user_id=None, agent_id=None, …)**  
    POST `{ messages: [{ role: "user", content: data }], sessionKey: user_id or "default", agentId: agent_id or "main" }` to `{base}/memory/add`. Optionally wait for flush if you need synchronous behavior (e.g. `?flush=1`).
  - **search(query, user_id=None, agent_id=None, limit=100, …)**  
    POST `{ query, maxResults: limit, agentId: agent_id or "main" }` to `{base}/memory/search`. Map response `hits` to HomeClaw’s expected list of `{ id, memory, score, ... }` (e.g. `memory` = hit’s `summary` or `original_excerpt`, `id` = `chunkId`).
  - **get(memory_id)**  
    Optional: if the wrapper adds `GET /memory/chunk/:id`, call it; else return `None`.
  - **get_all**  
    Return `[]` or implement later if wrapper exposes list endpoint.
  - **update / delete / delete_all**  
    Can return “not supported” at first, or the wrapper can add DELETE later (e.g. delete by chunk id or by owner).
  - **supports_summarization()**  
    Return `False` for v1 (MemOS does its own task/summary pipeline; we don’t run HomeClaw’s batch summarization on top).
  - **reset()**  
    If wrapper exposes `POST /memory/reset` or `DELETE /memory/all`, call it; else no-op or clear only for a given owner.

- **Owner / multi-user:** Map HomeClaw `(user_id, agent_id)` to MemOS `agentId`. For example: `agentId = f"{user_id}_{agent_id}"` or `agent_id` only if you have one agent per user. Use the same value in add and search so MemOS’s `ownerFilter` isolates data.

---

## 5. What You Reuse From MemOS (Unchanged)

- **Storage:** SQLite schema, FTS5, vector table (SqliteStore).
- **Ingest:** IngestWorker (chunking, summarization, dedup, embedding, TaskProcessor.onChunksIngested).
- **Recall:** RecallEngine (FTS + vector, RRF, MMR, recency decay).
- **Tasks:** TaskProcessor (boundary detection, task summaries).
- **Skills:** SkillEvolver (evaluate task → generate/upgrade SKILL.md).
- **Embedding / summarizer:** Same config and providers (including local and openai_compatible).
- **Viewer:** Optional; start ViewerServer in the same process on another port.

So the only new code is: (1) the HTTP server that wires these components and exposes add/search, and (2) the HomeClaw Python adapter that calls that API.

---

## 6. Where the Wrapper Code Can Live

- **Option A — Inside MemOS repo:** Add `apps/memos-local-openclaw/server-standalone.ts` (and a `npm run standalone` script) that starts the HTTP server using the same `src/` as the plugin. No OpenClaw dependency in that entrypoint. MemOS stays one repo; you run either as OpenClaw plugin or as standalone server.
- **Option B — Inside HomeClaw repo:** e.g. `memos_wrapper/` or `vendor/memos-standalone/` with a copy or git submodule of MemOS’s `src/` and a new `server.ts` that imports from `../src` and exposes HTTP. HomeClaw’s install script could run `npm install` and `npm run build` there and start the server (or the user runs it manually).
- **Option C — Separate repo:** e.g. `MemOS-standalone` or `memos-http-server` that depends on `@memtensor/memos-local-openclaw` (if published) or copies MemOS source and exposes the HTTP API. HomeClaw then only needs the adapter and the URL of this server.

**Implemented in HomeClaw:** MemOS is vendored under **vendor/memos**. Copy MemOS from GitHub into that folder; HomeClaw adds `server-standalone.ts`, `memos-standalone.json.example`, and `HOMECLAW-STANDALONE.md`. See §8 and `vendor/memos/HOMECLAW-STANDALONE.md` for copy and run steps.

---

## 7. Local LLM With the Wrapper

- **Embedding:** In the wrapper’s config (env or file), set MemOS-style `embedding: { provider: "local" }` for Xenova, or `provider: "openai_compatible", endpoint: "http://127.0.0.1:5066/v1", apiKey: "local"` for your local embedding server.
- **Summarizer / skill LLM:** Set `summarizer` (and optional `skillEvolution.summarizer`) to `openai_compatible` with your local chat endpoint (e.g. same host:port as HomeClaw’s main LLM). No OpenClaw needed; the wrapper reads config from its own env/file.

So “we still use local LLM for the memos” is satisfied by configuring the wrapper the same way you would configure MemOS in OpenClaw: local or openai_compatible for both embedding and summarizer.

---

## 8. Minimal Implementation Checklist

**Phase 1 — Wrapper**

1. Add a standalone entrypoint (e.g. `server-standalone.ts`) that:
   - Reads config (env + optional file).
   - Calls `buildContext`, creates Store, Embedder, IngestWorker, RecallEngine.
   - Registers `POST /memory/add` (body → captureMessages → enqueue), `POST /memory/search` (body → engine.search), `GET /health`.
   - Listens on a port (e.g. 39201 or from config).

2. (Optional) Add `?flush=1` to add, or `POST /memory/flush`, for synchronous add.

3. (Optional) Start ViewerServer on a second port.

**Phase 2 — HomeClaw adapter**

1. Add `memory/memos_adapter.py`: `MemosMemoryAdapter(MemoryBase)` with `add` and `search` calling the wrapper HTTP API; map `(user_id, agent_id)` to `agentId`/`sessionKey`.
2. In `core/initialization.py`, when `memory_backend == "memos"`, instantiate `MemosMemoryAdapter` with config from `memory_kb.yml` (memos.url, etc.).
3. Document in `memory_kb.yml` and install docs: start the MemOS standalone server (e.g. `cd memos_wrapper && npm run start`), set `memory_backend: memos` and `memos.url`.

**Phase 3 (optional)**

- Expose `GET /memory/tasks`, `GET /memory/skills` in the wrapper and, if useful, surface them via HomeClaw (e.g. tools or Portal).
- Add reset/delete endpoints and implement `reset()` / `delete` in the adapter.

This way you **write only the wrapper and the adapter**; MemOS itself is reused as much as possible and still drives tasks and skills when the wrapper runs its IngestWorker and TaskProcessor.
