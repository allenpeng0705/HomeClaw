# HomeClaw — 设计文档

本文描述 **HomeClaw** 的架构、组件与数据流，作为理解项目与后续开发的基础参考。

**其他语言：** [English](Design.md) | [日本語](Design_jp.md) | [한국어](Design_kr.md)

---

## 1. 项目概述

### 1.1 目的

**HomeClaw** 是一款**本地优先的 AI 助手**，具有以下特点：

- 运行在用户本机（如家庭电脑）。
- 支持**本地 LLM**（通过 llama.cpp 服务）与**云端 AI**（通过 OpenAI 兼容 API，使用 **LiteLLM**）。
- 通过**多种渠道**（邮件、IM、CLI）暴露助手，使用户可从任意位置（如手机）与家中实例交互。
- 使用 **RAG 式记忆**：**Cognee**（默认）或自管 SQLite + Chroma；可选每用户**档案**与**知识库**。见 docs/MemoryAndDatabase.md。
- 通过**插件**（plugin.yaml + config.yml + plugin.py；route_to_plugin 或 orchestrator）、**技能**（config/skills/ 下的 SKILL.md；可选向量检索；run_skill 工具）与**工具层**（use_tools: true — exec、browser、cron、sessions_*、memory_*、file_* 等）扩展行为。见 docs/ToolsSkillsPlugins.md。

### 1.2 设计目标

- **本地优先**：主要在本机运行；云端可选。
- **部署简单**：依赖最少（默认 SQLite、Chroma，无重型 DB）。
- **渠道无关**：无论用户通过邮件、Matrix、Tinode、WeChat、WhatsApp 还是 CLI 连接，同一 Core。
- **可扩展**：通过插件增加功能；未来可有专用 HomeClaw 渠道。
- **多模型**：对话与嵌入可使用不同模型；通过配置加载多个模型。

---

## 2. 高层架构

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

- **渠道**将用户输入以 `PromptRequest` 通过 HTTP 发给 **Core**。
- **Core** 要么自行处理（对话 + 记忆/RAG），要么路由到**插件**。
- **LLM** 调用统一走一个端点：本地 llama.cpp 服务或 LiteLLM 代理（同一 OpenAI 兼容 API）。
- **Memory** 存储对话与用于 RAG 的向量化知识。

---

## 3. 核心组件

### 3.1 Core 引擎（`core/`）

- **角色**：中央路由、权限校验与对话 + 记忆处理。
- **入口**：`core/core.py` — `Core`（单例）运行 FastAPI 应用并启动 LLM 管理器。
- **主要端点**：`POST /process`（渠道异步）、`POST /local_chat`（CLI 同步）、`POST /inbound`（任意机器人最小 API）、`WebSocket /ws`、`POST /register_channel`、`POST /deregister_channel`。
- **行为**：校验权限（config/user.yml）→ 若启用 orchestrator + 插件则做意图分类与插件选择 → 否则由 Core 处理：加载聊天历史、可选入队记忆、RAG（answer_from_memory）、调用 LLM、写回聊天 DB 并回复渠道。
- **配置**：`config/core.yml`（host、port、main_llm、embedding_llm、memory_backend、use_tools、use_skills、tools.*、result_viewer、auth_enabled、auth_api_key 等）。**认证**：auth_enabled: true 时，/inbound 与 /ws 需 X-API-Key 或 Authorization: Bearer；见 docs/RemoteAccess.md。**结果查看器**：可选 save_result_page 工具与报告服务（port、base_url）；见 docs/ComplexResultViewerDesign.md。

**Orchestrator**（`core/orchestrator.py`）：根据聊天历史与用户输入分类意图（TIME/OTHER）；对 OTHER 由 Core 选择插件。**TAM**（`core/tam.py`）：时间感知模块，处理 TIME 意图（如定时）。路由风格由 core.yml 中 **orchestrator_unified_with_tools** 控制（默认 true = 主 LLM 带工具做路由；false = 单独 orchestrator 先跑一轮 LLM）。

