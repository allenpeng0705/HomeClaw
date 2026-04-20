# HomeClaw Architecture Overview

## 1. What is HomeClaw?

HomeClaw is a **self-hosted AI assistant** that runs locally on a user's machine (desktop, server, NAS). It combines local LLMs with cloud LLMs via a hybrid routing system, supports multiple communication channels (Telegram, Discord, Slack, etc.), and provides a companion mobile app.

**Key characteristics:**
- Runs entirely on-premises — no cloud dependency
- Hybrid local/cloud LLM routing for cost and privacy
- Multi-channel: chat via many messaging platforms + native companion app
- Skill-based extensibility with a marketplace (ClawHub)
- E2E-encrypted federated messaging between users
- Developer bridge for IDE integration (Cursor, Claude Code, Trae)

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User (Human)                          │
│         ┌──────────┐  ┌──────────────────────┐         │
│         │Companion │  │  Messaging Channels  │         │
│         │App (Flutter)│ │  (Telegram/Discord/etc.) │  │
│         └────┬─────┘  └──────────┬───────────┘         │
└──────────────┼──────────────────────┼───────────────────┘
               │                      │
               │ HTTP/WebSocket       │ HTTP/Webhook
               ▼                      ▼
┌──────────────────────────────────────────────────────────┐
│                      HomeClaw Core                       │
│  ┌─────────────────────────────────────────────────┐   │
│  │              FastAPI Server (core.py)           │   │
│  │   - REST API (/inbound, /config, /files, etc.) │   │
│  │   - WebSocket endpoint (/ws)                    │   │
│  │   - Channel webhook handlers                     │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │              LLM Loop (llm_loop.py)             │   │
│  │   - Intent Router → Category                     │   │
│  │   - Skill Router → Filtered skills               │   │
│  │   - Hybrid Router → Local vs Cloud LLM           │   │
│  │   - Tool execution loop (ReAct)                  │   │
│  │   - Skill invocation (DAG)                      │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐    │
│  │  Memory    │  │  Tools    │  │   Plugins      │    │
│  │  (RAG+SQLite│  │  Registry │  │   Manager     │    │
│  │  +Graph)   │  │           │  │               │    │
│  └────────────┘  └────────────┘  └────────────────┘    │
│  ┌─────────────────────────────────────────────────┐   │
│  │           Skill System (skills.py)              │   │
│  │   - SKILL.md per folder                         │   │
│  │   - Vector store sync                            │   │
│  │   - Skill router (semantic search)               │   │
│  └─────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────┐
│              External Services                            │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ Local LLM    │  │ Cloud LLM    │  │ Vector DB   │  │
│  │ (llama.cpp   │  │ (OpenAI/     │  │ (Chroma/    │  │
│  │ /Ollama)     │  │ DeepSeek)    │  │ LanceDB)    │  │
│  └──────────────┘  └──────────────┘  └─────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Directory Structure

