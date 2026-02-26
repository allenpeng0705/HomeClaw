# core.yml — detailed introduction

**core.yml** is the main configuration file for HomeClaw Core. It lives in **`config/core.yml`** (relative to the project root). This page explains the main sections and what each setting means so you can tune Core for your setup.

---

## Overview

| Section | What it controls |
|--------|-------------------|
| **Server** | Where Core listens (host, port). |
| **Models** | Which LLM is used for chat and embedding (local and/or cloud); mix-mode routing. |
| **Memory** | RAG memory, agent memory files, daily memory, session lifecycle. |
| **Knowledge base** | User documents and URLs for RAG; file upload handling. |
| **Routing** | Mix mode: how Core chooses local vs cloud per request (heuristic, semantic, classifier). |
| **Skills & plugins** | Skills (SKILL.md), plugins (built-in + external), system plugins. |
| **Tools** | File read base, web search, browser, run_skill, exec allowlist, timeouts. |
| **Auth** | API key when Core is exposed (e.g. tunnel, remote app). |

---

## 1. Server

| Setting | Meaning |
|--------|--------|
| **`name`** | Core instance name (e.g. `core`). Used in logs and plugin registration. |
| **`host`** | Bind address. `0.0.0.0` = accept connections from any interface (e.g. LAN, tunnel). `127.0.0.1` = local only. |
| **`port`** | HTTP port Core listens on. Default **9000**. Clients (Companion app, WebChat, channels) use `http://<host>:9000`. |
| **`mode`** | Environment hint (e.g. `dev`, `prod`). Affects logging and optional behavior. |
| **`model_path`** | Base path for local model files (GGUF). Relative to project or absolute. Default `../models/`. |

---

## 2. Models

These settings define **which model** Core uses for chat (main LLM) and for embeddings (e.g. memory, knowledge base).

### Main and embedding model

| Setting | Meaning |
|--------|--------|
| **`main_llm`** | Single main model when not using mix mode: `local_models/<id>` or `cloud_models/<id>`. |
| **`main_llm_mode`** | `local` = always use local; `cloud` = always use cloud; **`mix`** = router picks **local** or **cloud** per request (see Routing below). |
| **`main_llm_local`** | When mode is `local` or `mix`: which local model to use (e.g. `local_models/main_vl_model_4B`). |
| **`main_llm_cloud`** | When mode is `cloud` or `mix`: which cloud model to use (e.g. `cloud_models/Gemini-2.5-Flash`). |
| **`embedding_llm`** | Model used for embeddings (RAG, knowledge base). Can be local or cloud (e.g. `local_models/embedding_text_model`). |
| **`main_llm_language`** | Preferred response languages (e.g. `[en, zh]`). First item is primary for prompts. |

### local_models

List of **local** models (llama.cpp servers). Each entry has:

- **`id`** — Unique id; you refer to it as `local_models/<id>` in `main_llm` / `embedding_llm`.
- **`path`** — GGUF file path relative to **`model_path`**.
- **`host`**, **`port`** — Where the llama.cpp server for this model runs.
- **`capabilities`** — `[Chat]` for chat, `[embedding]` for embedding, or both.
- **`mmproj`** — (Optional) Path to vision projector .gguf for image input.
- **`supported_media`** — (Optional) e.g. `[image]` for vision; default `[image]` when `mmproj` is set.

You run a separate llama.cpp server per model (or use Core’s built-in start). See [Models](models.md) and `llama.cpp-master/README.md`.

### cloud_models

List of **cloud** models (LiteLLM / provider APIs). Each entry has:

- **`id`** — Unique id; you refer to it as `cloud_models/<id>`.
- **`path`** — LiteLLM model name (e.g. `gemini/gemini-2.5-flash`, `openai/gpt-4o`).
- **`host`**, **`port`** — LiteLLM proxy (often same for all cloud models).
- **`api_key_name`** — Environment variable name for the API key (e.g. `GEMINI_API_KEY`).
- **`api_key`** — (Optional) Set the key here instead of env (convenience only; avoid committing secrets).
- **`supported_media`** — (Optional) e.g. `[image]` for vision-only models.

