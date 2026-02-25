# HomeClaw — Design Document

This document describes the architecture, components, and data flow of **HomeClaw**. It serves as the base reference for understanding the project and for future development.

**Other languages / 其他语言 / 他の言語 / 다른 언어:** [简体中文](Design_zh.md) | [日本語](Design_jp.md) | [한국어](Design_kr.md)

---

## 1. Project Overview

### 1.1 Purpose

**HomeClaw** is a **local-first AI assistant** that:

- Runs on the user’s machine (e.g. home computer).
- Supports **local LLMs** (via llama.cpp server) and **cloud AI** (via OpenAI-compatible APIs, using **LiteLLM**).
- Exposes the assistant through **multiple channels** (email, IM, CLI) so users can interact from anywhere (e.g. from a phone) with their home instance.
- Uses **RAG-style memory**: **Cognee** (default) or in-house SQLite + Chroma; optional per-user **profile** and **knowledge base**. See docs_design/MemoryAndDatabase.md.
- Extends behavior through **plugins** (plugin.yaml + config.yml + plugin.py; route_to_plugin or orchestrator), **skills** (SKILL.md under skills/; optional vector search; run_skill tool), and a **tool layer** (use_tools: true — exec, browser, cron, sessions_*, memory_*, file_*, etc.). See docs_design/ToolsSkillsPlugins.md.

### 1.2 Design Goals

- **Local-first**: Primary operation on local hardware; cloud optional.
- **Simple deployment**: Minimal dependencies (SQLite, Chroma, no heavy DB by default).
- **Channel-agnostic**: Same core regardless of how the user connects (email, Matrix, Tinode, WeChat, WhatsApp, CLI).
- **Extensible**: Plugins for features; possibility for a dedicated HomeClaw channel later.
- **Multi-model**: Different models for chat vs embedding; multiple models loadable via config.

---

## 2. High-Level Architecture

```
                    ┌──────────────────────────────────────────────────────────────────────────────────┐
                    │                              Channels                                             │
                    │  Email │ Matrix │ Tinode │ WeChat │ WhatsApp │ CLI(main) │ Webhook │ WebSocket   │
                    │  (full BaseChannel or inbound-style)                                              │
                    └─────────────────────────────────────┬────────────────────────────────────────────┘
                                                            │ HTTP (PromptRequest or /inbound) / WS /ws
                                                            ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │                      Core Engine                         │
                    │  • Request routing  • Permission check  • Orchestrator   │
                    │  • Plugin selection • Response dispatch • TAM (optional)  │
                    └───────┬─────────────────────────────┬────────────────────┘
                            │                             │
              ┌─────────────┴─────────────┐     ┌─────────┴─────────┐
              │  Core handles directly    │     │  Route to Plugin  │
              │  (chat + memory + RAG)     │     │  (Weather, News…)  │
              └─────────────┬─────────────┘     └─────────┬─────────┘
                            │                             │
                            │         ┌───────────────────┘
                            ▼         ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │  LLM Layer (llm/)                                        │
                    │  • Local: llama.cpp server (multi-model, main + embedding)│
                    │  • Cloud: LiteLLM (OpenAI-compatible API)                 │
                    └─────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌─────────────────────────────────────────────────────────┐
                    │  Memory (memory/)                                        │
                    │  • Cognee (default) or SQLite + Chroma (RAG)             │
                    │  • Chat history, sessions, runs; optional profile, KB    │
                    │  • Embedding model (local or cloud) for vectorization     │
                    └─────────────────────────────────────────────────────────┘
```

- **Channels** send user input as `PromptRequest` to the **Core** over HTTP.
- **Core** either handles the request itself (chat + memory/RAG) or routes to a **Plugin**.
- **LLM** calls go to one endpoint: either the local llama.cpp server or the LiteLLM proxy (same OpenAI-compatible API).
- **Memory** stores chat and vectorized knowledge used for RAG.

---

## 3. Core Components

### 3.1 Core Engine (`core/`)

- **Role**: Central router, permission checker, and handler for chat + memory.
- **Entry**: `core/core.py` — `Core` (singleton) runs a FastAPI app and starts the LLM manager.
- **Key endpoints**:
  - `POST /process`: Async path for channels; enqueues request, returns immediately; response is sent back via `POST /get_response` on the channel.
  - `POST /local_chat`: Sync path for CLI; processes request and returns response body.
  - `POST /inbound`: Minimal sync API for any bot: JSON `{ "user_id", "text", … }` → `{ "text" }`. No channel process needed; permission via user.yml.
  - `WebSocket /ws`: Same contract as /inbound for our own client (e.g. WebChat); one persistent connection.
  - `POST /register_channel`, `POST /deregister_channel`: Channel registration.
- **Behavior**:
  1. Check permission (`config/user.yml`: user identities and allowed channel types).
  2. If **orchestrator + plugins** are enabled: Orchestrator turns request into an **Intent** (e.g. TIME vs OTHER). For OTHER, Core uses LLM to pick a plugin by description; if one matches, it runs that plugin and the plugin sends the response (e.g. via `send_response_to_latest_channel`).
  3. If Core handles it: load chat history (SQLite), optionally enqueue to memory, run RAG (`answer_from_memory`), call LLM, store turn in chat DB, and send response back to the channel.
- **Queues**: `request_queue`, `response_queue`, `memory_queue` for async processing and response delivery.
- **Config**: `config/core.yml` (host, port, main_llm, embedding_llm, memory_backend, use_memory, use_tools, use_skills, use_workspace_bootstrap, tools.*, result_viewer, auth_enabled, auth_api_key, mode, etc.). **Auth**: When `auth_enabled: true`, /inbound and /ws require X-API-Key or Authorization: Bearer; see docs_design/RemoteAccess.md. **Result viewer**: Optional save_result_page tool and report server (port, base_url); see docs_design/ComplexResultViewerDesign.md.

**Orchestrator** (`core/orchestrator.py`): Classifies intent (TIME / OTHER) from chat history + user input; for OTHER, Core selects a plugin. **TAM** (`core/tam.py`): Time Awareness Module; handles TIME intents (e.g. scheduling). Orchestrator + TAM + plugins are always enabled. Routing style is controlled by **orchestrator_unified_with_tools** in `core.yml` (default true = main LLM with tools does routing; false = separate orchestrator_handler runs first with one LLM call).

