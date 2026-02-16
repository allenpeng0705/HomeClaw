<p align="center">
  <img src="HomeClaw_Banner.jpg" alt="HomeClaw Banner">
</p>

# HomeClaw

**HomeClaw** is a **local-first AI assistant** that runs on your own hardware. Each installation is an autonomous agent: it talks to you over the channels you already use (email, Telegram, Discord, WebChat, etc.), keeps memory and context, and extends its abilities through **plugins** and **skills**. You can run it entirely on **local models** (llama.cpp, GGUF) or mix in **cloud models** (OpenAI, Google Gemini, DeepSeek, Anthropic, and more) for flexibility. HomeClaw is **for the people**—decentralized, private when you want it, and fully under your control.

**Other languages / 其他语言 / 他の言語 / 다른 언어:** [简体中文](README_zh.md) | [日本語](README_jp.md) | [한국어](README_kr.md)

---

## Table of Contents

1. [What is HomeClaw?](#1-what-is-homeclaw)
2. [What Can HomeClaw Do?](#2-what-can-homeclaw-do)
3. [How to Use HomeClaw](#3-how-to-use-homeclaw)
4. [Skills and Plugins: Make HomeClaw Work for You](#4-skills-and-plugins-make-homeclaw-work-for-you)
5. [Plugins: Extend HomeClaw](#5-plugins-extend-homeclaw)
6. [Skills: Extend HomeClaw with Workflows](#6-skills-extend-homeclaw-with-workflows)
7. [Acknowledgments](#7-acknowledgments)
8. [Contributing & License](#8-contributing--license)

---

## 1. What is HomeClaw?

### Design idea

HomeClaw is built around a few principles:

- **Local-first** — The core runs on your machine. You can use only local LLMs (llama.cpp, GGUF) so that conversations and memory stay on your hardware.
- **Channel-agnostic** — The same Core serves all channels. Whether you talk via WebChat, Telegram, email, or Discord, the AI is one agent with one memory and one set of tools and plugins.
- **Modular** — The LLM layer, memory, channels, plugins, and tools are separate. You can swap local vs cloud models, enable or disable skills and plugins, and add new channels without changing the core logic.
- **Extensible** — **Plugins** add focused features (weather, news, email, custom APIs). **Skills** add application-style workflows (e.g. “social media agent”) that the LLM follows using tools. Both are designed so you can tailor HomeClaw to your needs.

### Modules and structure

HomeClaw is organized into a **Core** (one process), **channels** (separate processes or HTTP clients), **LLM layer** (local and/or cloud), **memory** (RAG + chat history), **profile** (per-user learning), and **plugins** + **tools** + **skills**. The diagrams below show all modules and how data flows through the system, including how the LLM (local or cloud) is used and how tools, skills, and plugins are selected.

**System overview: all modules**

```mermaid
flowchart TB
  subgraph Channels["Channels (separate processes or clients)"]
    WebChat
    Telegram
    Discord
    Email
    Webhook
    CLI["CLI (main.py)"]
  end

  subgraph Core["Core Engine (port 9000)"]
    Router["Permission (user.yml)"]
    Orch["Orchestrator (TIME vs OTHER)"]
    TAM["TAM (reminders, cron)"]
    Answer["answer_from_memory"]
    ToolExec["Tool executor"]
    PluginMgr["Plugin Manager"]
    Router --> Orch
    Orch --> TAM
    Orch --> PluginMgr
    Orch --> Answer
    Answer --> ToolExec
    Answer --> PluginMgr
  end

  subgraph Context["Context for LLM (built each request)"]
    Workspace["Workspace (identity, TOOLS.md)"]
    SkillsBlock["Skills block (SKILL.md list)"]
    MemoryBlock["RAG memories + chat history"]
    ProfileBlock["Profile (About the user)"]
    RoutingBlock["Routing: plugins list + choose one"]
    Workspace --> SkillsBlock --> MemoryBlock --> ProfileBlock --> RoutingBlock
  end

  subgraph LLM["LLM Layer — local OR cloud"]
    Local["Local: llama.cpp (GGUF)"]
    Cloud["Cloud: LiteLLM (OpenAI, Gemini, DeepSeek, etc.)"]
  end

  subgraph Memory["Memory system"]
    VectorStore["Vector store (Cognee/Chroma)"]
    ChatDB["Chat history (SQLite)"]
    KB["Knowledge base (optional)"]
    Embedding["Embedding model (local or cloud)"]
    Embedding --> VectorStore
  end

  subgraph Profile["Profile learning"]
    ProfileStore["Profile store (JSON per user)"]
  end

  subgraph Extensions["Tools / Skills / Plugins"]
    ToolReg["Tool registry (file, memory, web, cron, route_to_plugin, run_skill, …)"]
    SkillsDir["Skills (config/skills/, SKILL.md)"]
    PluginsDir["Plugins (built-in + external HTTP)"]
  end

  Channels -->|"user message"| Core
  Answer --> Context
  Context --> LLM
  Answer --> Memory
  Answer --> Profile
  Answer --> Extensions
  ToolExec --> ToolReg
  ToolExec --> PluginsDir
  ToolExec --> SkillsDir
  PluginMgr --> PluginsDir
```

**Data flow: how a message is handled and where the LLM is used**

```mermaid
sequenceDiagram
  participant User
  participant Channel
  participant Core
  participant Profile
  participant Memory
  participant LLM as "LLM (local or cloud)"
  participant Tools
  participant Plugin

  User->>Channel: message
  Channel->>Core: POST /inbound or /ws
  Core->>Core: Permission (user.yml)
  alt Non-unified: orchestrator runs first
    Core->>LLM: Intent + plugin selection (one call)
    LLM-->>Core: TIME → TAM, or OTHER + plugin_id
    Core->>Plugin: Run plugin (if selected)
    Plugin-->>Core: response
    Core->>Channel: response
  else Unified (default): main path
    Core->>Memory: RAG: fetch relevant memories (embedding)
    Core->>Profile: Load profile (user_id)
    Core->>Core: Build system prompt: workspace + skills + memories + profile + routing (plugins list)
    Core->>Core: Load chat history (SQLite)
    loop Tool loop (LLM may call tools many times)
      Core->>LLM: messages + tools schema (local or cloud)
      LLM-->>Core: tool_calls (e.g. route_to_plugin, file_read, run_skill) or final text
      alt LLM returns tool_calls
        Core->>Tools: Execute (file_read, memory_search, cron_schedule, route_to_plugin, run_skill, …)
        Tools->>Plugin: If route_to_plugin → run plugin (params from profile/config)
        Plugin-->>Tools: plugin result
        Tools-->>Core: tool result
        Core->>Core: Append result to messages, repeat
      else LLM returns final text
        Core->>Memory: Optionally add to memory (embedding)
        Core->>Core: Save turn to chat history
        Core->>Channel: response
      end
    end
  end
  Channel->>User: reply
```

**Summary of what the diagram shows**

| Aspect | Where it appears |
|--------|-------------------|
| **LLM: local or cloud** | **LLM Layer** in the first diagram; **LLM (local or cloud)** in the sequence. Core calls one OpenAI-compatible API; that API is served by **local** (llama.cpp, GGUF) or **cloud** (LiteLLM → OpenAI, Gemini, DeepSeek, etc.). Main and embedding model can each be local or cloud. |
| **Memory system** | **Memory** subgraph: vector store (Cognee or Chroma), chat history (SQLite), optional knowledge base. **RAG**: embedding model vectorizes query and memories; relevant chunks are fetched and injected into the system prompt. |
| **Profile learning** | **Profile** subgraph: per-user JSON (e.g. `database/profiles/<user_id>.json`). Loaded each request and injected as **"About the user"** in the prompt. Used for personalization and for plugin parameter resolution (`profile_key`). |
| **Tools / skills / plugin selection** | **Context** includes: workspace (TOOLS.md), **skills block** (list of skills from SKILL.md), **routing block** (list of plugins + “choose one: time tools, route_to_tam, route_to_plugin, run_skill, or other tools”). **Tool registry** holds all tools (file_read, memory_search, route_to_plugin, run_skill, …). The **LLM** sees this context and chooses which tool to call (or to reply with text). So selection is done by the **LLM** given the prompt and tool schemas; no separate “selector” service. |

- **Channels** — Email, Matrix, Tinode, WeChat, WhatsApp, Telegram, Discord, Slack, WebChat, webhook, Google Chat, Signal, iMessage, Teams, Zalo, Feishu, DingTalk, BlueBubbles. Each channel connects to Core via HTTP (`/inbound`, `/process`) or WebSocket (`/ws`). See [Channels](#2-what-can-homeclaw-do) and `channels/README.md`.
- **Core** — Single FastAPI app: permission check (`config/user.yml`), orchestrator (intent TIME vs OTHER; plugin selection), TAM (reminders, cron), tool execution (file, memory, web search, browser, cron, `route_to_plugin`, `run_skill`), plugin invocation, and chat + RAG. Config: `config/core.yml`.
- **LLM layer** — One OpenAI-compatible API used by Core. Filled by **local models** (llama.cpp server, GGUF) and/or **cloud models** (LiteLLM: OpenAI, Google Gemini, DeepSeek, Anthropic, Groq, Mistral, etc.). Main and embedding model can be chosen independently. See `config/core.yml` (`local_models`, `cloud_models`, `main_llm`, `embedding_llm`).
- **Memory** — **Cognee** (default) or in-house **Chroma** backend: vector + relational + optional graph. Used for RAG and chat history. See `docs/MemoryAndDatabase.md`.
- **Profile** — Per-user JSON store (e.g. `database/profiles/`). Loaded each request and injected as “About the user” in the prompt; used for personalization and plugin parameter resolution. See `docs/UserProfileDesign.md`.
- **Plugins** — Built-in (Python in `plugins/`) and external (HTTP, any language). Core routes user intent to a plugin (e.g. Weather, News, Mail) when the request matches. See [§5 Plugins](#5-plugins-extend-homeclaw).
- **Skills** — Folders under `config/skills/` with `SKILL.md` (name, description, workflow). The LLM uses tools to accomplish skill workflows; optional `run_skill` runs scripts. See [§6 Skills](#6-skills-extend-homeclaw-with-workflows).

For a full design reference, see **Design.md**. For tools vs skills vs plugins, see **docs/ToolsSkillsPlugins.md**.

---

## 2. What Can HomeClaw Do?

### Connect via different channels

You can talk to HomeClaw from:

- **WebChat** — Browser UI over WebSocket (`python -m channels.run webchat`, default http://localhost:8014).
- **CLI** — Interactive chat in the terminal (`python -m main start`).
- **Telegram, Discord, Slack** — Inbound bots: set bot token in `channels/<name>/.env`, add your user ID to `config/user.yml`, run `python -m channels.run telegram` (or `discord`, `slack`).
- **Email, Matrix, Tinode, WeChat, WhatsApp** — Full channels; see `channels/README.md` for setup.
- **Webhook** — Any client can POST to the webhook’s `/message` and get a reply (relay to Core `/inbound`). Useful when Core is not directly reachable (e.g. behind NAT).

All channels use the same Core: one agent, one memory, one set of plugins and skills. See **docs/RunAndTestPlugins.md** for a quick run/test flow.

### Multi-user support

Core uses an **allowlist** in `config/user.yml`. Only users listed there can send messages to Core. Chat history, memory, knowledge base, and profile data are **keyed by system user id** (from `id` or `name`), so each user has isolated data.

**Fields per user:**

- **name** (required) — Display name.
- **id** (optional) — Unique system user id used for all storage; defaults to `name` if omitted.
- **email** — List of email addresses (for email channel).
- **im** — List of channel identities for IM: `"<channel>:<id>"` (e.g. `telegram_<chat_id>`, `discord_<user_id>`, `matrix:@user:domain`, `tinode:usrXXXX`, `wechat:wxid`).
- **phone** — List of phone numbers (for SMS/phone channels).
- **permissions** — Optional (e.g. `[IM, EMAIL, PHONE]`); empty = allow all channel types.

**How to configure multi-user**

1. **Edit** `config/user.yml`. Add one entry under `users:` per person (or per identity).
2. **Channel identities** — Each channel sends a `user_id`; Core matches it against that user’s `email`, `im`, or `phone`. Use the format your channel expects:
   - **Telegram**: add `telegram_<chat_id>` to `im` (get chat_id from your bot when the user sends a message, or from Telegram API).
   - **Discord**: add `discord_<user_id>` to `im` (Discord numeric user id).
   - **Slack**: add `slack_<user_id>` to `im`.
   - **Matrix**: add `matrix:@localpart:domain` (e.g. `matrix:@alice:matrix.org`) to `im`.
   - **WebChat / inbound**: client sends `user_id` in the JSON; add that exact string to `im` (e.g. `webchat_local` or `webchat_<your_id>`).
   - **Email**: add the email address to `email:`.
3. **No overlap** — Each email/im/phone value must appear for at most one user (Core validates on load). One person can have multiple IDs (e.g. Matrix + Telegram) in the same user entry or in two entries with the same `id`/`name` if you want one logical user.
4. **First match wins** — Core finds the first user whose `email`/`im`/`phone` contains the request’s `user_id`; that user’s `id`/`name` becomes the system user id for the request.

**Example** (two users: one Telegram, one Matrix + WebChat):

```yaml
users:
  - id: alice
    name: Alice
    email: []
    im: ['telegram_123456789', 'webchat_alice']
    phone: []
    permissions: []
  - id: bob
    name: Bob
    email: ['bob@example.com']
    im: ['matrix:@bob:matrix.org']
    phone: []
    permissions: []
```

For full behaviour (matching logic, per-user data, direct reply), see **docs/MultiUserSupport.md**. For per-user profile (learned facts), see **docs/UserProfileDesign.md**.

### Secure and safe: local vs cloud models

- **Local models** — Run GGUF models via llama.cpp server on your machine. Data stays on your hardware; no third-party API. Configure in `config/core.yml` under `local_models`; set `main_llm` and `embedding_llm` to e.g. `local_models/Qwen3-14B-Q5_K_M`.
- **Cloud models** — Use LiteLLM in `config/core.yml` under `cloud_models`. Set `api_key_name` (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`) and the corresponding environment variable. HomeClaw sends prompts to the provider you choose; their privacy and terms apply.
- **Mix** — You can use a local model for chat and a cloud model for embedding (or vice versa). Switch at runtime via `llm set` / `llm cloud` in the CLI or by editing `main_llm` / `embedding_llm` in `config/core.yml`.
- **Remote access** — If you expose Core on the internet (e.g. for WebChat or bots), enable **auth** in `config/core.yml`: `auth_enabled: true` and `auth_api_key: "<secret>"`. Clients must send `X-API-Key` or `Authorization: Bearer <key>` on `/inbound` and `/ws`. See **docs/RemoteAccess.md**.

Supported cloud providers (via LiteLLM) include **OpenAI** (GPT-4o, etc.), **Google Gemini**, **DeepSeek**, **Anthropic**, **Groq**, **Mistral**, **xAI**, **Cohere**, **Together AI**, **OpenRouter**, **Perplexity**, and others. See `config/core.yml` and [LiteLLM docs](https://docs.litellm.ai/docs/providers).

---

## 3. How to Use HomeClaw

For a **step-by-step guide** (install, config, local/cloud models, memory, tools, workspace, testing, plugins, skills), see **[HOW_TO_USE.md](HOW_TO_USE.md)** (also [中文](HOW_TO_USE_zh.md) | [日本語](HOW_TO_USE_jp.md) | [한국어](HOW_TO_USE_kr.md)).

### Supported platforms

HomeClaw runs on **macOS**, **Windows**, and **Linux**. You need:

- **Python** 3.10–3.12 (recommended).
- For **local GGUF models**: a **llama.cpp** server (or use the bundled `llama.cpp-master` and start servers per config).
- For **cloud models**: only network access and the right API keys in the environment.

### Quick start (run, config, test)

1. **Clone and install**

   ```bash
   git clone <repo_url>
   cd <your_clone_folder>   # e.g. HomeClaw or GPT4All
   pip install -r requirements.txt
   ```

2. **Config**

   - **Core**: `config/core.yml` — host, port (default 9000), `main_llm`, `embedding_llm`, `use_tools`, `use_skills`, `use_memory`, etc.
   - **Users**: `config/user.yml` — allowlist of users and their channel identities (email, im, phone).
   - **Channels**: Copy `channels/.env.example` to `channels/.env`; set `CORE_URL` (e.g. `http://127.0.0.1:9000`) and any bot tokens (e.g. `TELEGRAM_BOT_TOKEN`). See `channels/README.md` per channel.

3. **Models**

   - **Local**: Download GGUF models (e.g. from Hugging Face) into a `models/` folder; configure `local_models` in `config/core.yml` with path, host, port. Start the llama.cpp server(s) for each model you use. Or use **Ollama**: run Ollama, then use `llm download` and `llm set` in the CLI.
   - **Cloud**: Add entries to `cloud_models` in `config/core.yml` with `api_key_name`; set the env var (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`). Set `main_llm` to e.g. `cloud_models/OpenAI-GPT4o`.

4. **Run Core**

   ```bash
   python -m core.core
   ```

   Or run the interactive CLI (Core + built-in channel):

   ```bash
   python -m main start
   ```

5. **Run a channel** (in another terminal)

   ```bash
   python -m channels.run webchat
   ```

   Open http://localhost:8014 (or the port shown). Or run Telegram/Discord/Slack, etc., as needed.

6. **Test**

   - Send a message in WebChat or the CLI. For tools/skills/plugins, see **docs/ToolsAndSkillsTesting.md** and **docs/RunAndTestPlugins.md**.
   - Check config and LLM connectivity: `python -m main doctor`.

### Commands (interactive CLI, `python -m main start`)

- **llm** — List models; **llm set** — switch local model; **llm cloud** — set cloud LLM; **llm download** — pull models via Ollama.
- **channel** — Help; **channel list** — list channels; **channel run &lt;name&gt;** — start a channel in the background.
- **wechat user / whatsapp user / matrix user / email user** — Configure allowed users for that channel.
- **reset** — Reset memory and history (or use Core API: `GET/POST http://127.0.0.1:9000/memory/reset`).

### Example: local GGUF models

Place GGUF files in a `models/` directory. In `config/core.yml`, define `local_models` with `id`, `path`, `host`, `port` for each model (and one for embedding). Set `main_llm` and `embedding_llm` to e.g. `local_models/<id>`. Start the llama.cpp server(s) for those ports. Example model links (see Hugging Face for latest):

- **Embedding** (e.g. BGE-M3): [bge-m3-Q5_K_M.gguf](https://huggingface.co/gpustack/bge-m3-GGUF/blob/main/bge-m3-Q5_K_M.gguf)
- **Chat**: Qwen3-8B/14B/32B, Qwen2.5-7B/14B, Llama-3.2-3B/8B, GLM-4-9B/32B, Gemma-3-4B/12B/27B, DeepSeek-R1-Distill-Qwen-1.5B/7B/14B, etc. (search “GGUF” on Hugging Face and set path in `local_models`).

**Tested setup:** Embedding **bge-m3-Q5_K_M.gguf**; chat **Qwen3-14B-Q5_K_M.gguf**. These work well together for local RAG and conversation.

### Where to put local models and how to select them

- **Model directory** — In `config/core.yml`, **`model_path`** (default `../models/`) is the base directory for GGUF files. Paths in **`local_models`** are **relative to `model_path`** (e.g. `path: bge-m3-Q5_K_M.gguf` or `path: deepseek-r1/DeepSeek-R1-Distill-Qwen-14B-Q5_K_M.gguf`). You can use an absolute path instead. Place all GGUF files under that base (e.g. project root `models/` or `../models/`).
- **Selecting models by system** — Choose size and quantization based on your hardware:
  - **CPU only**: Prefer smaller models (e.g. 1.5B–7B) and higher quantization (Q4_K_M, Q5_K_M) for speed; 14B+ may be slow.
  - **GPU (e.g. 8GB VRAM)**: 7B–14B Q4/Q5 is typical; 32B may need Q4 or offload.
  - **GPU (16GB+ VRAM)**: 14B–32B at Q5 or Q8; adjust based on VRAM.
  - **RAM**: Ensure enough system RAM for the model file and llama.cpp process (roughly 1–1.5× model file size).
- **Config** — In `config/core.yml`, under **`local_models`**, add one entry per model with `id`, `path` (relative to `model_path`), `host`, `port`, and `capabilities` (e.g. `[Chat]` or `[embedding]`). Set **`main_llm`** and **`embedding_llm`** to `local_models/<id>` (e.g. `local_models/Qwen3-14B-Q5_K_M`). Start one llama.cpp server per model on the configured port (see `llama.cpp-master/README.md`). At runtime you can switch the main model via CLI: **`llm set`** (local) or **`llm cloud`** (cloud).

### How to set OpenAI, Gemini, or other cloud AI

- **Config** — In `config/core.yml`, **`cloud_models`** lists each provider with `id`, `path` (LiteLLM model name, e.g. `openai/gpt-4o`, `gemini/gemini-1.5-pro`), `host`, `port`, **`api_key_name`**, and `capabilities`. Set **`main_llm`** (or **`embedding_llm`**) to `cloud_models/<id>` (e.g. `cloud_models/OpenAI-GPT4o`, `cloud_models/Gemini-1.5-Pro`).
- **API keys** — For each cloud model you use, set the **environment variable** that matches **`api_key_name`** where Core runs, e.g.:
  - **OpenAI**: `OPENAI_API_KEY`
  - **Google Gemini**: `GEMINI_API_KEY`
  - **DeepSeek**: `DEEPSEEK_API_KEY`
  - **Anthropic**: `ANTHROPIC_API_KEY`
  - **Groq**: `GROQ_API_KEY`
  - **Mistral**: `MISTRAL_API_KEY`
  - **xAI**: `XAI_API_KEY`
  - **OpenRouter**: `OPENROUTER_API_KEY`
  - (See `config/core.yml` and [LiteLLM providers](https://docs.litellm.ai/docs/providers) for more.)
- **Running LiteLLM** — Each cloud entry has its own `host`/`port` in config. Run a LiteLLM proxy (or one proxy per provider) that serves OpenAI-compatible `/v1/chat/completions` and `/v1/embeddings` on that host/port, with the corresponding API key. Then Core calls that URL; no API key is stored in `core.yml`—only the env var name.
- **Switch at runtime** — Use the CLI: **`llm cloud`** to choose a cloud model as the main LLM, or edit `main_llm` / `embedding_llm` in `config/core.yml` and restart Core.

### How to switch to enterprise-level databases (Postgres, Neo4j, enterprise vector DB)

HomeClaw uses a **relational DB** (chat history, sessions), a **vector DB** (RAG memory), and an optional **graph DB** (entities/relationships). You can keep defaults (SQLite, Chroma, optional Kuzu) or switch to enterprise backends.

- **Memory backend** — In `config/core.yml`, **`memory_backend`** is either **`cognee`** (default) or **`chroma`** (in-house RAG). The rest of the config depends on this choice.
- **When `memory_backend: cognee`** (default):
  - Configure via the **`cognee:`** section in `config/core.yml` and/or **Cognee’s `.env`** (see [docs.cognee.ai](https://docs.cognee.ai/)). The **`vectorDB`** and **`graphDB`** blocks in `core.yml` are **not** used for memory.
  - **Relational**: Default SQLite. For **PostgreSQL**, set `cognee.relational.provider: postgres` and `host`, `port`, `username`, `password`, `name`. Install: `pip install "cognee[postgres]"`.
  - **Vector**: Default ChromaDB. For **Qdrant**, **PGVector**, **LanceDB**, **Redis**, etc., set `cognee.vector.provider` and the corresponding URL/credentials; install the Cognee extra (e.g. `cognee[qdrant]`).
  - **Graph**: Default Kuzu. For **Neo4j** or **Neptune**, set `cognee.graph.provider` and URL/credentials; see Cognee docs.
- **When `memory_backend: chroma`** (in-house):
  - All storage is configured in **`config/core.yml`** under **`database:`**, **`vectorDB:`**, and **`graphDB:`**.
  - **Relational**: Set **`database.backend`** to **`postgresql`** (or `mysql`) and **`database.url`** (e.g. `postgresql+psycopg2://user:password@host:5432/dbname`). Core’s chat history, sessions, and runs then use Postgres.
  - **Vector**: Set **`vectorDB.backend`** to **`qdrant`**, **`milvus`**, **`pinecone`**, or **`weaviate`** and fill the corresponding block (host, port, url, api_key as needed).
  - **Graph**: Set **`graphDB.backend`** to **`neo4j`** and set **`graphDB.Neo4j.url`**, `username`, `password` for enterprise graph storage.
- **Core’s chat DB** — The **`database:`** section in `core.yml` is always used for Core’s own chat history, sessions, and runs. So even with `memory_backend: cognee`, you can set `database.backend: postgresql` and `database.url` to put Core’s relational data on Postgres.

For a full support matrix and step-by-step examples, see **docs/MemoryAndDatabase.md**.

### For developers (Windows notes)

- **Visual C++ Build Tools** may be required on Windows for some dependencies. See [Install Visual Studio Build Tools](https://github.com/bycloudai/InstallVSBuildToolsWindows).
- **WeChat channel**: Supported WeChat version and setup are documented in the CLI (`channel` command). Run `python -m channels.run wechat` and use `wechat user` to allow users.

### China developers

For faster pip installs, you can use a mirror, e.g.:

- 清华大学: https://pypi.tuna.tsinghua.edu.cn/simple/
- 阿里云: http://mirrors.aliyun.com/pypi/simple/

---

## 4. Skills and Plugins: Make HomeClaw Work for You

HomeClaw ships with **tools** (file, memory, web search, cron, browser, etc.), **plugins** (e.g. Weather, News, Mail), and **skills** (workflows described in SKILL.md). Together they let you:

- **Answer and remember** — The main LLM uses RAG (memory) and chat history to answer; you can store/recall with tools or natural language.
- **Do one thing well** — Ask for weather, news, or email; the orchestrator routes to the right **plugin** and returns the result.
- **Run workflows** — Enable **skills** in `config/core.yml` (`use_skills: true`). The LLM sees “Available skills” and can follow a skill’s instructions (using tools) or call **run_skill** to run a script.
- **Schedule and remind** — Use **TAM** (Time Awareness Module): say “remind me in 5 minutes” or “every day at 9am”; or use tools like `remind_me`, `record_date`, `cron_schedule`.

You don’t have to “call” plugins or skills by name—just ask naturally. The system routes to plugins when the intent matches and uses tools/skills when the model decides. See **docs/ToolsSkillsPlugins.md** for how the LLM chooses between tools, skills, and plugins.

---

## 5. Plugins: Extend HomeClaw

**Plugins** are single-feature modules: one plugin = one focused capability (e.g. Weather, News, Mail, custom API).

### Built-in plugins (Python)

- Live under `plugins/<Name>/` with **plugin.yaml** (id, description, capabilities), **config.yml** (API keys, defaults), and **plugin.py** (class extending `BasePlugin`).
- Core discovers them at startup; no registration step. Example: **Weather** (`plugins/Weather/`), **News** (`plugins/News/`), **Mail** (`plugins/Mail/`).
- The LLM sees the plugin list in the routing block and calls **route_to_plugin(plugin_id)** when the user intent matches. Core invokes the plugin and sends the response back to the channel.

### External plugins (any language)

- Run as a separate **HTTP server** (Node.js, Go, Java, Python, etc.) that implements:
  - `GET /health` → 2xx
  - `POST /run` (or your path) → body = PluginRequest JSON, response = PluginResult JSON.
- **Register** with Core: `POST http://<core>:9000/api/plugins/register` with plugin id, name, description, `health_check_url`, `type: "http"`, `config` (base_url, path, timeout_sec), and `capabilities`.
- After registration, Core routes to your server like built-in plugins. See **docs/PluginStandard.md** and **docs/PluginsGuide.md**.

### Example: external plugins (multi-language)

In `examples/external_plugins/` we provide:

- **Python** — Quote (port 3101), Time (port 3102).
- **Node.js** — Quote (port 3111).
- **Go** — Time (port 3112).
- **Java** — Quote (port 3113).

Each folder has a README and a register script. See **examples/external_plugins/README.md** and **docs/RunAndTestPlugins.md**.

### Parameter collection

Plugins can declare parameters (e.g. city, recipient). Core can fill them from **user profile**, **config**, or **user message**; optional **confirm_if_uncertain** and **use_default_directly_for** control confirmation. See **docs/PluginsGuide.md** and **docs/PluginParameterCollection.md**.

---

## 6. Skills: Extend HomeClaw with Workflows

**Skills** are application-style capabilities: each skill is a **folder** under `config/skills/` with a **SKILL.md** (name, description, and optional body that describes how to use tools).

- **What they do** — The LLM sees “Available skills” in the system prompt. When the user request matches a skill’s description, the LLM uses **tools** (file_read, web_search, browser, cron, etc.) to accomplish the workflow. Optionally the skill has a **scripts/** folder; then the LLM can call **run_skill(skill_name, script, ...)** to run a script (e.g. `run.sh`, `main.py`).
- **No separate runtime** — Skills don’t run in a separate process; the “runtime” is the main LLM + tool loop. So skills are **tool-driven workflows**.
- **Enable** — In `config/core.yml`: `use_skills: true`, `skills_dir: config/skills`. Optionally use **skills_use_vector_search** so only relevant skills are injected by similarity to the query. See **docs/SkillsGuide.md** and **docs/ToolsSkillsPlugins.md**.

Example: a “social media agent” skill might describe posting to X/Twitter using browser and cron; the LLM follows the skill’s instructions and calls the appropriate tools.

---

## 7. Acknowledgments

HomeClaw would not exist without two projects that inspired it:

- **GPT4People** — The author’s earlier project that explored decentralized, people-centric AI and channel-based interaction. Many of HomeClaw’s ideas—local-first agents, channels, memory, and the vision of AI “for the people”—grew from that work.
- **OpenClaw** — A sibling ecosystem (gateway, extensions, channels, providers). OpenClaw and HomeClaw share a similar spirit: extensible, channel-based AI that users can run and customize. The contrast between OpenClaw’s gateway/extensions model and HomeClaw’s core/plugins model helped clarify HomeClaw’s design (see **docs/ToolsSkillsPlugins.md** §2.7).

Thank you to everyone who contributed to GPT4People and OpenClaw, and to the open-source communities behind llama.cpp, LiteLLM, Cognee, and the many channels and tools we build on.

---

## 8. Contributing & License

- **Contributing** — We welcome issues, pull requests, and discussions. See **CONTRIBUTING.md** for guidelines.
- **License** — This project is licensed under the **Apache License 2.0**. See the **LICENSE** file.

### Roadmap (summary)

**Next**

- **Local + cloud model mix** — Design how to combine local and cloud models so that work is done efficiently and cost stays low (e.g. use local for simple or high-volume tasks, cloud for complex or low-latency needs; routing and fallback rules).

**Later**

- Simpler setup and onboarding (`python -m main onboard`, `python -m main doctor`).
- More channels and platform integrations.
- Stronger plugin/skill discovery and multi-agent options.
- Optional: directory, trust/reputation, and blockchain-based verification for agent-to-agent use cases.

We’re at the beginning of a long journey. Stay tuned and join us as we grow.