API key can be set via **environment variable** (recommended) or **`api_key`** in core.yml. See [Models](models.md).

### llama_cpp and completion

- **`llama_cpp`** — Defaults for **local** llama.cpp servers: `ctx_size` (context window), `predict` (max output tokens), `temp`, `threads`, `n_gpu_layers`, `repeat_penalty`, `function_calling`. Sub-key **`embedding`** for embedding-model-only overrides.
- **`completion`** — Parameters sent with **every** chat request: `max_tokens`, `temperature`, `top_p`, `repeat_penalty`, `image_max_dimension` (resize images for vision).

---

## 3. Routing (mix mode)

When **`main_llm_mode: mix`**, Core chooses **local** or **cloud** for each user message. These settings control how that choice is made.

| Setting | Meaning |
|--------|--------|
| **`hybrid_router.default_route`** | Fallback when no other rule applies: `local` or `cloud`. |
| **`hybrid_router.fallback_on_llm_error`** | If the chosen model fails (timeout/error), retry once with the other route. |
| **`hybrid_router.show_route_in_response`** | Include which route (local/cloud) was used in the reply (e.g. for tuning). |

### Layer 1: Heuristic rules

- **`hybrid_router.heuristic.enabled`** — Use keyword/simple rules (e.g. “translate” → cloud).
- **`hybrid_router.heuristic.threshold`** — Score threshold for heuristic match.
- **`hybrid_router.heuristic.rules_path`** — YAML file with rules (e.g. `config/hybrid/heuristic_rules.yml`).

### Layer 2: Semantic routes

- **`hybrid_router.semantic.enabled`** — Use semantic similarity to route (e.g. “complex coding” → cloud).
- **`hybrid_router.semantic.threshold`** — Similarity threshold.
- **`hybrid_router.semantic.routes_path`** — YAML with example phrases per route (e.g. `config/hybrid/semantic_routes.yml`).

### Layer 3: Classifier or perplexity

- **`hybrid_router.slm.enabled`** — Use a small model or perplexity probe to decide.
- **`hybrid_router.slm.mode`** — **`classifier`** = small model answers “Local or Cloud?”; **`perplexity`** = main local model confidence (logprobs) to decide.
- **`hybrid_router.slm.model`** — Local model id for classifier (e.g. `local_models/classifier_0_6b`).
- **`hybrid_router.slm.threshold`** — Score threshold for Layer 3.

Order: heuristic → semantic → Layer 3 → default_route. See [Mix mode and reports](mix-mode-and-reports.md).

---

## 4. Memory

These settings control **RAG memory** (vector + relational), **agent memory files**, and **session** lifecycle.

| Setting | Meaning |
|--------|--------|
| **`use_memory`** | Turn on/off RAG memory (search, store). |
| **`memory_backend`** | **`cognee`** (default) or **`chroma`**. Cognee uses its own DB; Chroma uses **`vectorDB`** and **`graphDB`** in core.yml. To clear memory, use **POST or GET** `http://<core_host>:<core_port>/memory/reset`. |

### Agent and daily memory (file-based)

| Setting | Meaning |
|--------|--------|
| **`use_agent_memory_file`** | Inject long-term context from **AGENT_MEMORY.md** (path set by `agent_memory_path` or `workspace_dir/AGENT_MEMORY.md`). |
| **`agent_memory_max_chars`** | Max characters to inject from that file; 0 = no limit. |
| **`use_agent_memory_search`** | If true, index agent memory and use **agent_memory_search** / **agent_memory_get** tools instead of injecting full file (recommended for large files). |
| **`use_daily_memory`** | Inject short-term context from daily files (e.g. `memory/YYYY-MM-DD.md` in `daily_memory_dir`). |
| **`daily_memory_dir`** | Directory for daily files; empty = `workspace_dir/memory`. |

### Session