**单 Core、多 LLM（本地 + 云端）**：配置中 `local_models`、`cloud_models`；`main_llm`、`embedding_llm` 为引用（如 local_models/xxx 或 cloud_models/xxx）。运行时 Util.main_llm()、Util.get_llm(name) 解析；可选 llm_name 按调用切换模型。**sessions_spawn** 工具可指定 llm_name 用不同模型做一次性子任务。

**单 agent 与多 agent**：当前为**单 agent**（一套身份、工具集、技能集）；可演进为多 agent（每 agent 独立 identity、工具子集、技能子集及可选默认 LLM）。推荐默认保持「单 agent、多 LLM」。

### 3.2 渠道（`channels/`、`main.py`，Core `/inbound` 与 `/ws`）

用户或机器人通过渠道接触 Core。HomeClaw 支持两种模式：**完整渠道**（独立进程、BaseChannel、异步/同步回复）与**最小模式**（无 BaseChannel 进程，直接 POST /inbound 或 WebSocket /ws 得同步回复）。权限统一用 `config/user.yml`。

**已有渠道**：Email、Matrix、Tinode、WeChat、WhatsApp、Telegram、Discord、Slack、WebChat、Google Chat、Signal、iMessage、Teams、Zalo、Feishu、DingTalk、BlueBubbles、CLI（main.py）。运行任意渠道：`python -m channels.run <name>`。详见 Design.md §3.2。

**Webhook 与 WebSocket**：Core `POST /inbound`（最小 HTTP API）；Webhook 渠道 `POST /message` 中继；Core `WebSocket /ws` 供自有客户端（如 WebChat）。新增机器人推荐：向 Core `/inbound` 或 Webhook `/message` 发 `{ user_id, text }`，将返回的 text 发回用户；在 user.yml 中登记 user_id。

### 3.3 LLM 层（`llm/`）

