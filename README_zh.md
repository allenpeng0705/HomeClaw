<p align="center">
  <img src="HomeClaw_Banner.jpg" alt="HomeClaw Banner">
</p>

# HomeClaw

**HomeClaw** 是一款**本地优先的 AI 助手**，运行在您自己的硬件上。每次安装都是一个自主智能体：通过您已有的渠道（邮件、Telegram、Discord、WebChat 等）与您对话，保持**记忆**（RAG + 智能体记忆）与上下文，并通过**内置与外部插件**和**技能**扩展能力。您可以完全使用**本地模型**（llama.cpp、GGUF），或混合使用**云端模型**（OpenAI、**Google Gemini**、DeepSeek、Anthropic 等）；**多模态**（图像、音频、视频）在本地与云端均支持。**Flutter 伴侣应用**（Mac、Windows、iPhone、Android）让 HomeClaw 更易用。**多智能体**即运行多个 HomeClaw 实例。HomeClaw **为人们服务**——去中心化、按需隐私、完全由您掌控。

**亮点：** **伴侣应用**（Flutter，全平台）| **记忆**（RAG + 智能体记忆）| **插件**（内置 + 外部，**任意语言**如 Node.js、Go、Java、Python）| **OpenClaw 技能集** | **多智能体**（多实例）| **云端与多模态**（Gemini 等，本地与云端均可用）

**其他语言 / Other languages:** [English](README.md) | [日本語](README_jp.md) | [한국어](README_kr.md)

**文档:** [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/)

---

## 目录

