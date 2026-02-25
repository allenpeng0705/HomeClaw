# HomeClaw 使用指南

本文说明如何**安装**、**配置**和**使用** HomeClaw：环境准备、核心与用户配置、本地与云端模型、记忆、工具、工作区、测试、插件与技能。

**其他语言：** [English](HOW_TO_USE.md) | [日本語](HOW_TO_USE_jp.md) | [한국어](HOW_TO_USE_kr.md)

---

## 目录

1. [概述](#1-概述)
2. [安装](#2-安装)
3. [配置](#3-配置)
4. [本地 GGUF 模型](#4-本地-gguf-模型)
5. [云端模式与 API 密钥](#5-云端模式与-api-密钥)
6. [记忆系统](#6-记忆系统)
7. [具体工具（网页搜索、本地文件）](#7-具体工具网页搜索本地文件)
8. [工作区文件（config/workspace）](#8-工作区文件-configworkspace)
9. [系统测试](#9-系统测试)
10. [插件](#10-插件)
11. [技能](#11-技能)

---

## 1. 概述

HomeClaw 是运行在本机的**本地优先 AI 助手**。通过**渠道**（WebChat、Telegram、Discord、邮件等）与之对话。单一 **Core** 进程处理所有渠道，维护**记忆**（RAG + 聊天历史），可使用**本地**（llama.cpp、GGUF）或**云端**（OpenAI、Gemini、DeepSeek 等）模型。**插件**提供天气、新闻、邮件等功能；**技能**提供由 LLM 按说明调用工具完成的工作流（如社交媒体代理）。

- **运行 Core：** `python main.py`（或 `python main.py core`）— Core 监听 9000 端口。
- **运行渠道：** 例如 `python main.py webchat`，或启动向 Core 的 `/inbound` 或 WebSocket 发送消息的渠道进程。
- **CLI：** `python main.py` 支持子命令如 `llm set`、`llm cloud`，以及交互式**引导**（`python main.py onboard`）配置工作区、LLM、渠道与技能。

架构与能力详见主 [README.md](README.md)。

---

## 2. 安装

### 2.1 Python 与依赖

- **Python：** 建议 3.10+。
- **从 requirements 安装：**

  ```bash
  pip install -r requirements.txt
  ```

  核心依赖包括：`loguru`、`PyYAML`、`fastapi`、`openai`、`litellm`、`chromadb`、`sqlalchemy`、`aiohttp`、`httpx`、`cognee` 等。见 [requirements.txt](requirements.txt)。

### 2.2 可选组件

- **浏览器工具（Playwright）：** 用于 `browser_navigate`、`browser_snapshot` 等。安装 `playwright` 后执行：
  ```bash
  python -m playwright install chromium
  ```
- **网页搜索（无需密钥）：** `duckduckgo-search` 已在 requirements 中；在配置中设置 `tools.web.search.provider: duckduckgo` 和 `fallback_no_key: true` 即可免密钥搜索。
- **文档处理（file_read / document_read）：** requirements 中的 `unstructured[all-docs]` 支持 PDF、Word、HTML 等。
- **图数据库（自管 RAG）：** 当 `memory_backend: chroma` 时可使用 `kuzu`。若用 Neo4j，在 requirements 中取消注释 `neo4j`。
- **渠道：** 部分渠道需额外包（如微信 `wcferry`、WhatsApp `neonize`），见 requirements 注释。

### 2.3 环境

- 建议使用**虚拟环境**（如 `python -m venv venv`，再 `source venv/bin/activate` 或 `venv\Scripts\activate`）。
- **云端模型**需设置 **API 密钥环境变量**，见 [§5](#5-云端模式与-api-密钥)。

---

## 3. 配置

主要配置文件为 **`config/core.yml`**（Core 行为、LLM、记忆、工具）和 **`config/user.yml`**（允许使用系统的用户及其身份）。

### 3.1 core.yml（概览）

- **Core 服务：** `host`、`port`（默认 9000）、`mode`。
- **路径：** `model_path`（GGUF 根目录）、`workspace_dir`（默认 `config/workspace`）、`skills_dir`（默认 `skills`）。
- **功能开关：** `use_memory`、`use_tools`、`use_skills`、`use_workspace_bootstrap`、`memory_backend`（如 `cognee` 或 `chroma`）。
- **LLM：** `local_models`、`cloud_models`、`main_llm`、`embedding_llm`，见 [§4](#4-本地-gguf-模型) 与 [§5](#5-云端模式与-api-密钥)。
- **记忆：** `memory_backend`、`cognee:`（使用 Cognee 时），或 `database`、`vectorDB`、`graphDB`（当 `memory_backend: chroma`）。见 [§6](#6-记忆系统)。
- **工具：** `tools` 段：`file_read_base`、`file_read_max_chars`、`web`（搜索提供商、API 密钥）、`browser_enabled`、`browser_headless` 等。见 [§7](#7-具体工具网页搜索本地文件)。
- **结果查看器：** `result_viewer`（启用、端口、报告链接的 base_url）。
- **知识库：** `knowledge_base`（启用、后端、分块等）。

根据你的环境编辑 `config/core.yml`（路径、端口、提供商）。

### 3.2 user.yml（允许列表与身份）

- **作用：** 定义**谁**可以通过渠道与 Core 对话。所有聊天、记忆与档案数据均按**系统用户 id** 区分。
- **结构：** `users` 列表。每项包含：
  - **id**（可选，默认取 `name`）、**name**（必填）。
  - **email：** 邮箱列表（邮件渠道）。
  - **im：** `"<渠道>:<id>"` 列表（如 `matrix:@user:matrix.org`、`telegram:123456`、`discord:user_id`）。
  - **phone：** 号码列表（短信/电话）。
  - **permissions：** 如 `[IM, EMAIL, PHONE]` 或 `[]` 表示全部允许。
- **示例：**

  ```yaml
  users:
    - id: me
      name: Me
      email: [me@example.com]
      im: [telegram:123456, matrix:@me:matrix.org]
      phone: []
      permissions: []
  ```

只有渠道身份与 `user.yml` 中某项匹配的用户才被允许。详见 **docs/MultiUserSupport.md**。

---

## 4. 本地 GGUF 模型

### 4.1 模型放置位置

- **根目录：** 在 `config/core.yml` 中，**`model_path`**（默认 `../models/`）为 GGUF 文件的根目录。**`local_models`** 中的 **path** 均**相对于 `model_path`**（也可写绝对路径）。
- 将所有 GGUF 文件放在该根目录下（如项目根目录的 `models/` 或 `../models/`）。

### 4.2 定义本地模型（嵌入 + 主模型）

在 **`config/core.yml`** 的 **`local_models`** 下为每个模型添加一项：

- **id**、**alias**、**path**（相对于 `model_path` 的文件路径）、**host**、**port**、**capabilities**（如 `[Chat]` 或 `[embedding]`）。
- **嵌入：** 一项 `capabilities: [embedding]`；将 **`embedding_llm`** 设为 `local_models/<id>`。
- **对话：** 一项或多项 `capabilities: [Chat]`；将 **`main_llm`** 设为 `local_models/<id>`。

示例：

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

### 4.3 运行 llama.cpp 服务

- 为每个模型在配置的 `host` 和 `port` 上**各启动一个** llama.cpp 服务。使用的路径与 config 中的 `path`（相对于 `model_path`）一致。
- 示例（项目根目录、`model_path: ../models/`）：用 `llama-server`（或你的构建）以 `-m <path>` 和对应端口启动。平台说明见 **llama.cpp-master/README.md**。
- **已测试组合：** 嵌入 **bge-m3-Q5_K_M.gguf**；对话 **Qwen3-14B-Q5_K_M.gguf**。二者搭配可用于本地 RAG 与对话。

### 4.4 模型规模与量化选择

- **仅 CPU：** 建议较小模型（如 1.5B–7B）和较高量化（Q4_K_M、Q5_K_M）；14B+ 可能较慢。
- **GPU（如 8GB 显存）：** 常见为 7B–14B Q4/Q5；32B 可能需要 Q4 或 offload。
- **GPU（16GB+ 显存）：** 可跑 14B–32B Q5 或 Q8。
- 确保系统 RAM 足够容纳模型文件与 llama.cpp 进程（约 1–1.5 倍文件大小）。

---

## 5. 云端模式与 API 密钥

### 5.1 使用云端模型

- 在 **`config/core.yml`** 中，**`cloud_models`** 列出云端提供商（OpenAI、Gemini、Anthropic、DeepSeek 等）。每项有 **id**、**path**（如 `openai/gpt-4o`）、**host**、**port**、**api_key_name**、**capabilities**。
- 将 **`main_llm`** 或 **`embedding_llm`** 设为 `cloud_models/<id>`（如 `cloud_models/OpenAI-GPT4o`）即可使用该模型。
- 通过 **LiteLLM** 与云端 API 通信。可为每个提供商运行一个 LiteLLM 代理（或一个代理服务多个）；在 cloud 模型项中设置对应的 `host` 和 `port`。

### 5.2 API 密钥（环境变量）

- 每个云端模型项有 **`api_key_name`**（如 `OPENAI_API_KEY`、`GEMINI_API_KEY`）。在启动 Core 前，将**同名环境变量**设为你的 API 密钥。
- 示例：
  - OpenAI：`export OPENAI_API_KEY=sk-...`
  - Google：`export GEMINI_API_KEY=...`
  - Anthropic：`export ANTHROPIC_API_KEY=...`
  - DeepSeek：`export DEEPSEEK_API_KEY=...`
- **Ollama** 项无 `api_key_name`（本地，无需密钥）。
- 请勿在受版本控制的 `core.yml` 中写入 API 密钥；使用环境变量或本地覆盖。

### 5.3 在本地与云端之间切换

- 运行时可通过 CLI **`llm set`**（选本地）或 **`llm cloud`**（选云端）切换主模型，或修改配置中的 `main_llm` 后重启。

---

## 6. 记忆系统

### 6.1 后端

- **`memory_backend: cognee`**（默认）：Cognee 负责关系、向量与图存储。通过 **`cognee:`**（在 `config/core.yml`）和/或 Cognee 的 **`.env`** 配置。使用 Cognee 时，core.yml 中的 `vectorDB`、`graphDB` **不**用于记忆。
- **`memory_backend: chroma`：** 自管 RAG：Core 使用 core.yml 中的 **`database`**、**`vectorDB`** 及可选的 **`graphDB`**（SQLite + Chroma + Kuzu/Neo4j）。

### 6.2 Cognee（默认）

- 在 **`config/core.yml`** 的 **`cognee:`** 下可设置关系型（如 sqlite/postgres）、向量（如 chroma）、图（如 kuzu/neo4j），以及可选的 LLM/embedding。LLM/embedding 留空则使用 Core 的 **main_llm** 与 **embedding_llm**（同一 host/port）。
- Cognee 与 chroma 的对应关系及 Cognee `.env` 选项见 **docs/MemoryAndDatabase.md**。

### 6.3 重置记忆

- 测试时清空 RAG 记忆：对 **`http://<core_host>:<core_port>/memory/reset`** 发送 `GET` 或 `POST`（如 `curl http://127.0.0.1:9000/memory/reset`）。
- 清空知识库：**`http://<core_host>:<core_port>/knowledge_base/reset`**。

---

## 7. 具体工具（网页搜索、本地文件）

### 7.1 网页搜索

- 在 **`config/core.yml`** 的 **`tools.web.search`** 下：
  - **provider：** `duckduckgo`（无密钥）、`google_cse`、`bing`、`tavily`、`brave`、`serpapi`。选择其一。
  - **API 密钥：** `google_cse` 需设置 `api_key` 和 `cx`。`tavily` 设 `api_key`（或环境变量 `TAVILY_API_KEY`）。`bing`、`brave`、`serpapi` 在各自块中设置。
  - **fallback_no_key：** 为 `true` 时，主提供商失败或无密钥时可回退到 DuckDuckGo（无密钥）。需安装 `duckduckgo-search`（已在 requirements 中）。

### 7.2 本地文件处理

- **file_read / folder_list：** 在 **`tools`** 下：
  - **file_read_base：** 文件访问根路径（`.` 为当前工作目录，或绝对路径）。模型只能读取该根路径下的文件。
  - **file_read_max_chars：** 工具未传限制时 `file_read` 返回的最大字符数（默认 32000；长文档可增大）。
- **document_read（PDF、Word 等）：** 安装 `unstructured[all-docs]` 后使用 Unstructured。同一根路径；长 PDF 可增大 `file_read_max_chars`。

### 7.3 浏览器工具

- **browser_enabled：** 设为 `false` 可完全禁用浏览器工具（仅用 `fetch_url` 和 `web_search` 访问网页）。
- **browser_headless：** 设为 `false` 可显示浏览器窗口（仅本地测试）。需安装 Playwright 并执行 `playwright install chromium`。

---

## 8. 工作区文件（config/workspace）

**工作区**仅用于提示：Markdown 文件被**注入到系统提示**中，让 LLM 知道自己的身份与能力。这些文件不执行任何代码。

### 8.1 文件与顺序

- **`config/workspace/IDENTITY.md`** — 助手是谁（语气、风格）。注入为 `## Identity`。
- **`config/workspace/AGENTS.md`** — 高层行为与路由提示。注入为 `## Agents / behavior`。
- **`config/workspace/TOOLS.md`** — 能力的人类可读列表。注入为 `## Tools / capabilities`。

按此顺序拼接，再追加 RAG 响应模板（记忆）。完整流程与技巧见 **config/workspace/README.md**。

### 8.2 配置

- 在 **`config/core.yml`** 中：**`use_workspace_bootstrap: true`** 启用注入；**`workspace_dir`**（默认 `config/workspace`）为加载目录。
- 编辑上述 `.md` 可调整身份、行为与能力描述。修改后需重启 Core（或不缓存时发新消息）生效。

### 8.3 建议

- 各文件保持简短，避免提示过长。
- 留空或删除某文件可跳过对应块。

---

## 9. 系统测试

### 9.1 快速检查

- 启动 Core：`python main.py`（或 `python main.py core`）。Core 监听 9000 端口。
- 启动 WebChat（若启用）：连接 WebChat URL 并发送消息。确保 `user.yml` 中允许你的身份。
- **记忆重置：** `curl http://127.0.0.1:9000/memory/reset` 可清空 RAG 以便干净测试。

### 9.2 触发工具

- **`use_tools: true`** 时，LLM 可调用工具。常见触发示例：
  - **time：** “现在几点？”
  - **memory_search：** “你还记得我什么？”
  - **web_search：** “上网查一下 …”
  - **file_read：** “读一下文件 X” / “总结 … 的内容”
  - **cron_schedule：** “每天 9 点提醒我”
- 各工具示例消息见 **docs/ToolsAndSkillsTesting.md**。

### 9.3 测试（pytest）

- 运行测试：在项目根目录执行 `pytest`。requirements 含 `pytest`、`pytest-asyncio`、`httpx`。

---

## 10. 插件

插件提供**单一功能**（如天气、新闻、邮件），可为**内置**（Python、进程内）或**外部**（HTTP 服务）。

- **使用与开发：** 见 **docs/PluginsGuide.md**（插件概念、编写方式：plugin.yaml、config.yml、plugin.py，以及外部插件注册）。
- **运行与测试：** **docs/RunAndTestPlugins.md** 分步说明运行与测试（Core、WebChat、注册、示例提示）。
- **参数收集与配置：** **docs/PluginParameterCollection.md** 介绍 `profile_key`、`config_key`、`confirm_if_uncertain`。
- **标准与注册：** **docs/PluginStandard.md**、**docs/PluginRegistration.md**。

---

## 11. 技能

**技能**是以任务为导向的说明包（SKILL.md + 可选脚本），告诉助手*如何*用**工具**完成目标。由 LLM 按说明执行，而非独立插件代码。

- **启用：** 在 **`config/core.yml`** 中设置 **`use_skills: true`** 和 **`skills_dir`**（默认 `skills`）。重启 Core。
- **添加技能：** 在 `skills_dir` 下新建文件夹，内含 **SKILL.md**（名称、描述、正文）。可选在 `scripts/` 下放脚本，通过 **run_skill** 调用。
- **向量检索：** 技能较多时可设 **`skills_use_vector_search: true`**，仅注入与查询相关的技能。选项见 **docs/SkillsGuide.md**。
- **复用 OpenClaw 技能：** OpenClaw 使用不同的扩展模型（渠道/提供商/技能在一个 manifest 中）。HomeClaw 技能是 **SKILL.md + scripts**，放在 `skills/` 下。若要将 OpenClaw 的“技能”复用到 HomeClaw，把说明整理成 **SKILL.md**（名称、描述、步骤正文）放入 `skills/<技能名>/` 即可；若行为可用工具步骤表达，无需移植代码。OpenClaw 与 HomeClaw 对比见 **docs/ToolsSkillsPlugins.md** §2.7。

**完整技能指南：** **docs/SkillsGuide.md**（结构、使用、实现、测试）。**docs/ToolsSkillsPlugins.md** 为工具/技能/插件整体设计。