**Time/scheduling: two paths.** (1) **Intent path**: User says something time-related (e.g. “remind me every day at 9am”) → Orchestrator classifies as TIME → TAM analyzes the message with an LLM and produces a scheduling JSON (reminder with repeated/fixed/random, or **cron** with `cron_expr`) → TAM schedules the job. (2) **Tool path**: When `use_tools` is true, the model can call **cron_schedule** and **cron_list** directly; no intent classification—TAM still stores and runs the cron jobs. Both paths use the same TAM scheduler and cron list.

**One Core, multiple LLMs (local + cloud).** HomeClaw has one Core but can use multiple LLMs from config. **Config**: `local_models` (list of id, path, host, port; e.g. llama.cpp per model) and `cloud_models` (list of id, path, host, port, api_key_name; e.g. LiteLLM to OpenAI/Anthropic/Gemini). **main_llm** is one ref (e.g. `local_models/qwen25_14B_q5_k_m` or `cloud_models/OpenAI-GPT4o`) and is the default for all chat and tool completions. **embedding_llm** is a separate ref for RAG. **Runtime**: Util.main_llm() resolves main_llm to (path, model_id, type, host, port); Util.get_llm(name) and _get_model_entry(name) resolve any `local_models/<id>` or `cloud_models/<id>`. Util.switch_llm(llm_name) changes the global main_llm (persisted to YAML). **Per-call model**: Util.openai_chat_completion(…, llm_name=None) accepts optional llm_name; Util._resolve_llm(llm_name) returns (path, model_id, type, host, port) for that ref or falls back to main_llm. So any caller (Core, plugins, tools) can pass llm_name to use a different model for that call. **sessions_spawn** (tool): sub-agent one-off run—Core.run_spawn(task, llm_name=None) runs a single user message with an optional system prompt and returns the model reply; the tool can pass llm_name (e.g. local_models/deepseek_r1_qwen_7B_q5_k_m) to use a faster/smaller model for the spawn while the main chat keeps using main_llm. So: one agent, multiple LLMs—main chat, spawn, vision—selected by config ref and llm_name per call.

**One agent vs multiple agents.** Today we have **one agent** (one identity, one tool set, one skills set) shared by all LLM calls. That is a valid design: “one assistant, many models” — same persona and capabilities; only the model doing the reasoning changes (e.g. main_llm for chat, a smaller/faster model for spawn, a vision model for image). It is **OK** and keeps config and routing simple. **Alternative**: **multiple agents**, each with its own identity (SOUL/IDENTITY), tools (allowlist or subset), and skills (or subset), and optionally a default LLM. Then you get “many assistants” (e.g. support bot vs coder bot vs writer bot) with different personas and capabilities; session or request would be routed to an agent, and that agent’s context + (optionally) its default LLM would be used. The initial design for HomeClaw was to run **multiple agents**; the codebase can evolve toward that (agent registry, per-agent workspace, session→agent or request→agent routing) while keeping the current “one agent, multiple LLMs” as the default or as one of the agents. **Recommended default**: **one agent, multiple LLMs** — simpler, fits most single-assistant use cases, and you can add multi-agent later (optional agent_id, per-agent workspace) when you need distinct personas or capability sets. So: ship one agent with multiple LLMs now; extend to multiple agents when there is a concrete need.

### 3.2 Channels (`channels/`, `main.py`, Core `/inbound` & `/ws`)

Channels are the way users (or bots) reach the Core. HomeClaw supports two patterns:

| Pattern | Description | When to use |
|--------|-------------|-------------|
| **Full channel** | Separate process implementing `BaseChannel`: registers with Core, sends `PromptRequest` (HTTP), receives reply via **async** `POST /get_response` or **sync** `POST /local_chat`. | Email, Matrix, Tinode, WeChat, WhatsApp, CLI — when you need a dedicated process that owns the IM/protocol connection and may need async delivery. |
| **Minimal (inbound / WebSocket)** | No `BaseChannel` process. External bot or client sends a **minimal payload** to the Core and gets a **sync** reply. | Any new bot (Telegram, Discord, etc.): just POST to Core or to the Webhook relay. Our own client (e.g. WebChat): connect to Core over WebSocket. |

Both use the same permission model: `config/user.yml` (user identities and allowed channel types). Below we list all channels in detail.

#### 3.2.1 Base contract: `BaseChannel` (full channels)

- **Role**: Adapt an external interface (IM, email, etc.) to the Core’s `PromptRequest` and deliver responses back.
- **Base class**: `base/BaseChannel.py` — `BaseChannel` with:
  - `ChannelMetadata` (name, host, port, endpoints).
  - `register_channel` / `deregister_channel` (call Core’s HTTP endpoints so Core knows where to send replies).
  - `transferTocore(request)` (async: Core will POST to this channel’s `/get_response`) or `localChatWithcore(request)` (sync: Core returns body in the same HTTP response).
  - `POST /get_response`: endpoint the Core calls to push an `AsyncResponse` back to the channel; subclass implements delivery to the user (e.g. send email, send IM message).

Full channels use `channels/.env` (e.g. `core_host`, `core_port`) to reach the Core.

#### 3.2.2 Existing channels (full, in-tree)