```
HomeClaw/
├── main.py                    # CLI entry point (start, onboard, doctor, etc.)
├── core/
│   ├── core.py                # Main FastAPI app, Core singleton, ~2500+ lines
│   ├── llm_loop.py            # ReAct tool loop, answer_from_memory, ~5100+ lines
│   ├── orchestrator.py        # Intent classification (TIME vs OTHER)
│   ├── inbound_handlers.py   # Request handling for POST /inbound and WebSocket
│   ├── tam.py                 # Time/Action/Memory scheduler (reminders/cron)
│   ├── routes/                # FastAPI route modules
│   │   ├── auth.py
│   │   ├── config_api.py
│   │   ├── files.py
│   │   ├── memory_routes.py
│   │   ├── plugins_api.py
│   │   ├── websocket_routes.py
│   │   └── ...
│   ├── skill_subagent.py     # Sub-agent for skill execution
│   ├── clawcode_*.py         # ClawCode IDE integration
│   └── ...
├── base/
│   ├── intent_router.py       # Category classification (LLM-based)
│   ├── intent_category_router.py  # Category doc loading/merging
│   ├── skill_router.py        # Semantic skill filtering
│   ├── tools.py               # Tool registry and execution
│   ├── skills.py              # Skill loading, vector store sync
│   ├── PluginManager.py       # Plugin discovery and lifecycle
│   ├── tool_profiles.py       # Tool allowlists per category
│   ├── planner_executor.py    # DAG-based planner
│   ├── router_reranker.py     # LLM-based reranking
│   └── ...
├── hybrid_router/
│   ├── heuristic.py           # Layer 1: keyword/long-input rules
│   ├── semantic.py            # Layer 2: semantic-router library
│   ├── slm.py                 # Layer 3: small classifier model
│   ├── perplexity.py           # Layer 3 alt: perplexity probe
│   ├── metrics.py             # Metrics + A/B experiments
│   └── template_expander.py    # {{a|b}} rule template expansion
├── memory/
│   ├── mem.py                 # Memory class (vector + graph + SQLite history)
│   ├── chat/                  # Chat history (SQLite)
│   │   ├── message.py         # ChatMessage dataclass
│   │   └── chat.py            # ChatHistory CRUD
│   ├── embedding.py           # Embedding service (llama.cpp)
│   ├── llm.py                  # Memory LLM (summarization, etc.)
│   ├── prompts.py              # Prompt templates
│   └── instructor_patch.py     # Instructor/litellm compatibility patch
├── tools/                     # Built-in tool implementations
│   └── builtin.py              # register_builtin_tools()
├── channels/                  # Channel adapters (Telegram, Discord, etc.)
│   ├── telegram_channel.py
│   ├── discord_channel.py
│   └── ...
├── portal/                    # Web configuration UI (separate FastAPI app)
│   └── app.py
├── clients/
│   └── HomeClawApp/           # Flutter companion app
│       └── lib/
│           ├── core_service.dart  # API/WebSocket client (~3000 lines)
│           ├── screens/           # UI screens
│           ├── widgets/          # Shared widgets
│           ├── models/           # Data classes
│           └── utils/            # Utilities
├── config/
│   ├── core.yml                # Main configuration
│   ├── user.yml                # User/auth config
│   ├── peers.yml               # Federated friends
│   ├── skills_and_plugins.yml  # Tool/skill profiles
│   └── hybrid/
│       └── heuristic_rules.yml  # Hybrid router Layer 1 rules
├── docs_design/                # Architecture and design documents
└── vendor/                    # Vendored dependencies (cognee)
```

---

## 4. Request Flow

When a user sends a message through any channel:

```
User Message
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. Inbound Handler (inbound_handlers.py)                  │
│    - Decode request (text, images, channel metadata)      │
│    - Load user session + chat history                    │
│    - Resolve user identity (system_user_id)             │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 2. Intent Router (intent_router.py)                     │
│    - Classifies into categories via small LLM call       │
│    - Categories: search_web, list_files, weather, etc.  │
│    - Modes: static (keyword only), semantic, hybrid     │
│    - Categories → filtered tool/skills lists            │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 3. Hybrid Router (hybrid_router/)                        │
│    Cascade (first-match by default):                     │
│    a) Vision override: images + no local vision → cloud │
│    b) Scheduling: time queries → cloud                   │
│    c) Heuristic: keyword/long-input rules → local/cloud │
│    d) Semantic: semantic-router (local/cloud utterances)│
│    e) SLM: small classifier or perplexity probe        │
│    f) Default route fallback                            │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 4. Skill Router (skill_router.py)                      │
│    - Semantic vector search over skill SKILL.md         │
│    - Union: trigger-matched + lexical-overlap skills    │
│    - Optional LLM reranking                             │
│    - Category-filtered skills from Phase 3.1           │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 5. LLM Loop (llm_loop.py / answer_from_memory)         │
│    ReAct tool loop:                                      │
│    a) Build prompt: system + history + tools + skills   │
│    b) Call main LLM (local or cloud)                  │
│    c) If no tool_calls → return answer                  │
│    d) If tool_calls → execute tools (ToolContext)       │
│    e) Append results, repeat until done or max_rounds   │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 6. Output Formatting (markdown_outbound.py)             │
│    - Render response for channel (Markdown, HTML, etc.) │
│    - Save long outputs (slides, PDFs) to files          │
│    - Return via channel (Telegram Bot API, WS, etc.)   │
└─────────────────────────────────────────────────────────┘
```

---

## 5. LLM Routing (Hybrid Router)

The hybrid router decides whether to use local or cloud LLM for each request.

### Cascade Layers

| Layer | Name | Purpose | Config |
|-------|------|---------|--------|
| 0 | Vision override | Images + no local vision → cloud | Always on |
| 1 | Scheduling | Time/reminder queries → cloud | Always on |
| 2 | Heuristic | Keyword/long-input rules | `hybrid_router.heuristic.enabled` |
| 3 | Semantic | semantic-router library | `hybrid_router.semantic.enabled` |
| 4 | SLM | Classifier or perplexity probe | `hybrid_router.slm.enabled` |
| 5 | Default | Fallback route | `hybrid_router.default_route` |

### Cascade Modes

- **`first-match`** (default): First layer to produce a result wins
- **`priority`**: All layers run, picks by priority order (vision=1, scheduling=2, heuristic=10, semantic=20, default_route=30, slm=40/41)

