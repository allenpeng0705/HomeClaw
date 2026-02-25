# How to Use HomeClaw

This guide describes how to **install**, **configure**, and **use** HomeClaw: environment setup, core and user config, local and cloud models, memory, tools, workspace, testing, plugins, and skills.

**Other languages:** [简体中文](HOW_TO_USE_zh.md) | [日本語](HOW_TO_USE_jp.md) | [한국어](HOW_TO_USE_kr.md)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Local GGUF Models](#4-local-gguf-models)
5. [Cloud Mode and API Keys](#5-cloud-mode-and-api-keys)
6. [Memory System](#6-memory-system)
7. [Specific Tools (Web Search, Local Files)](#7-specific-tools-web-search-local-files)
8. [Workspace Files (config/workspace)](#8-workspace-files-configworkspace)
9. [Testing the System](#9-testing-the-system)
10. [Plugins](#10-plugins)
11. [Skills](#11-skills)

---

## 1. Overview

HomeClaw is a **local-first AI assistant** that runs on your machine. You talk to it via **channels** (WebChat, Telegram, Discord, email, etc.). A single **Core** process handles all channels, keeps **memory** (RAG + chat history), and can use **local** (llama.cpp, GGUF) or **cloud** (OpenAI, Gemini, DeepSeek, etc.) models. **Plugins** add features (weather, news, mail); **skills** add workflows (e.g. social media agent) that the LLM follows using tools.

- **Run Core:** `python main.py` (or `python main.py core`) — Core listens on port 9000.
- **Run a channel:** e.g. `python main.py webchat` or start the channel process that sends messages to Core’s `/inbound` or WebSocket.
- **CLI:** `python main.py` supports subcommands like `llm set`, `llm cloud`, and interactive **onboarding** (`python main.py onboard`) to walk through workspace, LLM, channels, and skills.

See the main [README.md](README.md) for architecture and capabilities.

---

## 2. Installation

### 2.1 Python and dependencies

- **Python:** 3.10+ recommended.
- **Install from requirements:**

  ```bash
  pip install -r requirements.txt
  ```

  Core dependencies include: `loguru`, `PyYAML`, `fastapi`, `openai`, `litellm`, `chromadb`, `sqlalchemy`, `aiohttp`, `httpx`, `cognee`, and others. See [requirements.txt](requirements.txt).

### 2.2 Optional extras

- **Browser tools (Playwright):** For `browser_navigate`, `browser_snapshot`, etc. After `pip install playwright`:
  ```bash
  python -m playwright install chromium
  ```
- **Web search (no key):** `duckduckgo-search` is in requirements; set `tools.web.search.provider: duckduckgo` and `fallback_no_key: true` for key-free search.
- **Document processing (file_read / document_read):** `unstructured[all-docs]` in requirements for PDF, Word, HTML, etc.
- **Graph DB (in-house RAG):** `kuzu` for graph when `memory_backend: chroma`. For Neo4j, uncomment `neo4j` in requirements.
- **Channels:** Some channels need extra packages (e.g. WeChat `wcferry`, WhatsApp `neonize`); see requirements comments.

### 2.3 Environment

- Use a **virtual environment** (e.g. `python -m venv venv`, then `source venv/bin/activate` or `venv\Scripts\activate`).
- For **cloud models**, set the API key **environment variables** (see [§5](#5-cloud-mode-and-api-keys)).

---

## 3. Configuration

The main config files are **`config/core.yml`** (Core behavior, LLM, memory, tools) and **`config/user.yml`** (who can use the system and how they are identified).

### 3.1 core.yml (overview)

- **Core server:** `host`, `port` (default 9000), `mode`.
- **Paths:** `model_path` (base dir for GGUF files), `workspace_dir` (default `config/workspace`), `skills_dir` (default `skills`).
- **Features:** `use_memory`, `use_tools`, `use_skills`, `use_workspace_bootstrap`, `memory_backend` (e.g. `cognee` or `chroma`).
- **LLM:** `local_models`, `cloud_models`, `main_llm`, `embedding_llm` (see [§4](#4-local-gguf-models) and [§5](#5-cloud-mode-and-api-keys)).
- **Memory:** `memory_backend`, `cognee:` (when using Cognee), or `database`, `vectorDB`, `graphDB` (when `memory_backend: chroma`). See [§6](#6-memory-system).
- **Tools:** `tools` section: `file_read_base`, `file_read_max_chars`, `web` (search provider, API keys), `browser_enabled`, `browser_headless`, etc. See [§7](#7-specific-tools-web-search-local-files).
- **Result viewer:** `result_viewer` (enabled, port, base_url for report links).
- **Knowledge base:** `knowledge_base` (enabled, backend, chunk settings).

Edit `config/core.yml` to match your setup (paths, ports, providers).

### 3.2 user.yml (allowlist and identities)

- **Purpose:** Defines **who** can talk to Core via channels. All chat, memory, and profile data are keyed by **system user id**.
- **Structure:** List of `users`. Each user has:
  - **id** (optional; defaults to `name`), **name** (required).
  - **email:** list of email addresses (for email channel).
  - **im:** list of `"<channel>:<id>"` (e.g. `matrix:@user:matrix.org`, `telegram:123456`, `discord:user_id`).
  - **phone:** list of numbers (for SMS/phone).
  - **permissions:** e.g. `[IM, EMAIL, PHONE]` or `[]` for all.
- **Example:**

  ```yaml
  users:
    - id: me
      name: Me
      email: [me@example.com]
      im: [telegram:123456, matrix:@me:matrix.org]
      phone: []
      permissions: []
  ```

Only users whose channel identity matches an entry in `user.yml` are allowed. See **docs/MultiUserSupport.md** for details.

---

## 4. Local GGUF Models

### 4.1 Where to put models

- **Base directory:** In `config/core.yml`, **`model_path`** (default `../models/`) is the base directory for GGUF files. Paths in **`local_models`** are **relative to `model_path`** (or you can use absolute paths).
- Place GGUF files under that base (e.g. project root `models/` or `../models/`).

### 4.2 Defining local models (embedding + main model)

In **`config/core.yml`**, under **`local_models`**, add one entry per model:

- **id**, **alias**, **path** (file relative to `model_path`), **host**, **port**, **capabilities** (e.g. `[Chat]` or `[embedding]`).
- **Embedding:** One model with `capabilities: [embedding]`; set **`embedding_llm`** to `local_models/<id>`.
- **Chat:** One or more models with `capabilities: [Chat]`; set **`main_llm`** to `local_models/<id>`.

Example:

```yaml
local_models:
  - id: embedding_text_model
    alias: embedding
    path: bge-m3-Q5_K_M.gguf
    host: 127.0.0.1
    port: 5066
    capabilities: [embedding]
  - id: Qwen3-14B-Q5_K_M
    alias: Qwen3-14B-Q5_K_M
    path: Qwen3-14B-Q5_K_M.gguf
    host: 127.0.0.1
    port: 5023
    capabilities: [Chat]

main_llm: local_models/Qwen3-14B-Q5_K_M
embedding_llm: local_models/embedding_text_model
```

### 4.3 Running llama.cpp servers

- Start **one llama.cpp server per model** on the configured `host` and `port`. Use the same `path` (relative to `model_path`) as in config.
- Example (from the project root, with `model_path: ../models/`): run `llama-server` (or your build) with `-m <path>` and the correct port. See **llama.cpp-master/README.md** for your platform.
- **Tested setup:** Embedding **bge-m3-Q5_K_M.gguf**; chat **Qwen3-14B-Q5_K_M.gguf**. These work well together for local RAG and conversation.

### 4.4 Choosing model size and quantization

- **CPU only:** Prefer smaller models (e.g. 1.5B–7B) and higher quantization (Q4_K_M, Q5_K_M); 14B+ may be slow.
- **GPU (e.g. 8GB VRAM):** 7B–14B Q4/Q5 is typical; 32B may need Q4 or offload.
- **GPU (16GB+ VRAM):** 14B–32B at Q5 or Q8.
- Ensure enough system RAM for the model file and llama.cpp process (roughly 1–1.5× file size).

---

## 5. Cloud Mode and API Keys

### 5.1 Using cloud models

- In **`config/core.yml`**, **`cloud_models`** lists cloud providers (OpenAI, Gemini, Anthropic, DeepSeek, etc.). Each entry has **id**, **path** (e.g. `openai/gpt-4o`), **host**, **port**, **api_key_name**, **capabilities**.
- Set **`main_llm`** or **`embedding_llm`** to `cloud_models/<id>` (e.g. `cloud_models/OpenAI-GPT4o`) to use that model.
- **LiteLLM** is used to talk to cloud APIs. You can run a LiteLLM proxy per provider (or one proxy for several); set `host` and `port` in the cloud model entry to match.

### 5.2 API keys (environment variables)

- Each cloud model entry has **`api_key_name`** (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`). Set the **environment variable** with that name to your API key before starting Core.
- Examples:
  - OpenAI: `export OPENAI_API_KEY=sk-...`
  - Google: `export GEMINI_API_KEY=...`
  - Anthropic: `export ANTHROPIC_API_KEY=...`
  - DeepSeek: `export DEEPSEEK_API_KEY=...`
- **Ollama** entries have no `api_key_name` (local, no key).
- Do **not** put API keys in `core.yml` in version-controlled repos; use env vars or a local override.

### 5.3 Switching between local and cloud

- At runtime you can switch the main model via CLI: **`llm set`** (choose local) or **`llm cloud`** (choose cloud), or by changing `main_llm` in config and restarting.

---

## 6. Memory System

### 6.1 Backends

- **`memory_backend: cognee`** (default): Cognee handles relational, vector, and graph storage. Configure via **`cognee:`** in `config/core.yml` and/or Cognee’s **`.env`**. The `vectorDB` and `graphDB` sections in `core.yml` are **not** used for memory when using Cognee.
- **`memory_backend: chroma`:** In-house RAG: Core uses **`database`**, **`vectorDB`**, and optionally **`graphDB`** in `core.yml` (SQLite + Chroma + Kuzu/Neo4j).

### 6.2 Cognee (default)

- In **`config/core.yml`**, under **`cognee:`**, you can set relational (e.g. sqlite/postgres), vector (e.g. chroma), graph (e.g. kuzu/neo4j), and optionally LLM/embedding. Leave LLM/embedding empty to use Core’s **main_llm** and **embedding_llm** (same host/port).
- See **docs/MemoryAndDatabase.md** for full Cognee vs chroma mapping and Cognee `.env` options.

### 6.3 Resetting memory

- To clear RAG memory for testing: `GET` or `POST` **`http://<core_host>:<core_port>/memory/reset`** (e.g. `curl http://127.0.0.1:9000/memory/reset`).
- To clear the knowledge base: `GET` or `POST` **`http://<core_host>:<core_port>/knowledge_base/reset`**.

---

## 7. Specific Tools (Web Search, Local Files)

### 7.1 Web search

- In **`config/core.yml`**, under **`tools.web.search`**:
  - **provider:** `duckduckgo` (no key), `google_cse`, `bing`, `tavily`, `brave`, `serpapi`. Set the one you want.
  - **API keys:** For `google_cse`, set `api_key` and `cx`. For `tavily`, set `api_key` (or env `TAVILY_API_KEY`). Same for `bing`, `brave`, `serpapi` in their blocks.
  - **fallback_no_key:** If `true`, when the primary provider fails or has no key, Core can fall back to DuckDuckGo (no key). Requires `duckduckgo-search` (in requirements).

### 7.2 Local file processing

- **file_read / folder_list:** Under **`tools`** in `core.yml`:
  - **file_read_base:** Base path for file access (`.` = current working directory, or an absolute path). The model can only read files under this base.
  - **file_read_max_chars:** Max characters returned by `file_read` when the tool doesn’t pass a limit (default 32000; increase for long documents).
- **document_read (PDF, Word, etc.):** Uses **Unstructured** when `unstructured[all-docs]` is installed. Same base path applies; increase `file_read_max_chars` for long PDFs.

### 7.3 Browser tools

- **browser_enabled:** Set to `false` to disable browser tools entirely (only `fetch_url` and `web_search` for web).
- **browser_headless:** Set to `false` to show the browser window (local testing only). Requires Playwright and `playwright install chromium`.

---

## 8. Workspace Files (config/workspace)

The **workspace** is prompt-only: markdown files are **injected into the system prompt** so the LLM knows who it is and what it can do. No code runs from these files.

### 8.1 Files and order

- **`config/workspace/IDENTITY.md`** — Who the assistant is (tone, voice, style). Injected under `## Identity`.
- **`config/workspace/AGENTS.md`** — High-level behavior and routing hints. Injected under `## Agents / behavior`.
- **`config/workspace/TOOLS.md`** — Human-readable list of capabilities. Injected under `## Tools / capabilities`.

They are concatenated in that order, then the RAG response template (memories) is appended. See **config/workspace/README.md** for the full flow and tips.

### 8.2 Config

- In **`config/core.yml`**: **`use_workspace_bootstrap: true`** enables injection; **`workspace_dir`** (default `config/workspace`) is the folder to load.
- Edit the `.md` files to refine identity, behavior, and capability descriptions. Restart Core (or send a new message if you don’t cache) for changes to apply.

### 8.3 Tips

- Keep each file short so the prompt doesn’t grow too large.
- Leave a file empty or delete it to skip that block.

---

## 9. Testing the System

### 9.1 Quick checks

- Start Core: `python main.py` (or `python main.py core`). Core listens on port 9000.
- Start WebChat (if enabled): connect to the WebChat URL and send a message. Ensure `user.yml` allows your identity.
- **Memory reset:** `curl http://127.0.0.1:9000/memory/reset` to clear RAG for a clean test.

### 9.2 Triggering tools

- With **`use_tools: true`**, the LLM can call tools. Example phrases that often trigger tools:
  - **time:** “What time is it?”
  - **memory_search:** “What do you remember about me?”
  - **web_search:** “Search the web for …”
  - **file_read:** “Read file X” / “Summarize the contents of …”
  - **cron_schedule:** “Remind me every day at 9am”
- See **docs/ToolsAndSkillsTesting.md** for a full list of example messages per tool.

### 9.3 Tests (pytest)

- Run tests: `pytest` (from project root). Requirements include `pytest`, `pytest-asyncio`, `httpx`.

---

## 10. Plugins

Plugins add **focused features** (e.g. Weather, News, Mail). They can be **built-in** (Python, in-process) or **external** (HTTP service).

- **How to use and develop plugins:** See **docs/PluginsGuide.md** for what plugins are, how to write them (plugin.yaml, config.yml, plugin.py), and how to register external plugins.
- **Run and test:** **docs/RunAndTestPlugins.md** for step-by-step running and testing (Core, WebChat, registration, example prompts).
- **Parameter collection and config:** **docs/PluginParameterCollection.md** for `profile_key`, `config_key`, and `confirm_if_uncertain`.
- **Standard and registration:** **docs/PluginStandard.md**, **docs/PluginRegistration.md**.

---

## 11. Skills

**Skills** are task-oriented instruction packages (SKILL.md + optional scripts) that tell the assistant *how* to accomplish goals using **tools**. They are “workflows” implemented by the LLM following instructions, not by separate plugin code.

- **Enable:** In **`config/core.yml`**, set **`use_skills: true`** and **`skills_dir`** (default `skills`). Restart Core.
- **Add a skill:** Put a folder under `skills_dir` with a **SKILL.md** (name, description, body). Optionally add scripts under `scripts/` and reference them via **run_skill**.
- **Vector search:** With many skills, set **`skills_use_vector_search: true`** so only relevant skills are injected per query. See **docs/SkillsGuide.md** for options.
- **Reusing skills from OpenClaw:** OpenClaw uses a different extension model (channels/providers/skills in one manifest). HomeClaw skills are **SKILL.md + scripts** under `skills/`. To reuse an OpenClaw “skill” in HomeClaw, adapt the instructions into a **SKILL.md** (name, description, step-by-step body) and place it in `skills/<skill-name>/`. No code port is required if the behavior can be expressed as tool-using steps. See **docs/ToolsSkillsPlugins.md** §2.7 for OpenClaw vs HomeClaw.

**Full skills guide:** **docs/SkillsGuide.md** (structure, use, implement, test). **docs/ToolsSkillsPlugins.md** for the overall tools/skills/plugins design.