| Channel | Location | How it works | Config / notes |
|---------|----------|---------------|----------------|
| **Email** | `channels/emailChannel/` | IMAP polling for new mail; builds `PromptRequest` from From/Subject/Body; SMTP to reply. Async: Core POSTs to channel’s `/get_response`, channel sends email. | `config/email_account.yml` (IMAP/SMTP, credentials). `channels/emailChannel/config.yml` (host, port). |
| **Matrix** | `channels/matrix/` | Matrix client; on room message → build `PromptRequest` → Core; on `/get_response` → send message back to room. | `channels/matrix/config.yml`, `channels/matrix/.env`. |
| **Tinode** | `channels/tinode/` | Tinode messenger client; same flow as Matrix. | `channels/tinode/config.yml`, `channels/tinode/.env`. |
| **WeChat** | `channels/wechat/` | WeChat integration (e.g. wcferry); receive message → Core; reply via WeChat API. | `channels/wechat/config.yml`, `channels/wechat/.env`. |
| **WhatsApp** | `channels/whatsapp/` | WhatsApp client (e.g. neonize); receive message → Core; reply via WhatsApp. | `channels/whatsapp/config.yml`, `channels/whatsapp/.env`. |
| **Telegram** | `channels/telegram/` | Inbound: long-poll getUpdates → POST to Core `/inbound` → send reply. | `channels/telegram/.env` (TELEGRAM_BOT_TOKEN, CORE_URL); user.yml: `telegram_<chat_id>`. |
| **Discord** | `channels/discord/` | Inbound: bot on_message → POST to Core `/inbound` → reply in channel. | `channels/discord/.env` (DISCORD_BOT_TOKEN, CORE_URL); user.yml: `discord_<user_id>`. |
| **Slack** | `channels/slack/` | Inbound: Socket Mode events → POST to Core `/inbound` → post reply. | `channels/slack/.env` (SLACK_APP_TOKEN, SLACK_BOT_TOKEN, CORE_URL); user.yml: `slack_<user_id>`. |
| **WebChat** | (e.g. channels/webchat/) | Web UI; connects to Core WebSocket `/ws` or HTTP; user_id from session. | CORE_URL; user.yml allowlist. |
| **Google Chat** | `channels/google_chat/` | Inbound: bot events → POST to Core `/inbound` → reply. | channels/.env; user.yml. |
| **Signal** | `channels/signal/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **iMessage** | `channels/imessage/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **Teams** | `channels/teams/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **Zalo** | `channels/zalo/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **Feishu** | `channels/feishu/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **DingTalk** | `channels/dingtalk/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **BlueBubbles** | `channels/bluebubbles/` | Inbound → Core `/inbound` → reply. | channels/.env; user.yml. |
| **CLI** | `main.py` | In-process “channel”: user types in terminal; `Channel` builds `PromptRequest` and calls Core **POST /local_chat** (sync); reply is returned in HTTP body and printed. Core runs in a background thread. | No separate config; uses same Core. Prefixes `+` / `?` for memory store/retrieve. **Onboarding**: `python main.py onboard` (wizard), `python main.py doctor` (config + LLM connectivity). |

**Run any channel**: From repo root, `python -m channels.run <name>` (e.g. `telegram`, `discord`, `slack`, `webhook`, `whatsapp`, `matrix`, `wechat`, `tinode`). Each channel is a separate process; run multiple channels in separate terminals. See `channels/README.md`.

#### 3.2.3 New channels: Webhook (HTTP relay) and WebSocket

These allow **new bots or our own client** to connect **without** implementing a full `BaseChannel` process.

**1. Core `POST /inbound` (minimal HTTP API)**

- **Endpoint**: `POST http://<core_host>:<core_port>/inbound`
- **Request body** (JSON): `{ "user_id": "<id>", "text": "<message>", "channel_name?": "telegram", "user_name?": "Alice" }`
- **Response**: `{ "text": "<reply>" }` (sync). Permission: `user_id` must be allowed in `config/user.yml` (e.g. under `im` with `IM` permission).
- **Use case**: Any external bot (Telegram, Discord, Slack, n8n, etc.) can POST here and get a reply. No channel process in HomeClaw; the “channel” is the external bot that forwards messages to this URL.

**2. Webhook channel** (`channels/webhook/`)

- **Role**: HTTP relay when the Core is not directly reachable (e.g. Core on home LAN; webhook on a public host or Tailscale).
- **Endpoint**: `POST http://<webhook_host>:8005/message` — same JSON body as Core `/inbound`. The webhook forwards to `http://<core_host>:<core_port>/inbound` and returns the same `{ "text": "..." }`.
- **Run**: `python -m channels.webhook.channel` (reads `core_host`, `core_port` from `channels/.env`).
- **Use case**: External bots point at the webhook URL instead of the Core; one relay process for many bots.

**3. Core WebSocket `/ws`**

- **Endpoint**: `ws://<core_host>:<core_port>/ws`
- **Protocol**: Client sends JSON `{ "user_id": "...", "text": "..." }`; Core responds with `{ "text": "...", "error": "..." }`. Same permission as `/inbound`.
- **Use case**: **Our own client** (e.g. a future WebChat UI or dedicated app) that keeps one persistent connection. Enables future streaming or push without polling.

Summary:

| Channel type | Entry point | Response path | Typical use |
|--------------|-------------|---------------|-------------|
| **Webhook (HTTP)** | Core `POST /inbound` or Webhook `POST /message` | Sync in same response | Any bot (Telegram, Discord, etc.) |
| **WebSocket** | Core `WebSocket /ws` | Sync per message over same connection | Our own WebChat or app |

#### 3.2.4 Adding a new bot (minimal vs full channel)

- **Minimal (recommended for new bots)**: Implement a small script that (1) receives messages from your platform (Telegram, Discord, …), (2) POSTs `{ "user_id", "text", "channel_name" }` to Core `/inbound` (or to the Webhook `/message`), (3) sends the returned `text` back. Add `user_id` to `config/user.yml`. Ready-made channels in `channels/telegram/`, `channels/discord/`, `channels/slack/`; run with `python -m channels.run <name>`.
- **Full channel**: When you need async delivery or a dedicated process that owns the IM connection and must implement `/get_response`, add a new folder under `channels/` with a `BaseChannel` subclass and config; register with Core on startup.

### 3.3 LLM Layer (`llm/`)

- **Role**: Unify local and cloud LLMs behind one OpenAI-compatible API used by Core.
- **Config**: `config/core.yml` holds everything: `llama_cpp` settings, `local_models` (array), `cloud_models` (array), and selected `main_llm` / `embedding_llm` (by id). Each model has its own host/port for distributed mode.

**Local (llama.cpp)**:

- `llm/llmService.py`: **LLMServiceManager** (singleton) starts:
  - **Embedding model**: one llama-server process with embedding/pooling options (e.g. BGE), used for RAG.
  - **Main model**: one llama-server process for chat (and plugin selection, etc.).
- Command line and ports come from `core.yml` (`local_models` / `cloud_models`; each entry has `host`, `port`, `path`). Binary: auto-selected from `llama.cpp-master/<platform>/`. See `llama.cpp-master/README.md`.

**Cloud (LiteLLM)**:

- `llm/litellmService.py`: **LiteLLMService** exposes FastAPI routes (`/v1/chat/completions`, etc.) and forwards to LiteLLM (`litellm.acompletion`, etc.). API keys: each **cloud_models** entry has **`api_key_name`** (e.g. OPENAI_API_KEY); set the **environment variable** with that name where Core runs. Do not put API keys in core.yml in version control.
- When `main_llm_type` is `litellm`, Core’s chat completion still calls `http://main_llm_host:main_llm_port/v1/chat/completions` — that request is served by LiteLLMService, which can target OpenAI, Anthropic, Gemini, etc.