| Setting | Meaning |
|--------|--------|
| **`session.dm_scope`** | How to isolate conversations: **`main`** = one shared session; **`per-peer`** = by sender id; **`per-channel-peer`** = by channel + sender; **`per-account-channel-peer`** = by account + channel + sender. |
| **`session.identity_links`** | Map one user id to several channel ids (e.g. same person on Telegram and Discord) so they share one session. |
| **`session.prune_keep_last_n`** | Keep at most this many turns per session when pruning. |
| **`session.prune_after_turn`** | If true, prune after each reply to avoid unbounded context. |
| **`session.daily_reset_at_hour`** | 0–23 = start a new session when last activity was before today at this hour; -1 = disabled. |
| **`session.idle_minutes`** | New session when last activity older than N minutes; -1 = disabled. |
| **`session.api_enabled`** | Expose **GET /api/sessions** for UIs. |

Reset memory via **POST/GET** `http://<core>:<port>/memory/reset`. See [Tools](tools.md) and design docs in the repo.

---

## 5. Knowledge base

User documents and URLs for RAG (separate from chat memory).

| Setting | Meaning |
|--------|--------|
| **`knowledge_base.enabled`** | Turn on/off knowledge base and tools (e.g. **knowledge_base_add**, retrieval). |
| **`knowledge_base.backend`** | **`auto`** = same as memory backend; **`cognee`** or **`chroma`** to override. |
| **`knowledge_base.collection_name`** | Chroma collection name when backend is chroma. |
| **`knowledge_base.chunk_size`**, **`chunk_overlap`** | How documents are split for embedding. |
| **`knowledge_base.unused_ttl_days`** | Remove sources not used for this many days (Cognee age-based; Chroma by last_used). |
| **`knowledge_base.retrieval_min_score`** | Min similarity (0–1) for retrieved chunks; null = no filter. |
| **`file_understanding.add_to_kb_max_chars`** | When user sends **only** file(s), auto-add to KB only if extracted text length ≤ this; 0 = never auto-add. |

Reset KB via **POST/GET** `http://<core>:<port>/knowledge_base/reset`.

---

## 6. Skills and plugins