- **角色**：将本地与云端 LLM 统一为 Core 使用的同一套 OpenAI 兼容 API。
- **配置**：`config/core.yml` 中 `llama_cpp`、`local_models`（数组）、`cloud_models`（数组）及选定的 `main_llm`、`embedding_llm`（按 id）。本地：llama-server 按条目 host/port 启动；二进制从 **llama.cpp-master/** 对应平台子目录自动选择，见 llama.cpp-master/README.md。云端：LiteLLM；每个 cloud_models 条目有 **api_key_name**，在 Core 运行环境中设置**同名环境变量**，勿在 core.yml 中写密钥。

### 3.4 记忆（`memory/`）

- **角色**：聊天历史 + RAG（存储与检索与当前查询相关的历史内容）。
- **设计**：**Cognee（默认）**：默认 SQLite + ChromaDB + Kuzu；可通过 Cognee `.env` 使用 Postgres、Qdrant 等。**自管（chroma）**：core.yml 中 SQLite + Chroma + 可选 Kuzu/Neo4j。见 docs/MemoryAndDatabase.md。
- **memory_backend**：`cognee`（默认）或 `chroma`。cognee 时通过 **cognee:** 与/或 Cognee `.env` 配置；chroma 时使用 core.yml 的 vectorDB、graphDB。**database** 始终用于 Core 的聊天会话、runs、轮次。**profile**（可选）：每用户 JSON；profile.enabled、profile.dir。**knowledge_base**（可选）：独立于 RAG 记忆；knowledge_base.enabled、knowledge_base.backend。
- **工作区引导（可选）**：`config/workspace/` 下 IDENTITY.md、AGENTS.md、TOOLS.md；由 base/workspace.py 加载并拼入系统提示。core.yml：use_workspace_bootstrap、workspace_dir。
- **会话记录**：ChatHistory.get_transcript、get_transcript_jsonl、prune_session、Core.summarize_session_transcript 等；见 Comparison.md §7.6。
- **最近渠道存储**：base/last_channel.py — save_last_channel、get_last_channel；用于 channel_send 与插件回复到正确渠道。

### 3.5 插件（`plugins/`）

- **角色**：在 Core 不打算用通用对话 + RAG 直接回答时，由**路由到插件**（route_to_plugin 或 orchestrator）做专项处理。

**内置插件 vs 外部插件**

| 类型 | 语言 | 运行位置 | 清单 | 适用场景 |
|------|------|----------|------|----------|
| **内置** | 仅 Python | 与 Core 同进程 | `plugin.yaml` 中 **type: inline**，`config.yml`，`plugin.py`（继承 BasePlugin）置于 `plugins/<Name>/` | 快速集成、无额外进程、使用 Python 库（如 Weather、News、Mail）。 |
| **外部** | 任意（Node.js、Go、Java 等） | 独立进程或远程 HTTP 服务 | 在 `plugins/` 下目录中 `plugin.yaml` 设 **type: http**，或通过 **POST /api/plugins/register** 注册 | 已有服务、其他语言或独立部署；服务接受 POST PluginRequest 并返回 PluginResult。 |

Core 通过扫描 `plugins/` 并加载 plugin.yaml + plugin.py 发现**内置**插件；**外部**插件通过在目录中声明（plugin.yaml type: http + 端点 URL）或运行时 API 注册。两者路由方式相同（orchestrator 或 route_to_plugin）。见 **docs/PluginsGuide.md**（§2 内置、§3 外部）、**docs/PluginStandard.md**、**docs/RunAndTestPlugins.md**。

- **清单**：**plugin.yaml**（id、name、description、**type: inline** 或 **type: http**、capabilities 及参数）。**config.yml** 为运行时配置。**plugin.py**（仅内置）— 继承 BasePlugin，实现 run() 和/或能力方法。**加载**：PluginManager 扫描 plugins/，加载 plugin.yaml（及 type: inline 时的 plugin.py），注册描述；Core 用 LLM 匹配用户文本或 **route_to_plugin** 调用，内置走 plugin.run()，外部走 HTTP POST。

### 3.6 插件与工具：区别与设计

**插件** = 将本条消息路由到一个处理器，执行后返回响应。**工具** = 模型按名称与结构化参数调用函数；执行后结果回填，模型可继续调用或回复。HomeClaw 已实现**工具层**（exec、browser、cron、sessions_*、memory_*、file_*、document_read、web_search、run_skill、route_to_plugin、route_to_tam、save_result_page、models_list、agents_list、channel_send、image；remind_me、record_date、recorded_events_list；profile_*、knowledge_base_*；tavily_extract/crawl/research、web_extract、web_crawl、web_search_browser、http_request 等）；nodes/canvas 不在范围内。完整列表见 **Design.md §3.6**。见 **docs/ToolsSkillsPlugins.md**、**Comparison.md** §7.10.2。

- **实现**：`base/tools.py`（ToolDefinition、ToolContext、ToolRegistry）、`tools/builtin.py`（register_builtin_tools）；Core 在 initialize() 中注册，在 answer_from_memory 中当 use_tools 为 true 时带工具调用并执行 tool_calls 循环。**配置**：core.yml 中 **use_tools: true** 及 **tools:**（exec_allowlist、file_read_base、tools.web、browser_*、run_skill_* 等）。见 **docs/ToolsDesign.md**、**docs/ToolsAndSkillsTesting.md**。新增工具：定义 execute_async、构造 ToolDefinition、在 register_builtin_tools 中或通过 get_tool_registry().register(tool) 注册。

---

## 4. 端到端流程

### 4.1 用户发送消息（如通过邮件或 IM）

渠道接收消息 → 构建 PromptRequest → 调用 Core POST /process（或 CLI 用 POST /local_chat）→ Core 校验权限 → 若启用 orchestrator 则意图分类与插件选择并执行插件或由 Core 处理 → 若 Core 处理：加载聊天历史、可选入队记忆、answer_from_memory（取记忆 Cognee/Chroma、调 LLM；use_tools 时执行 tool_calls 循环）、写回聊天 DB、将 AsyncResponse 推到 response_queue → 渠道从 /get_response 取回复并送达用户。

### 4.2 本地 CLI（`main.py`）

用户运行 main.py 在控制台输入；Core 在后台线程运行；CLI 使用 local_chat（同步），回复在 HTTP 体中返回并打印。前缀 `+`/`?` 可映射为记忆存储/检索。

---

## 5. 配置摘要

| 文件 | 用途 |
|------|------|
| `config/core.yml` | **单一配置**：host/port、model_path、local_models、cloud_models、main_llm、embedding_llm、memory_backend、cognee:、database、vectorDB/graphDB（chroma 时）、use_memory、use_workspace_bootstrap、workspace_dir、use_tools、tools:、use_skills、skills_dir、skills_use_vector_search、profile、knowledge_base、result_viewer、auth_enabled、auth_api_key 等。见 HOW_TO_USE.md。 |
| `config/user.yml` | 允许列表：用户（id、name、email、im、phone、permissions）；所有聊天/记忆/档案按系统用户 id 区分。 |
| `config/email_account.yml` | 邮件渠道 IMAP/SMTP 与凭证。 |
| `channels/.env` | CORE_URL、各渠道机器人 token。 |

Core 从 core.yml 读取 main_llm、embedding_llm（id），并从 local_models 或 cloud_models 解析 host/port 与类型。本地模型 path 相对于 model_path。llama.cpp 服务端二进制放在 **llama.cpp-master/** 对应平台子目录（mac/、win_cuda/、linux_cpu/ 等）；见 llama.cpp-master/README.md。云端 API 密钥：设置与各 cloud 模型 **api_key_name** 同名的**环境变量**（如 OPENAI_API_KEY）。

---

## 6. 扩展点与后续工作

- **渠道**：最小 — 任意机器人 POST /inbound 或 Webhook /message；完整 — 在 channels/ 下新增 BaseChannel 子类并实现 /get_response。专用 app 可用 WebSocket /ws。
- **LLM**：在 core.yml 的 local_models 或 cloud_models 中增加条目；本地按条目启动 llama-server。
- **记忆/RAG**：默认 Cognee；替代为 memory_backend: chroma。见 docs/MemoryAndDatabase.md。
- **插件**：在 plugins/ 下新增目录，含 plugin.yaml、config.yml、plugin.py（内置）或 type: http + 端点（外部）；外部也可 POST /api/plugins/register。见 docs/PluginsGuide.md、docs/PluginStandard.md、docs/RunAndTestPlugins.md。
- **工具层**：见 §3.6；已实现内置工具；可选让插件通过 get_tools()/run_tool() 暴露工具。
- **技能（SKILL.md）**：已实现；base/skills.py 从 config/skills/ 加载；use_skills、skills_dir、skills_use_vector_search；run_skill 工具。见 docs/SkillsGuide.md、docs/ToolsSkillsPlugins.md。
- **TAM**：时间意图已分类；可扩展更多定时/提醒行为与集成。

---

## 7. 关键文件速查

| 领域 | 关键文件 |
|------|----------|
| Core | core/core.py、core/coreInterface.py、core/orchestrator.py、core/tam.py |
| Channels | base/BaseChannel.py、base/base.py（InboundRequest）、channels/、main.py。运行：`python -m channels.run <name>`。 |
| LLM | llm/llmService.py、llm/litellmService.py |
| Memory | memory/base.py、memory/mem.py、memory/chroma.py、memory/storage.py、memory/embedding.py、memory/chat/chat.py；memory/graph/（chroma 时）；memory/cognee_adapter.py（cognee 时）；base/profile_store.py、database/profiles/；知识库见 core.yml。工作区：base/workspace.py、config/workspace/。技能：base/skills.py、config/skills/；run_skill 在 tools/builtin.py。见 docs/MemoryAndDatabase.md、docs/SkillsGuide.md。 |
| Tools | base/tools.py、tools/builtin.py；配置见 core.yml tools:。见 docs/ToolsDesign.md、docs/ToolsAndSkillsTesting.md。 |
| Plugins | base/BasePlugin.py、base/PluginManager.py、plugins/Weather/（plugin.yaml、config.yml、plugin.py）；外部：POST /api/plugins/register。见 docs/PluginsGuide.md、docs/PluginStandard.md。 |
| Shared | base/base.py（PromptRequest、AsyncResponse、枚举、配置数据类）、base/util.py |

---

本文档反映当前代码库，旨在作为 HomeClaw 进一步开发与重构的基础文档。