So: **one URL per role** (main vs embedding); local = llama-server, cloud = LiteLLM. Multi-model: define multiple entries in `core.yml` under `local_models` and `cloud_models` (each with its own host/port); set `main_llm` / `embedding_llm` by id. Run multiple llama-server processes for different local models if needed.

### 3.4 Memory (`memory/`)

- **Role**: Chat history + RAG (store and retrieve relevant past content for the current query).
- **Design**: **Relational + vector + graph**. **Cognee (default)**: SQLite + ChromaDB + Kuzu by default; supports Postgres, Qdrant/LanceDB/PGVector, Neo4j via Cognee `.env`. **In-house (chroma)**: SQLite + Chroma + optional Kuzu/Neo4j via `core.yml`; enterprise: Postgres, Qdrant, etc. See **docs_design/MemoryAndDatabase.md** (detailed support matrix), **docs_design/MemoryUpgradePlan.md**, **docs_design/MemoryCogneeEvaluation.md**.

**Backends** (`config/core.yml`):

- **memory_backend**: `cognee` (default; Cognee engine) | `chroma` (in-house RAG). When `cognee`, Core uses `CogneeMemory`; configure via **`cognee:`** in core.yml and/or Cognee `.env`. When `chroma`, **vectorDB** and **graphDB** in core.yml are used; when cognee, they are **not** used for memory (Cognee uses its own stores).
- **database**: `sqlite` | `postgresql` — always used for **Core’s** chat sessions, runs, turns. When memory_backend is chroma, in-house memory may also use it.
- **vectorDB** and **graphDB**: Used **only when memory_backend: chroma**. vectorDB.backend: `chroma` | qdrant | milvus | pinecone | weaviate. graphDB.backend: `kuzu` | neo4j — optional. See docs_design/MemoryAndDatabase.md.
- **profile** (optional): Per-user JSON store; `profile.enabled`, `profile.dir` (default database/profiles). Injected as “About the user” in prompt. See docs_design/UserProfileDesign.md.
- **knowledge_base** (optional): Separate from RAG memory; user documents/sources; `knowledge_base.enabled`, `knowledge_base.backend` (auto | cognee | chroma). See core.yml and docs_design/MemoryAndDatabase.md.

**Components**:

- **SQLite** (`memory/storage.py`, `memory/database/`): Chat sessions, runs, message history; memory change history (add/update/delete) for the in-house backend.
- **Chroma** (`memory/chroma.py`) or other vector store: Implements `VectorStoreBase`; used by `Memory` for similarity search. Factory: `memory/vector_store_factory.py`.
- **Graph** (`memory/graph/`): `GraphStoreBase`, `KuzuStore` (file-based), `Neo4jStore` (enterprise), `NullGraphStore` (no-op). Optional: `pip install kuzu` or `neo4j`. Used for entity/relation storage and graph-aware search expansion.
- **Memory class** (`memory/mem.py`): Implements `MemoryBase`: `add()` (embed + Chroma + SQLite history; when graph enabled, LLM extracts entities/relations → graph), `search()` (vector search + optional graph expansion: 1-hop related memories). Used by Core for RAG in `answer_from_memory` and for background memory ingestion from `memory_queue`.
- **CogneeMemory** (`memory/cognee_adapter.py`): Implements `MemoryBase` using Cognee (add → cognify, search). Dataset scope: `(user_id, agent_id)` → dataset name. Used when `memory_backend=cognee`.
- **Embedding**: `memory/embedding.py` (e.g. LlamaCppEmbedding) calls the embedding model’s HTTP API (main or dedicated embedding model per config).

**Flow**:

- Incoming user message is optionally queued to `memory_queue`; worker adds it to Memory (vector + metadata; if graph enabled, entity/relation extraction → graph).
- When generating a reply, Core calls `_fetch_relevant_memories()` (vector search + optional graph-expanded related memories) and injects them into the system prompt / context, then calls the main LLM.

**Workspace bootstrap (optional)** — see `Comparison.md` §7.4:

- **Role**: Inject identity and capabilities into the system prompt (who the assistant is, what it can do), separate from RAG (what to remember).
- **Location**: `config/workspace/` with optional markdown files: **IDENTITY.md** (tone, voice), **AGENTS.md** (behavior / routing hints), **TOOLS.md** (plugins / capabilities description).
- **Loader**: `base/workspace.py` — `load_workspace()`, `build_workspace_system_prefix()`. Core prepends this block to the system prompt in `answer_from_memory` when `use_workspace_bootstrap` is true in `core.yml`.
- **Config**: `core.yml` → `use_workspace_bootstrap: true` (default). Set to `false` to disable.
- **Switching agents (e.g. day vs night)**: `core.yml` → `workspace_dir: config/workspace` (default). Use different dirs (e.g. `config/workspace_day`, `config/workspace_night`) and set `workspace_dir` to the one you want; Core loads that workspace per request. To switch by time without restart, change `workspace_dir` via a cron/script or add a small schedule (e.g. 08:00–20:00 → `config/workspace_day`, else → `config/workspace_night`) in config and resolve it at request time.

**Multi-agent: two paths.**

- **Path 1 — Single Core, switch workspace (by config or time).** One HomeClaw instance. Use different workspace dirs (e.g. `config/workspace_day`, `config/workspace_night`) and set `workspace_dir` in `core.yml` to the one you want; Core loads that workspace per request. Switch by editing config and restarting, or by a cron/script that updates config, or add a schedule in config and resolve `workspace_dir` at request time (e.g. 08:00–20:00 → day, else → night). One agent active at a time; no in-process agent registry.
- **Path 2 — Multiple HomeClaw instances.** Run two or more Core processes, each with its own `config/` (and thus its own `workspace_dir`, `main_llm`, memory/Chroma, sessions). Each instance is one agent (one identity, one workspace, one memory). Multi-agent at the system level; coordination is external (load balancer, gateway, or client choosing which instance to call). No shared state between instances unless you build it (e.g. shared DB).

**Session transcript (first-class artifact)**:

- **Role**: Expose chat history as a linear transcript per session for debugging, export, or future use in the prompt (e.g. “recent transcript” block). Transcript may be exported as JSONL, pruned (keep last N turns), or summarized via LLM (see Comparison.md §7.6).
- **API**:
  - `ChatHistory.get_transcript(app_id, user_name, user_id, session_id, limit, fetch_all)` returns a list of `{ "role": "user"|"assistant", "content": str, "timestamp": str }` in chronological order. Core exposes `get_session_transcript(...)` that delegates to `chatDB.get_transcript(...)`.
  - **JSONL**: `ChatHistory.get_transcript_jsonl(...)` returns the same transcript as one JSON object per line. Core: `get_session_transcript_jsonl(...)`.
  - **Pruning**: `ChatHistory.prune_session(app_id, user_name, user_id, session_id, keep_last_n)` deletes older turns for that session, keeping only the last `keep_last_n` turns; returns number deleted. Core: `prune_session_transcript(...)`.
  - **Summarization**: `Core.summarize_session_transcript(app_id, user_name, user_id, session_id, limit=50)` (async) fetches transcript, formats as text, calls the main LLM to produce a short summary; returns the summary string.

**Last channel store (for send_response_to_latest_channel and channel_send)**:

- **Role**: Persist which channel last sent a request so follow-up messages (e.g. from **channel_send** or plugins) can be delivered to the right place after restart or when in-memory is missing.
- **Implementation**: `base/last_channel.py` — **save_last_channel** (on every incoming request) and **get_last_channel** (when sending). Persists to **SQLite** (`homeclaw_last_channel` table via `memory/database/models.py`) and an **atomic file** (`database/latest_channel.json` — write to `.tmp` then rename). Core calls `_persist_last_channel(request)` wherever it sets `latestPromptRequest`; `send_response_to_latest_channel` uses in-memory first, then **get_last_channel()** (DB then file fallback).

### 3.5 Plugins (`plugins/`)

- **Role**: Feature-specific handlers when Core decides not to answer with generic chat + RAG. Model can call **route_to_plugin** (when use_tools and orchestrator_unified_with_tools) or orchestrator selects plugin by intent.

**Built-in vs external plugins**

| Type | Language | Where it runs | Manifest | When to use |
|------|----------|---------------|----------|-------------|
| **Built-in** | Python only | In-process with Core | `plugin.yaml` with **type: inline**, `config.yml`, `plugin.py` (subclass `BasePlugin`) under `plugins/<Name>/` | Fast integration, no extra process, use Python libs (e.g. Weather, News, Mail). |
| **External** | Any (Node.js, Go, Java, etc.) | Separate process or remote HTTP service | `plugin.yaml` with **type: http** in a folder under `plugins/`, or register via **POST /api/plugins/register** | Existing service, different language, or independent deployment; server accepts POST with `PluginRequest` and returns `PluginResult`. |

Core discovers **built-in** plugins by scanning `plugins/` and loading plugin.yaml + plugin.py; **external** plugins are either declared in a folder (plugin.yaml with type: http + endpoint URL) or registered at runtime via the API. Both are routed the same way (orchestrator or route_to_plugin). See **docs_design/PluginsGuide.md** (§2 Built-in, §3 External), **docs_design/PluginStandard.md**, **docs_design/RunAndTestPlugins.md**.

- **Manifest**: **plugin.yaml** (id, name, description, **type: inline** for built-in or **type: http** for external, capabilities with parameters). **config.yml** for runtime config (API keys, defaults). **plugin.py** (built-in only) — class extending `BasePlugin`, implements `run()` and/or capability methods.
- **Base**: `base/BasePlugin.py` — `BasePlugin(coreInst)` (built-in plugins), with `description`, `config`, `user_input`, `promptRequest`, `run()`, `check_best_plugin()`.
- **Loading**: `base/PluginManager.py` scans `plugins/` directories, loads **plugin.yaml** (and plugin.py for type: inline), registers descriptions; Core uses an LLM to match user text to a plugin (or **route_to_plugin** tool) and invokes `plugin.run()` (built-in) or HTTP POST (external).
- **Example (built-in)**: `plugins/Weather/` — plugin.yaml (type: inline), config.yml, plugin.py; uses config (e.g. city, API key), fetches weather, then `await self.coreInst.send_response_to_latest_channel(response=...)`.
- **Example (external)**: Run an HTTP server that accepts POST with `PluginRequest` and returns `PluginResult`; put a folder under `plugins/` with plugin.yaml (type: http, endpoint URL) or call **POST /api/plugins/register**. Core forwards requests to that endpoint like built-in plugins.

Plugins get the same `CoreInterface` (chat completion, send response, memory, session/run IDs) so built-in plugins can use the same LLM and channels; external plugins receive the same contract (PluginRequest/PluginResult) over HTTP.

### 3.6 Plugins vs tools: difference and design

This subsection clarifies the **difference** between HomeClaw’s **plugins** and **callable tools**, and describes the **implemented** tool layer (exec, browser, cron, sessions_*, memory_*, file_*, run_skill, route_to_plugin, etc.). Nodes/canvas remain out of scope; see **docs_design/ToolsSkillsPlugins.md** and **Comparison.md** §7.10.2. 
#### Difference: plugin vs tool

| Aspect | HomeClaw plugin | Tool (model-invoked) |
|--------|-------------------|---------------|
| **What it is** | A **handler** for a class of user intents: “do one thing and return the response.” | A **callable** the model invokes by name with **structured arguments** (e.g. `exec` with `{ "command": "ls" }`). |
| **How the model uses it** | **Routing**: An LLM (orchestrator) reads user text + plugin **descriptions** and picks **one** plugin for this message. No structured args. | **Function calling**: The chat LLM receives **tool definitions** (name, description, parameters schema). The model outputs **tool_calls** (tool name + JSON args); gateway executes and returns results; model can call again or reply. |
| **Invocation** | `plugin.run()` — plugin gets `user_input` (raw text) and `promptRequest`; it does its work and calls `send_response_to_latest_channel(response)`. | Execute tool by name with parsed args; return result (e.g. stdout, JSON); append to conversation; model may issue more tool_calls or a final text reply. |
| **Granularity** | **One plugin per turn**; each plugin is a “feature” (Weather, News, Quotes). | **Multiple tools per turn**; tools are small (one command, one browser action, one session send). |
| **Discovery** | Plugin **descriptions** (free text) in a prompt; LLM picks best match. | **TOOLS.md** (human-readable) + **tool schemas** (OpenAI/Anthropic function-calling format) passed to the LLM API. |
| **Typical use** | “Answer about weather,” “get news,” “send a quote” — single-shot feature. | “Run this command,” “open this URL,” “send this to session X” — composable actions the model chooses and parameterizes. |