| Setting | Meaning |
|--------|--------|
| **`use_skills`** | Enable skills (folders under **`skills_dir`** with SKILL.md). The model sees “Available skills” and can call **run_skill** or use tools per skill. |
| **`skills_dir`** | Directory for skill folders (default `skills` (project root)). |
| **`skills_use_vector_search`** | Retrieve skills by similarity to user query instead of loading all; reduces prompt size. |
| **`skills_similarity_threshold`** | Min score to keep a skill in the prompt. |
| **`skills_force_include_rules`** | When user query matches a pattern, always include listed skill folders (and optional instruction). |
| **`use_tools`** | Enable built-in tools (file_read, web_search, browser_*, run_skill, etc.). |
| **`plugins_max_in_prompt`** | When `plugins_use_vector_search=true`, max plugins in the routing block after RAG; when false (include all), not used. |
| **`plugins_use_vector_search`** | Retrieve plugins by similarity (like skills). |
| **`plugins_force_include_rules`** | When query matches, always include listed plugin ids. |
| **`system_plugins_auto_start`** | If true, Core starts plugins in **system_plugins/** (e.g. homeclaw-browser) and registers them. |
| **`system_plugins`** | Allowlist of plugin ids to auto-start; empty = all discovered. |
| **`system_plugins_env`** | Per-plugin env vars (e.g. `BROWSER_HEADLESS: "false"` for homeclaw-browser). |

See [Plugins](plugins.md), [Writing plugins and skills](writing-plugins-and-skills.md), [Tools](tools.md).

---

## 7. Tools

Under **`tools:`** you configure:

| Setting | Meaning |
|--------|--------|
| **`file_read_base`** | Base directory for file_read, folder_list, document_read; paths are relative to this. |
| **`file_read_max_chars`** | Max chars returned by file_read when not overridden per call. |
| **`run_skill_allowlist`** | If set, only these script names under skill/scripts/ are allowed; [] = allow all. |
| **`run_skill_timeout`** | Timeout in seconds for run_skill. |
| **`web.search`** | Web search provider (duckduckgo, google_cse, bing, tavily, brave, serpapi) and API keys (or env vars). |
| **`browser_enabled`** | If false, Core does not register browser tools; use plugin (e.g. homeclaw-browser) for browser actions. |
| **`tool_timeout_seconds`** | Per-tool execution timeout; 0 = no timeout. |

API keys for tools (e.g. Tavily, Google CSE) can be set in **core.yml** under the tool block or via **environment variables** where documented.

---

## 8. Auth

When Core is reachable from the internet (e.g. Cloudflare Tunnel, Tailscale Funnel), enable auth so only you can use it.

| Setting | Meaning |
|--------|--------|
| **`auth_enabled`** | If true, **POST /inbound** and **WebSocket /ws** require an API key. |
| **`auth_api_key`** | The secret key. Clients must send **X-API-Key** or **Authorization: Bearer &lt;key&gt;** on each request. |

Use a long, random value (e.g. 32+ characters). See [Remote access](remote-access.md).

### Public URL and Pinggy (Companion scan-to-connect)

When you want to reach Core from another network (e.g. Companion on your phone), **GET /pinggy** shows a public URL and a **QR code** for the Companion app (Settings → Scan QR to connect). You can supply the URL in either of two ways:

| Setting | Meaning |
|--------|--------|
| **`core_public_url`** | Your public Core URL (e.g. from Cloudflare Tunnel, Tailscale Funnel). When set, **/pinggy** shows this URL and a QR code for Companion; also used for file/report links (**/files/out**). Leave empty for local-only or if using Pinggy. |
| **`pinggy.token`** | Your Pinggy token from [pinggy.io](https://pinggy.io). When set, Core starts the Pinggy tunnel and **/pinggy** shows the tunnel URL and QR. Leave empty if using **core_public_url** or another service. |
| **`pinggy.open_browser`** | If true, open the browser to **/pinggy** when the Pinggy tunnel is ready (default: true). Only applies when **pinggy.token** is set. |

Use **core_public_url** when you expose Core yourself (e.g. Cloudflare Tunnel, Tailscale Funnel). Use **pinggy.token** when you want Core to start the Pinggy tunnel. See [Remote access](remote-access.md).

---

## 9. Other important settings

| Setting | Meaning |
|--------|--------|
| **`profile.enabled`** | Per-user profile (name, preferences) stored in JSON; model can read/update via tools. |
| **`workspace_dir`** | Workspace root (e.g. for AGENT_MEMORY.md, identity files). |
| **`use_workspace_bootstrap`** | Inject workspace files (IDENTITY.md, AGENTS.md, TOOLS.md) into system prompt. |
| **`database`** | Relational DB for chat history/sessions: **backend** (sqlite, mysql, postgresql), **url**. |
| **`vectorDB`** | Used when **memory_backend: chroma**; backend (chroma, qdrant, etc.) and connection. |
| **`graphDB`** | Used when memory_backend is chroma; backend (kuzu, neo4j) for entity/relationship graph. |
| **`cognee`** | Used when **memory_backend: cognee**; relational, vector, graph providers and optional LLM/embedding overrides. |
| **`silent`** | If true, reduce logging for memory/tools/skills/plugin/orchestrator. |
| **`llm_max_concurrent_local`** | Max concurrent local (llama.cpp) calls; default 1. |
| **`llm_max_concurrent_cloud`** | Max concurrent cloud (LiteLLM) calls; default 4; 2–10 under provider RPM/TPM. |
| **`compaction`** | When context approaches model limit: trim or summarize messages; **reserve_tokens** for reply. |

---

## Summary

- **core.yml** controls server, **models** (local/cloud, mix routing), **memory**, **knowledge base**, **skills & plugins**, **tools**, and **auth**.
- **Models:** Set **main_llm_local**, **main_llm_cloud**, **embedding_llm**; use **main_llm_mode: mix** and **hybrid_router** for per-request local/cloud routing.
- **Memory:** **use_memory**, **memory_backend** (cognee/chroma), agent/daily memory files, **session** scope and pruning.
- **Knowledge base:** **knowledge_base.enabled**, backend, chunking, **file_understanding** for auto-add on file upload.
- **Routing:** **hybrid_router** (default_route, heuristic, semantic, slm) when **main_llm_mode: mix**.
- **API keys:** For cloud models and some tools, set via **environment variable** or in **core.yml** (env recommended for secrets).

For the full file with every key, see **config/core.yml** (and **config/core.yml.reference** if present) in the repo. For model examples and tested configs, see [Models](models.md).