1. [HomeClaw 是什么？](#1-homeclaw-是什么)
2. [HomeClaw 能做什么？](#2-homeclaw-能做什么)
3. [如何使用 HomeClaw](#3-如何使用-homeclaw)
4. [技能与插件：让 HomeClaw 为您服务](#4-技能与插件让-homeclaw-为您服务)
5. [插件：扩展 HomeClaw](#5-插件扩展-homeclaw)
6. [技能：用工作流扩展 HomeClaw](#6-技能用工作流扩展-homeclaw)
7. [致谢](#7-致谢)
8. [贡献与许可](#8-贡献与许可)

---

## 1. HomeClaw 是什么？

### 设计理念

HomeClaw 围绕以下原则构建：

- **本地优先** — 核心在您的机器上运行。可仅使用本地 LLM（llama.cpp、GGUF），对话与记忆留在本机。
- **渠道无关** — 同一 Core 服务所有渠道。无论通过 WebChat、Telegram、邮件还是 Discord，AI 都是同一智能体、同一记忆、同一套工具与插件。
- **模块化** — LLM 层、记忆、渠道、插件与工具彼此独立。可切换本地/云端模型，启用或禁用技能与插件，新增渠道而无需改动核心逻辑。
- **可扩展** — **插件**提供单一功能（天气、新闻、邮件、自定义 API）；**技能**提供应用式工作流（如「社交媒体代理」），由 LLM 通过工具执行。两者都便于您按需定制 HomeClaw。

### 模块与结构

HomeClaw 由 **Core**（单进程）、**渠道**（独立进程或 HTTP 客户端）、**LLM 层**（本地和/或云端）、**记忆**（RAG + 对话历史）、**档案**（每用户学习）以及 **插件** + **工具** + **技能** 组成。下图展示所有模块及数据流，包括 LLM（本地或云端）的使用方式以及工具、技能、插件的选择方式。

**简单概览**

```mermaid
flowchart LR
  subgraph CH["渠道"]
    A[WebChat、Telegram、邮件...]
  end
  subgraph CO["Core"]
    B[编排器 · 工具 · 插件]
  end
  subgraph LL["LLM"]
    C[本地 / 云端]
  end
  subgraph ME["记忆"]
    D[RAG + 对话]
  end
  CH -->|消息| CO
  CO --> LL
  ME <--> CO
  style CH fill:#e3f2fd,stroke:#1976d2
  style CO fill:#fff3e0,stroke:#ef6c00
  style LL fill:#e8f5e9,stroke:#388e3c
  style ME fill:#fce4ec,stroke:#c2185b
```

**系统概览：所有模块**

```mermaid
flowchart TB
  subgraph Channels["渠道（独立进程或客户端）"]
    WebChat
    Telegram
    Discord
    Email
    Webhook
    CLI["CLI (main.py)"]
  end

  subgraph Core["Core 引擎（端口 9000）"]
    Router["权限 (user.yml)"]
    Orch["编排器 (TIME vs OTHER)"]
    TAM["TAM（提醒、cron）"]
    Answer["answer_from_memory"]
    ToolExec["工具执行器"]
    PluginMgr["插件管理器"]
    Router --> Orch
    Orch --> TAM
    Orch --> PluginMgr
    Orch --> Answer
    Answer --> ToolExec
    Answer --> PluginMgr
  end

  subgraph Context["LLM 上下文（每次请求构建）"]
    Workspace["工作区（身份、TOOLS.md）"]
    SkillsBlock["技能块（SKILL.md 列表）"]
    MemoryBlock["RAG 记忆 + 对话历史"]
    ProfileBlock["档案（关于用户）"]
    RoutingBlock["路由：插件列表 + 择一执行"]
    Workspace --> SkillsBlock --> MemoryBlock --> ProfileBlock --> RoutingBlock
  end

  subgraph LLM["LLM 层 — 本地或云端"]
    Local["本地：llama.cpp (GGUF)"]
    Cloud["云端：LiteLLM (OpenAI, Gemini, DeepSeek 等)"]
  end

  subgraph Memory["记忆系统"]
    VectorStore["向量存储 (Cognee/Chroma)"]
    ChatDB["对话历史 (SQLite)"]
    KB["知识库（可选）"]
    Embedding["嵌入模型（本地或云端）"]
    Embedding --> VectorStore
  end

  subgraph Profile["档案学习"]
    ProfileStore["档案存储（每用户 JSON）"]
  end

  subgraph Extensions["工具 / 技能 / 插件"]
    ToolReg["工具注册表 (file, memory, web, cron, route_to_plugin, run_skill, …)"]
    SkillsDir["技能 (config/skills/, SKILL.md)"]
    PluginsDir["插件（内置 + 外部 HTTP）"]
  end

  Channels -->|"用户消息"| Core
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

**数据流：消息如何被处理及 LLM 的使用位置**

```mermaid
sequenceDiagram
  participant User as 用户
  participant Channel as 渠道
  participant Core
  participant Profile as 档案
  participant Memory as 记忆
  participant LLM as "LLM（本地或云端）"
  participant Tools as 工具
  participant Plugin as 插件

  User->>Channel: 消息
  Channel->>Core: POST /inbound 或 /ws
  Core->>Core: 权限 (user.yml)
  alt 非统一：编排器先运行
    Core->>LLM: 意图 + 插件选择（一次调用）
    LLM-->>Core: TIME → TAM，或 OTHER + plugin_id
    Core->>Plugin: 运行插件（若被选中）
    Plugin-->>Core: 响应
    Core->>Channel: 响应
  else 统一（默认）：主路径
    Core->>Memory: RAG：获取相关记忆（嵌入）
    Core->>Profile: 加载档案 (user_id)
    Core->>Core: 构建系统提示：工作区 + 技能 + 记忆 + 档案 + 路由（插件列表）
    Core->>Core: 加载对话历史 (SQLite)
    loop 工具循环（LLM 可能多次调用工具）
      Core->>LLM: 消息 + 工具模式（本地或云端）
      LLM-->>Core: tool_calls（如 route_to_plugin, file_read, run_skill）或最终文本
      alt LLM 返回 tool_calls
        Core->>Tools: 执行 (file_read, memory_search, cron_schedule, route_to_plugin, run_skill, …)
        Tools->>Plugin: 若 route_to_plugin → 运行插件（参数来自档案/配置）
        Plugin-->>Tools: 插件结果
        Tools-->>Core: 工具结果
        Core->>Core: 将结果追加到消息，重复
      else LLM 返回最终文本
        Core->>Memory: 可选：写入记忆（嵌入）
        Core->>Core: 保存本轮对话历史
        Core->>Channel: 响应
      end
    end
  end
  Channel->>User: 回复
```

**图表说明摘要**

| 方面 | 在图中的位置 |
|--------|-------------------|
| **LLM：本地或云端** | 第一张图中的 **LLM 层**；序列图中的 **LLM（本地或云端）**。Core 调用统一的 OpenAI 兼容 API；该 API 由**本地**（llama.cpp、GGUF）或**云端**（LiteLLM → OpenAI、Gemini、DeepSeek 等）提供。主模型与嵌入模型可分别选择本地或云端。 |
| **记忆系统** | **记忆**子图：向量存储（Cognee 或 Chroma）、对话历史（SQLite）、可选知识库。**RAG**：嵌入模型对查询与记忆向量化；相关片段被取出并注入系统提示。 |
| **档案学习** | **档案**子图：每用户 JSON（如 `database/profiles/<user_id>.json`）。每次请求加载并作为**「关于用户」**注入提示；用于个性化及插件参数解析（`profile_key`）。 |
| **工具 / 技能 / 插件选择** | **上下文**包含：工作区（TOOLS.md）、**技能块**（SKILL.md 技能列表）、**路由块**（插件列表 +「择一：时间工具、route_to_tam、route_to_plugin、run_skill 或其他工具」）。**工具注册表**包含所有工具（file_read、memory_search、route_to_plugin、run_skill 等）。**LLM** 根据该上下文选择调用哪一工具（或直接回复文本）。选择由 **LLM** 根据提示与工具模式完成；无独立「选择器」服务。 |

- **渠道** — Email、Matrix、Tinode、WeChat、WhatsApp、Telegram、Discord、Slack、WebChat、webhook、Google Chat、Signal、iMessage、Teams、Zalo、Feishu、DingTalk、BlueBubbles。各渠道通过 HTTP（`/inbound`、`/process`）或 WebSocket（`/ws`）连接 Core。参见 [渠道](#2-homeclaw-能做什么) 与 `channels/README.md`。
- **Core** — 单一 FastAPI 应用：权限检查（`config/user.yml`）、编排器（意图 TIME vs OTHER；插件选择）、TAM（提醒、cron）、工具执行（文件、记忆、网页搜索、浏览器、cron、`route_to_plugin`、`run_skill`）、插件调用及对话 + RAG。配置：`config/core.yml`。
- **LLM 层** — Core 使用的统一 OpenAI 兼容 API。由**本地模型**（llama.cpp 服务、GGUF）和/或**云端模型**（LiteLLM：OpenAI、Google Gemini、DeepSeek、Anthropic、Groq、Mistral 等）提供。主模型与嵌入模型可独立选择。参见 `config/core.yml`（`local_models`、`cloud_models`、`main_llm`、`embedding_llm`）。
- **记忆** — **Cognee**（默认）或自研 **Chroma** 后端：向量 + 关系 + 可选图。用于 RAG 与对话历史。参见 `docs_design/MemoryAndDatabase.md`。
- **档案** — 每用户 JSON 存储（如 `database/profiles/`）。每次请求加载并作为「关于用户」注入提示；用于个性化与插件参数解析。参见 `docs_design/UserProfileDesign.md`。
- **插件** — 内置（Python，位于 `plugins/`）与外部（HTTP，任意语言）。当请求匹配时 Core 将用户意图路由到插件（如 Weather、News、Mail）。参见 [§5 插件](#5-插件扩展-homeclaw)。
- **技能** — 位于 `config/skills/` 下的文件夹，含 `SKILL.md`（名称、描述、工作流）。LLM 使用工具完成技能工作流；可选 `run_skill` 运行脚本。参见 [§6 技能](#6-技能用工作流扩展-homeclaw)。

完整设计参见 **Design.md**。工具、技能与插件的区别参见 **docs_design/ToolsSkillsPlugins.md**。

---

## 2. HomeClaw 能做什么？

### 通过不同渠道连接

您可以通过以下方式与 HomeClaw 对话：

- **WebChat** — 基于 WebSocket 的浏览器界面（`python -m channels.run webchat`，默认 http://localhost:8014）。
- **CLI** — 终端交互式对话（`python -m main start`）。
- **Telegram、Discord、Slack** — 入站机器人：在 `channels/<name>/.env` 中设置机器人令牌，在 `config/user.yml` 中添加您的用户 ID，运行 `python -m channels.run telegram`（或 `discord`、`slack`）。
- **Email、Matrix、Tinode、WeChat、WhatsApp** — 完整渠道；参见 `channels/README.md` 配置。
- **Webhook** — 任意客户端可向 webhook 的 `/message` 发送 POST 并获回复（转发到 Core `/inbound`）。适用于 Core 无法直接访问时（如 NAT 后）。

所有渠道共用同一 Core：一个智能体、一套记忆、一套插件与技能。参见 **docs_design/RunAndTestPlugins.md** 快速运行与测试。

### 多用户支持

Core 使用 `config/user.yml` 中的**允许列表**；只有列出的用户才能向 Core 发送消息。对话历史、记忆、知识库与档案数据均按**系统用户 id**（来自 `id` 或 `name`）区分，因此每个用户的数据彼此隔离。

**每用户字段：**

- **name**（必填）— 显示名称。
- **id**（可选）— 用于所有存储的唯一系统用户 id；省略时默认与 `name` 相同。
- **email** — 邮箱列表（用于邮件渠道）。
- **im** — IM 渠道身份列表：`"<channel>:<id>"`（如 `telegram_<chat_id>`、`discord_<user_id>`、`matrix:@user:domain`、`tinode:usrXXXX`、`wechat:wxid`）。
- **phone** — 电话号码列表（用于短信/电话渠道）。
- **permissions** — 可选（如 `[IM, EMAIL, PHONE]`）；空表示允许所有渠道类型。

**如何配置多用户**

1. **编辑** `config/user.yml`。在 `users:` 下为每个人（或每个身份）添加一条。
2. **渠道身份** — 各渠道会发送一个 `user_id`；Core 将其与该用户的 `email`、`im` 或 `phone` 匹配。使用渠道要求的格式：
   - **Telegram**：在 `im` 中添加 `telegram_<chat_id>`（用户发消息时从机器人或 Telegram API 获取 chat_id）。
   - **Discord**：在 `im` 中添加 `discord_<user_id>`（Discord 数字用户 id）。
   - **Slack**：在 `im` 中添加 `slack_<user_id>`。
   - **Matrix**：在 `im` 中添加 `matrix:@localpart:domain`（如 `matrix:@alice:matrix.org`）。
   - **WebChat / 入站**：客户端在 JSON 中发送 `user_id`；将该字符串加入 `im`（如 `webchat_local` 或 `webchat_<your_id>`）。
   - **Email**：将邮箱地址加入 `email:`。
3. **不可重叠** — 每个 email/im/phone 值最多只能出现在一个用户中（Core 加载时会校验）。同一人可有多个身份（如 Matrix + Telegram），可写在同一用户条目的 `im` 中，或两条条目用相同 `id`/`name` 表示同一逻辑用户。
4. **先匹配先得** — Core 找到第一个其 `email`/`im`/`phone` 包含请求 `user_id` 的用户；该用户的 `id`/`name` 即作为该请求的系统用户 id。

**示例**（两个用户：一个 Telegram，一个 Matrix + WebChat）：

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

完整行为（匹配逻辑、每用户数据、直接回复）参见 **docs_design/MultiUserSupport.md**。每用户档案（学习到的事实）参见 **docs_design/UserProfileDesign.md**。

### 安全与隐私：本地 vs 云端模型

- **本地模型** — 通过本机上的 llama.cpp 服务运行 GGUF 模型。数据留在本机；无需第三方 API。在 `config/core.yml` 的 `local_models` 下配置；将 `main_llm` 与 `embedding_llm` 设为如 `local_models/Qwen3-14B-Q5_K_M`。
- **云端模型** — 在 `config/core.yml` 的 `cloud_models` 下使用 LiteLLM。设置 `api_key_name`（如 `OPENAI_API_KEY`、`GEMINI_API_KEY`、`DEEPSEEK_API_KEY`）及对应环境变量。HomeClaw 将提示发送到您选择的提供商；隐私与条款以该提供商为准。
- **混合** — 可对话用本地模型、嵌入用云端模型（或反之）。通过 CLI 的 `llm set` / `llm cloud` 或编辑 `config/core.yml` 中的 `main_llm` / `embedding_llm` 切换。
- **远程访问** — 若将 Core 暴露到公网（如 WebChat 或机器人），请在 `config/core.yml` 中启用 **auth**：`auth_enabled: true` 与 `auth_api_key: "<secret>"`。客户端在 `/inbound` 与 `/ws` 上须发送 `X-API-Key` 或 `Authorization: Bearer <key>`。参见 **docs_design/RemoteAccess.md**。

支持的云端提供商（通过 LiteLLM）包括 **OpenAI**（GPT-4o 等）、**Google Gemini**、**DeepSeek**、**Anthropic**、**Groq**、**Mistral**、**xAI**、**Cohere**、**Together AI**、**OpenRouter**、**Perplexity** 等。参见 `config/core.yml` 与 [LiteLLM 文档](https://docs.litellm.ai/docs_design/providers)。

---

## 3. 如何使用 HomeClaw

**分步指南**（安装、配置、本地/云端模型、记忆、工具、工作区、测试、插件、技能）见 **[HOW_TO_USE_zh.md](HOW_TO_USE_zh.md)**（另有 [English](HOW_TO_USE.md) | [日本語](HOW_TO_USE_jp.md) | [한국어](HOW_TO_USE_kr.md)）。

### 支持平台

HomeClaw 支持 **macOS**、**Windows** 与 **Linux**。需要：

- **Python** 3.10–3.12（推荐）。
- **本地 GGUF 模型**：本机上的 **llama.cpp** 服务（或使用自带的 `llama.cpp-master` 并按配置启动服务）。
- **云端模型**：仅需网络与正确的 API 密钥环境变量。

### 快速开始（运行、配置、测试）

1. **克隆与安装**

   ```bash
   git clone <repo_url>
   cd <your_clone_folder>   # 如 HomeClaw 或 GPT4All
   pip install -r requirements.txt
   ```

2. **配置**

   - **Core**：`config/core.yml` — host、port（默认 9000）、`main_llm`、`embedding_llm`、`use_tools`、`use_skills`、`use_memory` 等。
   - **用户**：`config/user.yml` — 用户允许列表及渠道身份（email、im、phone）。
   - **渠道**：将 `channels/.env.example` 复制为 `channels/.env`；设置 `CORE_URL`（如 `http://127.0.0.1:9000`）及各渠道机器人令牌（如 `TELEGRAM_BOT_TOKEN`）。参见 `channels/README.md` 各渠道说明。

3. **模型**

   - **本地**：将 GGUF 模型（如从 Hugging Face）放入 `models/` 目录；在 `config/core.yml` 的 `local_models` 中配置 path、host、port。为每个使用的模型启动 llama.cpp 服务。或使用 **Ollama**：运行 Ollama 后，在 CLI 中使用 `llm download` 与 `llm set`。
   - **云端**：在 `config/core.yml` 的 `cloud_models` 中添加条目并设置 `api_key_name`；设置对应环境变量（如 `OPENAI_API_KEY`、`GEMINI_API_KEY`、`DEEPSEEK_API_KEY`）。将 `main_llm` 设为如 `cloud_models/OpenAI-GPT4o`。

4. **运行 Core**

   ```bash
   python -m core.core
   ```

   或运行交互式 CLI（Core + 内置渠道）：

   ```bash
   python -m main start
   ```

5. **运行渠道**（在另一终端）

   ```bash
   python -m channels.run webchat
   ```

   打开 http://localhost:8014（或显示的端口）。或按需运行 Telegram/Discord/Slack 等。

6. **测试**

   - 在 WebChat 或 CLI 中发送消息。工具/技能/插件测试参见 **docs_design/ToolsAndSkillsTesting.md** 与 **docs_design/RunAndTestPlugins.md**。
   - 检查配置与 LLM 连通性：`python -m main doctor`。

### 命令（交互式 CLI，`python -m main start`）

- **llm** — 列出模型；**llm set** — 切换本地模型；**llm cloud** — 设置云端 LLM；**llm download** — 通过 Ollama 拉取模型。
- **channel** — 帮助；**channel list** — 列出渠道；**channel run &lt;name&gt;** — 在后台启动渠道。
- **wechat user / whatsapp user / matrix user / email user** — 配置该渠道的允许用户。
- **reset** — 重置记忆与历史（或使用 Core API：`GET/POST http://127.0.0.1:9000/memory/reset`）。

### 示例：本地 GGUF 模型

将 GGUF 文件放入 `models/` 目录。在 `config/core.yml` 中为每个模型（及一个嵌入模型）在 `local_models` 中定义 `id`、`path`、`host`、`port`。将 `main_llm` 与 `embedding_llm` 设为如 `local_models/<id>`。为对应端口启动 llama.cpp 服务。示例模型链接（以 Hugging Face 最新为准）：

- **嵌入**（如 BGE-M3）：[bge-m3-Q5_K_M.gguf](https://huggingface.co/gpustack/bge-m3-GGUF/blob/main/bge-m3-Q5_K_M.gguf)
- **对话**：Qwen3-8B/14B/32B、Qwen2.5-7B/14B、Llama-3.2-3B/8B、GLM-4-9B/32B、Gemma-3-4B/12B/27B、DeepSeek-R1-Distill-Qwen-1.5B/7B/14B 等（在 Hugging Face 搜索「GGUF」并在 `local_models` 中设置 path）。

**已测试组合**：嵌入 **bge-m3-Q5_K_M.gguf**；对话 **Qwen3-14B-Q5_K_M.gguf**。二者搭配可用于本地 RAG 与对话。

### 本地模型放在哪、如何按系统选择

- **模型目录** — 在 `config/core.yml` 中，**`model_path`**（默认 `../models/`）是 GGUF 文件的根目录。**`local_models`** 中的 **`path`** 均**相对于 `model_path`**（如 `path: bge-m3-Q5_K_M.gguf` 或 `path: deepseek-r1/DeepSeek-R1-Distill-Qwen-14B-Q5_K_M.gguf`）。也可使用绝对路径。将所有 GGUF 文件放在该根目录下（如项目根目录的 `models/` 或 `../models/`）。
- **按系统选择模型** — 根据硬件选择模型大小与量化：
  - **仅 CPU**：建议较小模型（如 1.5B–7B）和较高量化（Q4_K_M、Q5_K_M）以保证速度；14B+ 可能较慢。
  - **GPU（如 8GB 显存）**：常见为 7B–14B Q4/Q5；32B 可能需要 Q4 或 offload。
  - **GPU（16GB+ 显存）**：可跑 14B–32B Q5 或 Q8；按显存调整。
  - **内存**：确保系统 RAM 足够容纳模型文件与 llama.cpp 进程（约 1–1.5 倍模型文件大小）。
- **配置** — 在 `config/core.yml` 的 **`local_models`** 下为每个模型添加一项：`id`、`path`（相对于 `model_path`）、`host`、`port`、`capabilities`（如 `[Chat]` 或 `[embedding]`）。将 **`main_llm`** 与 **`embedding_llm`** 设为 `local_models/<id>`（如 `local_models/Qwen3-14B-Q5_K_M`）。为每个模型在对应端口启动一个 llama.cpp 服务（见 `llama.cpp-master/README.md`）。运行时可通过 CLI **`llm set`**（本地）或 **`llm cloud`**（云端）切换主模型。

### 如何设置 OpenAI、Gemini 或其他云端 AI

- **配置** — 在 `config/core.yml` 中，**`cloud_models`** 列出各提供商，每项包含 `id`、`path`（LiteLLM 模型名，如 `openai/gpt-4o`、`gemini/gemini-1.5-pro`）、`host`、`port`、**`api_key_name`** 和 `capabilities`。将 **`main_llm`**（或 **`embedding_llm`**）设为 `cloud_models/<id>`（如 `cloud_models/OpenAI-GPT4o`、`cloud_models/Gemini-1.5-Pro`）。
- **API 密钥** — 对每个要使用的云端模型，在 Core 运行环境中设置与 **`api_key_name`** 对应的**环境变量**，例如：
  - **OpenAI**：`OPENAI_API_KEY`
  - **Google Gemini**：`GEMINI_API_KEY`
  - **DeepSeek**：`DEEPSEEK_API_KEY`
  - **Anthropic**：`ANTHROPIC_API_KEY`
  - **Groq**：`GROQ_API_KEY`
  - **Mistral**：`MISTRAL_API_KEY`
  - **xAI**：`XAI_API_KEY`
  - **OpenRouter**：`OPENROUTER_API_KEY`
  - （更多见 `config/core.yml` 与 [LiteLLM providers](https://docs.litellm.ai/docs_design/providers)。）
- **运行 LiteLLM** — 配置中每个云端条目有各自的 `host`/`port`。在该 host/port 上运行 LiteLLM 代理（或按提供商运行一个代理），提供 OpenAI 兼容的 `/v1/chat/completions` 与 `/v1/embeddings`，并配置对应 API 密钥。Core 只调用该 URL；API 密钥不写入 `core.yml`，仅写环境变量名。
- **运行时切换** — 使用 CLI **`llm cloud`** 选择云端模型作为主 LLM，或编辑 `config/core.yml` 中的 `main_llm` / `embedding_llm` 后重启 Core。

### 如何切换到企业级数据库（Postgres、Neo4j、企业向量库）

HomeClaw 使用**关系型 DB**（对话历史、会话）、**向量 DB**（RAG 记忆）和可选的**图 DB**（实体/关系）。可保持默认（SQLite、Chroma、可选 Kuzu）或切换到企业后端。

- **记忆后端** — 在 `config/core.yml` 中，**`memory_backend`** 为 **`cognee`**（默认）或 **`chroma`**（自研 RAG）。其余配置依此选择。
- **当 `memory_backend: cognee`**（默认）时：
  - 通过 **`cognee:`** 小节和/或 **Cognee 的 `.env`** 配置（见 [docs.cognee.ai](https://docs.cognee.ai/)）。`core.yml` 中的 **`vectorDB`** 与 **`graphDB`** 块**不**用于记忆。
  - **关系型**：默认 SQLite。使用 **PostgreSQL** 时，设置 `cognee.relational.provider: postgres` 及 `host`、`port`、`username`、`password`、`name`。安装：`pip install "cognee[postgres]"`。
  - **向量**：默认 ChromaDB。使用 **Qdrant**、**PGVector**、**LanceDB**、**Redis** 等时，设置 `cognee.vector.provider` 及对应 URL/凭据；安装对应 Cognee 扩展（如 `cognee[qdrant]`）。
  - **图**：默认 Kuzu。使用 **Neo4j** 或 **Neptune** 时，设置 `cognee.graph.provider` 及 URL/凭据；见 Cognee 文档。
- **当 `memory_backend: chroma`**（自研）时：
  - 所有存储均在 **`config/core.yml`** 的 **`database:`**、**`vectorDB:`**、**`graphDB:`** 下配置。
  - **关系型**：将 **`database.backend`** 设为 **`postgresql`**（或 `mysql`）并设置 **`database.url`**（如 `postgresql+psycopg2://user:password@host:5432/dbname`）。Core 的对话历史、会话与运行将使用 Postgres。
  - **向量**：将 **`vectorDB.backend`** 设为 **`qdrant`**、**`milvus`**、**`pinecone`** 或 **`weaviate`**，并填写对应块（host、port、url、api_key 等）。
  - **图**：将 **`graphDB.backend`** 设为 **`neo4j`**，并设置 **`graphDB.Neo4j.url`**、`username`、`password` 以使用企业图存储。
- **Core 的对话 DB** — **`database:`** 小节始终用于 Core 自身的对话历史、会话与运行。因此即使 `memory_backend: cognee`，也可设置 `database.backend: postgresql` 和 `database.url`，将 Core 的关系型数据放到 Postgres。

完整支持矩阵与分步示例见 **docs_design/MemoryAndDatabase.md**。

### 开发者（Windows 说明）

- **Visual C++ Build Tools** 在 Windows 上可能为部分依赖所需。参见 [安装 Visual Studio Build Tools](https://github.com/bycloudai/InstallVSBuildToolsWindows)。
- **WeChat 渠道**：支持的微信版本与配置见 CLI（`channel` 命令）。运行 `python -m channels.run wechat` 并使用 `wechat user` 添加允许用户。

### 中国开发者

可使用国内 pip 镜像加速安装，例如：

- 清华大学：https://pypi.tuna.tsinghua.edu.cn/simple/
- 阿里云：http://mirrors.aliyun.com/pypi/simple/

---

## 4. 技能与插件：让 HomeClaw 为您服务

HomeClaw 自带**工具**（文件、记忆、网页搜索、cron、浏览器等）、**插件**（如 Weather、News、Mail）和**技能**（在 SKILL.md 中描述的工作流）。它们共同实现：

- **回答与记忆** — 主 LLM 使用 RAG（记忆）与对话历史回答；可通过工具或自然语言存储/回忆。
- **专注一事** — 询问天气、新闻或发邮件；编排器将请求路由到对应**插件**并返回结果。
- **运行工作流** — 在 `config/core.yml` 中启用**技能**（`use_skills: true`）。LLM 会看到「可用技能」并按技能说明使用工具，或调用 **run_skill** 运行脚本。
- **日程与提醒** — 使用 **TAM**（时间感知模块）：说「5 分钟后提醒我」或「每天 9 点」；或使用工具 `remind_me`、`record_date`、`cron_schedule`。

无需按名称「调用」插件或技能，自然表达即可。系统在意图匹配时路由到插件，在模型决定时使用工具/技能。LLM 如何在工具、技能与插件间选择参见 **docs_design/ToolsSkillsPlugins.md**。

---

## 5. 插件：扩展 HomeClaw

**插件**是单一功能模块：一个插件对应一种能力（如天气、新闻、邮件、自定义 API）。

### 内置插件（Python）

- 位于 `plugins/<Name>/`，包含 **plugin.yaml**（id、描述、能力）、**config.yml**（API 密钥、默认值）和 **plugin.py**（继承 `BasePlugin` 的类）。
- Core 在启动时自动发现；无需注册。示例：**Weather**（`plugins/Weather/`）、**News**（`plugins/News/`）、**Mail**（`plugins/Mail/`）。
- LLM 在路由块中看到插件列表，在用户意图匹配时调用 **route_to_plugin(plugin_id)**。Core 调用插件并将响应返回渠道。

### 外部插件（任意语言）

- 以独立 **HTTP 服务**运行（Node.js、Go、Java、Python 等），实现：
  - `GET /health` → 2xx
  - `POST /run`（或自定义路径）→ 请求体为 PluginRequest JSON，响应为 PluginResult JSON。
- **向 Core 注册**：`POST http://<core>:9000/api/plugins/register`，提交插件 id、name、description、`health_check_url`、`type: "http"`、`config`（base_url、path、timeout_sec）及 `capabilities`。
- 注册后 Core 会像内置插件一样将请求路由到您的服务。参见 **docs_design/PluginStandard.md** 与 **docs_design/PluginsGuide.md**。

### 示例：多语言外部插件

在 `examples/external_plugins/` 中提供：

- **Python** — Quote（端口 3101）、Time（端口 3102）。
- **Node.js** — Quote（端口 3111）。
- **Go** — Time（端口 3112）。
- **Java** — Quote（端口 3113）。

每个目录有 README 与注册脚本。参见 **examples/external_plugins/README.md** 与 **docs_design/RunAndTestPlugins.md**。

### 参数收集

插件可声明参数（如城市、收件人）。Core 可从**用户档案**、**配置**或**用户消息**中填充；可选 **confirm_if_uncertain** 与 **use_default_directly_for** 控制确认行为。参见 **docs_design/PluginsGuide.md** 与 **docs_design/PluginParameterCollection.md**。

---

## 6. 技能：用工作流扩展 HomeClaw

**技能**是应用式能力：每个技能是 `config/skills/` 下的一个**文件夹**，内含 **SKILL.md**（名称、描述及可选的使用工具说明）。

- **作用** — LLM 在系统提示中看到「可用技能」。当用户请求与某技能描述匹配时，LLM 使用**工具**（file_read、web_search、browser、cron 等）完成工作流。若技能有 **scripts/** 文件夹，LLM 可调用 **run_skill(skill_name, script, ...)** 运行脚本（如 `run.sh`、`main.py`）。
- **无独立运行时** — 技能不在单独进程中运行；「运行时」即主 LLM + 工具循环。因此技能是**工具驱动的工作流**。
- **启用** — 在 `config/core.yml` 中：`use_skills: true`、`skills_dir: config/skills`。可选 **skills_use_vector_search** 使仅与查询相似的技能被注入。参见 **docs_design/SkillsGuide.md** 与 **docs_design/ToolsSkillsPlugins.md**。

例如：「社交媒体代理」技能可描述如何使用浏览器与 cron 在 X/Twitter 发帖；LLM 按技能说明调用相应工具。

---

## 7. 致谢

HomeClaw 的诞生离不开两个项目的启发：

- **GPT4People** — 作者早先的项目，探索去中心化、以人为中心的 AI 与基于渠道的交互。HomeClaw 的许多想法——本地优先智能体、渠道、记忆以及「为人们服务」的愿景——都源于此。
- **OpenClaw** — 姊妹生态（网关、扩展、渠道、提供商）。OpenClaw 与 HomeClaw 理念相近：可扩展、基于渠道的 AI，用户可自运行与定制。OpenClaw 的网关/扩展模式与 HomeClaw 的 Core/插件模式的对比，帮助厘清了 HomeClaw 的设计（参见 **docs_design/ToolsSkillsPlugins.md** §2.7）。

感谢所有为 GPT4People 与 OpenClaw 做出贡献的人，以及 llama.cpp、LiteLLM、Cognee 与众多渠道与工具背后的开源社区。

---

## 8. 贡献与许可

- **贡献** — 欢迎提交 issue、Pull Request 与讨论。参见 **CONTRIBUTING.md**。
- **许可** — 本项目采用 **Apache License 2.0**。见 **LICENSE** 文件。

### 路线图（摘要）

**下一步**

- **本地与云端模型混合** — 设计如何将本地模型与云端模型结合使用：既高效又降低成本（例如：简单或高量任务用本地，复杂或低延迟需求用云端；路由与回退规则）。

**后续**

- 更简单的安装与入门（`python -m main onboard`、`python -m main doctor`）。
- 更多渠道与平台集成。
- 更强的插件/技能发现与多智能体选项。
- 可选：目录、信任/声誉与基于区块链的智能体间验证。

我们刚刚启程。欢迎持续关注与参与。