So: **Plugin** = “route this message to one handler that does a thing and returns.” **Tool** = “model calls named functions with structured arguments; we execute and feed back; model can chain or reply.” To support tool layer “work,” we need a **tool layer** (callable by the model with args), not only plugin routing.

#### Reference capabilities (tool layer)

- **exec**: Run shell commands (often sandboxed).
- **browser**: Drive a browser (navigate, click, etc.).
- **canvas**: Drawing/UI surface.
- **nodes**: Device/sidecar (camera, screen, location, system.run/notify); exec can run on gateway or node.
- **cron**: Scheduled tasks.
- **webhooks**: In/out webhooks.
- **sessions_***: List sessions, get history (transcript), send to another session (agent-to-agent).

All of the above except **canvas** and **nodes** are implemented as first-class callable tools when `use_tools: true`. Canvas and nodes remain out of scope (see Comparison.md §7.10.2).

#### Proposed design: tool layer alongside plugins

**Goal**: Keep existing **plugins** for “do one thing and return” (Weather, News, etc.), and add a **tool layer** so the model can call **tools** by name with arguments (tool layer). Optionally, plugins can **expose tools** (one plugin → one or more tools with schemas).

1. **Tool registry**
   - **Central registry** of tools: each tool has `name`, `description`, **parameters schema** (JSON Schema / OpenAI `function` format), and an **executor** (async function or callable that takes (args, context) and returns a result string or structured value).
   - **Context** passed to executor: `coreInst`, `request` (PromptRequest or equivalent), `session_id`, `user_id`, etc., so tools can send responses, read transcript, call LLM.

2. **Tool schemas for the LLM**
   - Build a list of tool definitions in the format expected by the chat API (e.g. OpenAI `tools: [{ type: "function", function: { name, description, parameters } }]`).
   - Source: (a) **Built-in tools** (exec, browser, nodes, cron, webhooks, sessions_*) implemented in Core or a `tools/` module. (b) **Plugin-exposed tools**: optional interface on `BasePlugin`, e.g. `get_tools() -> list[dict]` and `run_tool(name, args) -> str`; PluginManager registers those with the central registry.
   - `config/workspace/TOOLS.md` stays the **human-readable** description for the system prompt; the **machine** uses the registry’s schemas for the API.

3. **Chat flow with tools**
   - When **tools are enabled** (config or feature flag): in the path that generates the reply (e.g. `answer_from_memory` or a variant), call `openai_chat_completion(messages, tools=..., tool_choice="auto")`. If the response contains **tool_calls**, for each call: resolve tool by name → run executor with args and context → append tool result to `messages` (assistant message with tool_calls, then tool results). **Loop** until the model returns a message without tool_calls (final text reply). Then save the turn to chat and send the final reply to the user.
   - When **tools are disabled**: keep current behavior (RAG + chat only, or orchestrator → plugin as today).

4. **Built-in tool implementations (roadmap)**
   - **exec**: Sandboxed subprocess (allowlist of commands or safe interpreter); return stdout/stderr. Config: `allowed_commands`, `cwd`, `timeout`, optional Docker/sandbox.
   - **browser**: Integrate a browser automation library (e.g. Playwright); tool args: `action`, `url`, `selector`, etc.; return screenshot or text. Optional plugin or core module.
   - **nodes**: Adapter to talk to “nodes” (devices) if we add a node protocol or bridge; tools: `node_run`, `node_notify`, etc. Can be a thin adapter that forwards to external node services.
   - **cron**: Schedule a task (store in DB or use system cron); tool: `schedule_cron(expr, action, payload)`. May reuse or extend TAM/scheduler.
   - **webhooks**: `webhook_trigger(url, payload)`; optional `webhook_register` for inbound. Can be a small core module or plugin.
   - **sessions_***: We already have transcript and chat; add tools: `sessions_list`, `sessions_transcript(session_id)`, `sessions_send(session_id, message)` that call Core/chat APIs and return results. These are thin wrappers over existing APIs.

5. **Safety and config**
   - **exec**: Mandatory allowlist or sandbox; no arbitrary shell by default. Config in **`core.yml`** under **`tools:`**: `exec_allowlist`, `exec_timeout`. File tools: `file_read_base`, `file_read_max_chars`. Web: `tools.web.search` (provider, API keys, fallback_no_key). Browser: `browser_enabled`, `browser_headless`. **run_skill**: `run_skill_allowlist`, `run_skill_timeout`. See core.yml and **docs_design/ToolsDesign.md**.
   - **Permissions**: Tool execution can be gated by `user_id` / channel (e.g. only certain users can call exec). Reuse or extend `user.yml` / permission layer.
   - **Rate limits**: Optional per-user or per-session limits on tool calls to avoid abuse.

6. **Plugins as tool providers (optional)**
   - Extend `BasePlugin` with optional `get_tools() -> list[dict]` and `run_tool(name: str, args: dict) -> str`. PluginManager, when loading plugins, can register these into the central tool registry. Then the **same** plugin can still be used the old way (orchestrator picks it by description and calls `run()`) or as a set of tools the model calls by name with args. Example: a “Weather” plugin could expose a tool `get_weather(city: string)` so the model can call it with a city; the plugin’s `run_tool("get_weather", {"city": "Beijing"})` runs and returns the result.

**Summary**

- **Plugin** (current): “Route message → one handler → run() → return response.” Good for feature bundles (Weather, News).
- **Tool** (tool layer): “Model calls named tools with structured args; we execute and loop until model replies.” Good for exec, browser, nodes, sessions_*, etc.
- **Design**: Add a **tool registry** and **tool-aware chat flow** (tools in LLM API, execute tool_calls, append results, loop). Implement **built-in tools** (exec, browser, nodes, cron, webhooks, sessions_*) with safety and config. Optionally let **plugins expose tools** so existing plugins can participate in the tool layer. This gives HomeClaw the ability to “do all the things a full tool layer” while keeping the current plugin design and RAG+transcript memory.

#### Implementation (step by step) and how to extend