### Perplexity Probe

Measures local model's confidence using log probabilities. If avg logprob ≥ threshold → local, else → cloud.

### Configuration

```yaml
hybrid_router:
  default_route: local  # or cloud
  cascade_mode: first-match  # or priority
  heuristic:
    enabled: true
    rules_path: config/hybrid/heuristic_rules.yml
  semantic:
    enabled: true
    threshold: 0.5
    routes_path: config/hybrid/semantic_routes.yml
  slm:
    enabled: false
    mode: classifier  # or perplexity
    perplexity_threshold: -0.4
  experiment_id: null  # enables A/B tracking
```

---

## 6. Tool System

Tools are defined in `skills_and_plugins.yml` and `config/intent_category/*.md`.

### Tool Execution Flow

```
LLM returns tool_calls: [{"name": "web_search", "arguments": {...}}]
    │
    ▼
ToolRegistry.get_tool("web_search") → ToolDefinition
    │
    ▼
ToolContext.build(params, user_id, chat_id) → validated params
    │
    ▼
ToolDefinition.execute(context) → ToolResult
    │
    ▼
Result appended to LLM history, loop repeats
```

### Key Features

- **Permission evaluation**: `tool_permissions.py` checks user permissions before execution
- **Retry logic**: Built-in retry with exponential backoff for transient failures
- **Timeout**: Per-tool timeout prevents hanging (default 120s)
- **Streaming**: Some tools support streaming responses
- **Tool profiles**: Tool allowlists per intent category

---

## 7. Skill System

Skills are directories with a `SKILL.md` file containing metadata and instructions.

### SKILL.md Frontmatter

```yaml
---
name: Weather Skill
description: Get weather forecast for a location
trigger:
  patterns:
    - "weather in *"
    - "天气预报 *"
category: weather
auto_invoke:
  tool: run_skill
  arguments:
    skill_name: weather
    query: "{{query}}"
---
# Weather Skill

Instructions for getting weather data...
```

### Skill Loading

1. `skills.py` scans `skills/` directories (internal + external)
2. Parses SKILL.md frontmatter for metadata
3. Syncs to vector store for semantic search
4. Skill router uses vector search + trigger patterns + lexical overlap

### Skill Invocation

Skills run as DAGs defined in `config/skills/` or inline via `run_skill` tool. The planner (`planner_executor.py`) can create execution DAGs for multi-step tasks.

---

## 8. Plugin System

Plugins extend HomeClaw via HTTP, subprocess, or MCP (Model Context Protocol).

### Plugin Types

- **Inline**: Python code executed directly
- **HTTP**: External webhook called via HTTP
- **Subprocess**: Shell command executed locally
- **MCP**: Remote MCP server integration

### Plugin Manager

- `PluginManager.py` handles discovery, loading, and lifecycle
- Plugins register tools and skills at startup
- MCP plugins use `mcp_client.py` for server communication

---

## 9. Memory System

### Architecture

```
User Message
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ Memory (mem.py)                                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────┐  │
│  │ Vector Store   │  │ Graph Store    │  │ SQLite   │  │
│  │ (RAG chunks)  │  │ (entities/      │  │ (chat    │  │
│  │                │  │  relations)    │  │  history)│  │
│  └────────────────┘  └────────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────┘
    │
    ▼
RAG results + chat history + daily memory → LLM context
```

### Storage Backends

- **memory_backend: cognee** (default): Cognee with SQLite+ChromaDB+Kuzu by default; supports Postgres, LanceDB, Qdrant, Neo4j, etc.
- **memory_backend: chroma** (legacy): In-house SQLite + Chroma + optional graph (Kuzu, Neo4j)

### Chat History

- SQLite-based (`memory/chat/chat.py`)
- Per-user, per-session storage
- Summarization for long conversations

---

## 10. Channel System

Channels are adapters that connect HomeClaw to different messaging platforms.

### BaseChannel Pattern

```python
class BaseChannel:
    async def receive(message: InboundMessage) -> InboundRequest
    async def send(message: OutboundMessage) -> None
    async def start_voice_transcription(audio_url: str) -> str
```

### Supported Channels

- Telegram Bot
- Discord Bot
- Slack
- WhatsApp (via webhook)
- LINE
- Microsoft Teams
- WeChat (work in progress)
- Custom webhooks

### Companion App

Native Flutter app with:
- WebSocket real-time messaging
- REST API for file access, settings, friends
- Hive local storage for offline chat history
- Firebase Cloud Messaging for push notifications
- E2E encryption for federated messaging (X25519 + AES-256-GCM)

---

## 11. API Layer

### Core API (`core/routes/`)