**Implemented**  
- **`base/tools.py`**: `ToolDefinition` (name, description, parameters schema, `execute_async`), `ToolContext` (core, app_id, user_name, user_id, session_id, run_id, request), `ToolRegistry` (register, get_openai_tools, execute_async), `get_tool_registry()`.  
- **`tools/builtin.py`**: Built-in tools; `register_builtin_tools(registry)` called from Core at startup. **Tools included**: `sessions_transcript`, `sessions_list`, `sessions_send`, `sessions_spawn`, `session_status`; `time`, `echo`, `platform_info`, `cwd`, `env`; `exec` (allowlist in config; background for job_id); `process_list`, `process_poll`, `process_kill`; `file_read`, `file_write`, `file_edit`, `apply_patch`, `folder_list`, `file_find`, **document_read** (PDF, Word, etc. via Unstructured); `fetch_url`, **web_search** (provider + API keys in config), **web_search_browser** (Google/Bing/Baidu when Playwright available); **full browser** (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`) with request-scoped Playwright; `webhook_trigger`, **http_request** (GET/POST/PUT/PATCH/DELETE); **memory_search**, **memory_get** (when use_memory); **cron_schedule**, **cron_list**, **cron_remove**; **remind_me**, **record_date**, **recorded_events_list** (TAM one-shot and recorded events); **run_skill** (script from skill’s scripts/ with allowlist); **route_to_plugin**, **route_to_tam**; **save_result_page** (result viewer); **models_list**, **agents_list**; **channel_send** (send to last-used channel); **image** (vision/multimodal); **profile_get**, **profile_update**, **profile_list** (per-user profile when profile.enabled); **knowledge_base_search**, **knowledge_base_add**, **knowledge_base_remove**, **knowledge_base_list** (when knowledge_base.enabled); **tavily_extract**, **tavily_crawl**, **tavily_research** (Tavily API when configured); **web_extract**, **web_crawl**. File/folder use `tools.file_read_base`. Requires **Playwright** for browser (`pip install playwright && playwright install chromium`). See **docs_design/ToolsDesign.md**, **docs_design/ToolsAndSkillsTesting.md**.  
- **Core**: In `initialize()`, `register_builtin_tools(get_tool_registry())`. In `answer_from_memory`, when `use_tools` is true and the registry has tools, use `Util().openai_chat_completion_message` with tools and run the tool loop (execute tool_calls, append results, repeat until the model returns text).  
- **Config**: `core.yml` → **`use_tools: true`** to enable. **`tools:`** section: `exec_allowlist`, `exec_timeout`, `file_read_base`, `file_read_max_chars`, `tools.web` (search provider, API keys), `browser_enabled`, `browser_headless`, `run_skill_allowlist`, `run_skill_timeout`, `tool_timeout_seconds`. `CoreMetadata.use_tools` in `base/base.py`. See **docs_design/ToolsDesign.md**, **docs_design/ToolsAndSkillsTesting.md**.

**How to add a new tool (keep it clear and simple)**  
1. **Define an executor**: `async def my_tool_executor(arguments: dict, context: ToolContext) -> str:` — use `context.core`, `context.user_id`, etc.; return a string result.  
2. **Create a `ToolDefinition`**: `ToolDefinition(name="my_tool", description="...", parameters={"type": "object", "properties": {...}, "required": [...]}, execute_async=my_tool_executor)`.  
3. **Register it**: Either in `tools/builtin.py` inside `register_builtin_tools(registry)` (for built-ins), or elsewhere with `get_tool_registry().register(tool)` (for plugins or app code).  
No inheritance or extra classes needed; the registry is the single extension point.

**Adding more tools later**  
- **Built-in**: Add the tool in `tools/builtin.py` and register it in `register_builtin_tools`.  
- **From a plugin**: (Optional) Implement `get_tools()` and `run_tool(name, args)` on the plugin; have PluginManager register those with the registry when the plugin loads.  
- **From config**: (Future) A YAML list of tool names or paths that get loaded and registered at startup.

---

## 4. End-to-End Workflow

### 4.1 User sends a message (e.g. from phone via Email or IM)

1. **Channel** receives the message (e.g. new email or IM event).
2. Channel builds a **PromptRequest** (request_id, channel_name, user_id, contentType, text, action, host/port for callback, etc.).
3. Channel calls Core **POST /process** (or **POST /local_chat** for CLI).
4. Core checks **permission** (user_id / channel type in `user.yml`).
5. **If orchestrator + plugins enabled**:  
   - Orchestrator → Intent (TIME/OTHER).  
   - If OTHER → select plugin by LLM; if selected → run plugin → plugin sends response via Core → Core pushes to **response_queue** → **process_response_queue** POSTs to channel’s **/get_response** → channel delivers to user.
6. **If Core handles it**:  
   - Get session/run IDs; load recent **chat history** from SQLite.  
   - Optionally put request in **memory_queue** (async add to RAG).  
   - **answer_from_memory**: fetch relevant memories (Cognee or Chroma), build messages with context, call **openai_chat_completion** (main LLM; when use_tools, run tool loop for tool_calls), save turn to chat DB.  
   - Push **AsyncResponse** to response_queue → same delivery path to channel → user sees reply.

### 4.2 Local CLI (`main.py`)

1. User runs `main.py` and types in the console.
2. Core runs in a background thread; CLI is a channel that does not start its own HTTP server for incoming Core callbacks; it uses **local_chat** (sync): same Core logic, response returned in HTTP body and printed in console.
3. Prefixes like `+` / `?` can map to store/retrieve actions for memory in the same flow.

---

## 5. Configuration Summary

| File | Purpose |
|------|--------|
| `config/core.yml` | **Single config** for Core: host/port, **model_path**, **local_models** (array: id, path, host, port, capabilities), **cloud_models** (array: id, path, host, port, **api_key_name** → set env var), **main_llm** / **embedding_llm** (refs: local_models/<id> or cloud_models/<id>). **memory_backend** (cognee default \| chroma), **cognee:** (when cognee), database, vectorDB, graphDB (when chroma). **use_memory**, **use_workspace_bootstrap**, **workspace_dir**. **use_tools**, **tools:** (exec_allowlist, file_read_base, web, browser_*, run_skill_*, etc.). **use_skills**, **skills_dir**, **skills_use_vector_search**, etc. **profile** (enabled, dir). **knowledge_base**. **result_viewer** (enabled, port, base_url). **auth_enabled**, **auth_api_key**. Prompts, TAM, orchestrator_unified_with_tools. See HOW_TO_USE.md. |
| `config/user.yml` | Allowlist: users (id, name, email, im, phone, permissions). All chat/memory/profile keyed by system user id. |
| `config/email_account.yml` | IMAP/SMTP and credentials for the email channel. |
| `channels/.env` | CORE_URL (e.g. http://127.0.0.1:9000), channel bot tokens (TELEGRAM_BOT_TOKEN, etc.). |

Core reads **main_llm** / **embedding_llm** (id) from `core.yml` and resolves host/port and type from **local_models** or **cloud_models**. Local model **path** is relative to **model_path**. Llama.cpp server binary is placed in **llama.cpp-master/** subfolder for the platform (mac/, win_cuda/, linux_cpu/, etc.); see llama.cpp-master/README.md. Cloud API keys: set the **environment variable** matching each cloud model’s **api_key_name** (e.g. OPENAI_API_KEY).

---

## 6. Extension Points and Future Work

- **Channels**: Two options. (1) **Minimal**: Any bot can POST to Core `/inbound` (or Webhook `/message`) with `{ user_id, text }` and get `{ text }`; add user_id to user.yml. Ready-made: `channels/telegram/`, `channels/discord/`, `channels/slack/`; run with `python -m channels.run <name>`. (2) **Full**: New folder under `channels/` with `BaseChannel` subclass and config; register with Core, implement `/get_response` for async delivery. A **dedicated HomeClaw app** can use WebSocket `/ws` for a persistent connection.
- **LLM**: Add entries in `core.yml` under `local_models` or `cloud_models`; for local, llama-server is started per main/embedding model (LLMServiceManager); multiple processes for multiple models are supported via host/port per entry).
- **Memory/RAG**: **Default**: Cognee — SQLite + ChromaDB + Kuzu (Cognee defaults); Postgres, enterprise vector DBs, Neo4j via Cognee `.env`. **Alternative**: in-house RAG — `memory_backend: chroma` with SQLite/Chroma/optional graph (kuzu \| neo4j) via `core.yml`. See **docs_design/MemoryAndDatabase.md** (support matrix), **docs_design/MemoryUpgradePlan.md**, **docs_design/MemoryCogneeEvaluation.md**.
- **Plugins**: Add a folder under `plugins/` with **plugin.yaml** (manifest: id, description, capabilities), **config.yml**, and **plugin.py** (BasePlugin subclass, run() or capability methods). PluginManager loads plugins; routing: **orchestrator_unified_with_tools** in `core.yml` (default true = main LLM with **route_to_plugin** tool; false = separate orchestrator LLM call). External HTTP plugins: plugin.yaml with type: http or POST /api/plugins/register. See **docs_design/PluginsGuide.md**, **docs_design/PluginStandard.md**, **docs_design/RunAndTestPlugins.md**.
- **Tool layer**: See §3.6. Add a central **tool registry**, tool schemas for the LLM, and a **tool-aware chat flow** (execute tool_calls, append results, loop). Implement built-in tools: exec (sandboxed), browser, nodes adapter, cron, webhooks, sessions_*. Optionally let plugins expose tools via `get_tools()` / `run_tool()`. This gives “do things” (exec, browser, devices) while keeping plugins for feature bundles.
- **Skills (SKILL.md format)**: **Implemented**: `base/skills.py` loads **SKILL.md** (name, description, body) from **skills/** (or `skills_dir` in core.yml). When **use_skills: true**, Core injects an “Available skills” block into the system prompt. **skills_use_vector_search: true** (optional) retrieves skills by similarity to the query (separate Chroma collection). **run_skill** tool executes scripts from a skill’s `scripts/` folder (allowlist in `tools.run_skill_allowlist`). Add skill folders under `skills/` with a SKILL.md each; reuse format from OpenClaw/ClawHub. See **docs_design/SkillsGuide.md**, **docs_design/ToolsSkillsPlugins.md**.
- **TAM**: Time intents are already classified; TAM can be extended to more scheduling/reminder actions and integrations.

---

## 7. Key Files Quick Reference

| Area | Key files |
|------|-----------|
| Core | `core/core.py`, `core/coreInterface.py`, `core/orchestrator.py`, `core/tam.py` |
| Channels | `base/BaseChannel.py`, `base/base.py` (InboundRequest), `channels/` (webhook, telegram, discord, slack, whatsapp, matrix, wechat, tinode), `main.py` (CLI). Run any channel: `python -m channels.run <name>`. |
| LLM | `llm/llmService.py`, `llm/litellmService.py` |
| Memory | `memory/base.py`, `memory/mem.py`, `memory/chroma.py`, `memory/storage.py`, `memory/embedding.py`, `memory/chat/chat.py` (ChatHistory, get_transcript). **Graph**: `memory/graph/` (when memory_backend=chroma). **Cognee**: `memory/cognee_adapter.py` (default when memory_backend=cognee). **Profile**: `base/profile_store.py`, database/profiles/. **Knowledge base**: see core.yml knowledge_base, docs_design/MemoryAndDatabase.md. Workspace bootstrap: `base/workspace.py`, `config/workspace/` (IDENTITY.md, AGENTS.md, TOOLS.md). Skills: `base/skills.py`, `skills/` (SKILL.md per folder); `use_skills`, `skills_dir`, `skills_use_vector_search`; run_skill in tools/builtin.py. See **docs_design/MemoryAndDatabase.md**, **docs_design/SkillsGuide.md**. |
| Tools | `base/tools.py` (ToolRegistry, ToolContext), `tools/builtin.py` (register_builtin_tools). Config: core.yml `tools:` (exec_allowlist, file_read_base, web, browser_*, run_skill_*, etc.). See **docs_design/ToolsDesign.md**, **docs_design/ToolsAndSkillsTesting.md**. |
| Plugins | `base/BasePlugin.py`, `base/PluginManager.py`, `plugins/Weather/` (plugin.yaml, config.yml, plugin.py). External: POST /api/plugins/register. See **docs_design/PluginsGuide.md**, **docs_design/PluginStandard.md**. |
| Shared | `base/base.py` (PromptRequest, AsyncResponse, enums, config dataclasses), `base/util.py` (config, LLM calls, paths) |

---

This Design.md reflects the current codebase and is intended as the base document for further development and refactoring of HomeClaw.