| Route | Purpose |
|-------|---------|
| `POST /inbound` | Main message endpoint for channels |
| `WebSocket /ws` | Real-time bidirectional communication |
| `GET/POST /config` | Configuration management |
| `GET /files/*` | File serving (with auth) |
| `GET /api/memory/*` | Memory/RAG queries |
| `POST /api/skills/*` | Skill management |
| `GET/POST /api/plugins/*` | Plugin management |
| `POST /api/reminders/*` | Reminder scheduling |

### Portal API (`portal/app.py`)

Web UI for configuration:
- Model selection
- Channel setup
- Skill management
- User management
- Metrics dashboard

---

## 12. Security

### Authentication

- API key-based authentication per user
- Channel-specific auth (Telegram Bot tokens, Discord webhooks, etc.)
- Companion app uses session tokens

### Authorization

- Per-user permission system (`config/user.yml`)
- Tool-level permissions (camera, microphone, file access, etc.)
- Sandboxed skill execution

### Encryption

- E2E encryption for federated messaging (X25519 key exchange + AES-256-GCM)
- API key encryption at rest
- Layer encryption for companion app ↔ Core communication

---

## 13. Configuration

### Main Config (`config/core.yml`)

```yaml
main_llm: local_models/gemma-4-E4B-it-Q5_K_M
main_llm_mode: mix  # local | cloud | mix
embedding_llm: local_models/embedding-model
local_models:
  - id: gemma-4-E4B-it-Q5_K_M
    path: ...
cloud_models:
  - id: DeepSeek-Chat
    ...
use_skills: true
use_memory: true
memory_backend: cognee
channels:
  telegram:
    enabled: true
    bot_token: ...
```

### Intent Categories (`config/intent_category/`)

Markdown files per category with:
- Display name and description
- Match patterns (regex)
- Tool/skill profiles
- Priority for ordering

---

## 14. Key Entry Points

| File | Purpose |
|------|---------|
| `main.py` | CLI entry: `start`, `portal`, `onboard`, `doctor`, `ollama`, `skills`, `clawcode`, `peer` |
| `core/core.py` | FastAPI app factory + Core singleton + route registration |
| `core/llm_loop.py` | Main ReAct loop (`answer_from_memory`) |
| `core/inbound_handlers.py` | Webhook + WS inbound processing |
| `core/tam.py` | Time/Action/Memory scheduler |
| `channels/run.py` | Channel process runner |
| `portal/app.py` | Configuration web UI |

---

## 15. Dependencies

### Core Python Dependencies

- **FastAPI** + **Uvicorn**: Web framework and server
- **Loguru**: Logging
- **YAML**: Configuration
- **AIOHTTP**: Async HTTP client
- **ChromaDB** / **LanceDB**: Vector store
- **SQLAlchemy** / **TinyDB**: Database (legacy)
- **httpx**: HTTP client
- **Pydantic**: Data validation

### LLM Integration

- **LiteLLM**: Unified LLM interface (OpenAI, Claude, DeepSeek, Ollama, llama.cpp)
- **llama-cpu** / **llama.cpp**: Local LLM inference
- **chromadb**: Vector DB client

### Memory

- **Cognee** (default): RAG + graph memory framework
- **ChromaDB**: Vector storage
- **Kuzu** / **Neo4j**: Graph database (optional)

---

## 16. Known Architectural Observations

### Strengths

1. **Hybrid routing**: Well-designed cascade with clear layer responsibilities
2. **Multi-channel**: Consistent adapter pattern for adding new channels
3. **Skill system**: Simple, effective SKILL.md format
4. **E2E encryption**: Federated messaging is properly encrypted
5. **Tool permission model**: Fine-grained per-user tool access control

### Areas for Improvement

1. **`core/llm_loop.py` is very large** (~5100 lines): Would benefit from splitting into smaller modules (prompt builder, tool executor, skill invoker)
2. **`core_service.dart` is very large** (~3000 lines): Needs Riverpod/BLoC state management
3. **In-memory metrics**: Router metrics are in-memory only (recently added JSON persistence)
4. **No A/B testing infrastructure for routing** (recently added framework)
5. **Test coverage**: Limited unit tests for core logic
6. **Error handling**: Inconsistent error handling across components
7. **Configuration complexity**: Many config options with interdependencies

---

## 17. Getting Started with Development

### Run Core

```bash
cd HomeClaw
python main.py start
```

### Run Portal

```bash
python main.py portal
```

### Run Tests

```bash
# Python
pytest

# Flutter companion
cd clients/HomeClawApp
flutter test
```

### Key Debug Paths

```bash
# View recent logs
tail -f logs/homeclaw.log

# Check config
python main.py doctor

# List skills
python main.py skills list
```
