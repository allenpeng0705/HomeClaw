# HomeClaw - Claude Code Development Reference

## Overview

**HomeClaw** is a self-hosted AI assistant platform built with Python/FastAPI. It acts as a central hub for AI-powered conversations with support for multiple channels, local/cloud LLM models, tools, skills, plugins, and memory management.

---

## Architecture Overview

### System Structure

```
User Request → Channel → Core (port 9000) → Orchestrator (Intent Filter)
                                                    ↓
                              ┌─────────────────────┴─────────────────────┐
                            TIME Intent                                OTHER Intent
                              ↓                                              ↓
                          TAM (Scheduling)                    LLM Loop (answer_from_memory)
                                                                ↓
                                              ┌─────────────────┼─────────────────┐
                                    Hybrid Router                      Build Messages
                                    (3 layers)                         (system+skills+
                                              ↓                         tools+history)
                                    Select LLM                       ↓
                                    (local/cloud/mix)              LLM Call
                                              ↓                      ↓
                                    ReAct Loop ◄────────────────┤
                                              ↓                   |
                                    Tool Execution              │
                                              ↓                   │
                                    Loop back to LLM ───────────┘
                                              ↓
                                    Response → Channel → User
```

### Main Entry Point
- `/Users/shileipeng/Documents/mygithub/HomeClaw/main.py`

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `core/` | Core server (FastAPI routes, LLM loop, session management) |
| `channels/` | Channel adapters (webchat, telegram, discord, etc.) |
| `memory/` | Memory backends (Cognee, Chroma, database) |
| `llm/` | LLM abstraction (llama.cpp, Ollama, LiteLLM) |
| `portal/` | Portal web UI (config/onboarding) |
| `plugins/` | Built-in plugins |
| `skills/` | Built-in skills |
| `tools/` | Built-in tools |
| `hybrid_router/` | Hybrid LLM routing (local/cloud) |
| `config/` | YAML configs (core.yml, llm.yml, user.yml, etc.) |
| `clients/` | Client apps including Flutter companion app |

### Key Services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| **Core** | `python3 -m main start --no-open-browser` | 9000 | Main FastAPI server |
| **Portal** | `python3 -m main portal --no-open-browser` | 18472 | Config/onboarding web UI |
| **WebChat** | `python3 -m channels.run webchat` | 8014 | Chat interface |

---

## Agent System

### Intent Filter

**File:** `core/orchestrator.py`

The orchestrator classifies user requests into intents:

- **TIME intent** → TAM (Time/Action/Memory) for scheduling/reminders
- **OTHER intent** → LLM Loop for general processing

```python
# From core/orchestrator.py lines 80-102
async def translate_to_intent(self, request: PromptRequest) -> Intent:
    text = request.text
    hist = self.get_hist_chats(request)
    prompt = self.create_prompt(text, hist)
    messages = [{"role": "system", "content": prompt}]
    intent_str = await Util().openai_chat_completion(messages)
    intent = await self.process_intent(hist, text, intent_str, request)
    return intent
```

### Skill Router

**File:** `base/skill_router.py`

- `load_skills_for_query()` - semantic search for relevant skills using vector embeddings
- Supports hybrid mode (semantic + trigger pattern matching)
- Config options: `skills_router_config` in core.yml

### ReAct Loop

**File:** `core/llm_loop.py` - `answer_from_memory()` function

The loop:
1. Builds messages with system prompt, chat history, tools, skills
2. Calls LLM with tools
3. If `tool_calls` returned: executes tools and loops back
4. If no `tool_calls`: returns response to user
5. Max iterations controlled by configuration

### Hybrid Router (LLM Selection)

**Files:** `hybrid_router/`

3-layer routing:
1. **Heuristic** - keyword matching (`config/hybrid/heuristic_rules.yml`)
2. **Semantic** - vector similarity (`config/hybrid/semantic_routes.yml`)
3. **SLM Classifier** - perplexity-based routing

Modes: `local` | `cloud` | `mix` (default)

---

## LLM Integration

### LLM Configuration

**File:** `config/llm.yml`

**Local Models (llama.cpp/GGUF):**
- Configured in `local_models:` array
- Each entry specifies: `id`, `path`, `host`, `port`, `capabilities`
- Core starts `llama-server` processes on configured ports

**Cloud Models (LiteLLM):**
- Configured in `cloud_models:` array
- DeepSeek, OpenAI, Gemini, Anthropic, etc.
- LiteLLM proxy on `cloud_llm_host:cloud_llm_port` (default 127.0.0.1:14005)

**LLM Service Manager:** `llm/llmService.py`

### Key Config Options (config/core.yml)

```yaml
main_llm_mode: mix  # local | cloud | mix
main_llm_local: local_models/gemma-4-E4B-it-Q5_K_M
main_llm_cloud: cloud_models/DeepSeek-Chat
embedding_llm: local_models/Qwen3-Embedding-0.6B
vision_llm: local_models/main_vl_model_2B
```

---

## Tools, Skills, Plugins

### Tools

**File:** `tools/builtin.py` (490KB)

Core built-in tools registered in `ToolRegistry`:
- `file_read`, `file_write`, `folder_list`
- `remind_me`, `cron_schedule`
- `run_skill`, `web_search`
- etc.

**Tool Registry:** `base/tools.py`

```python
@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    execute_async: ToolExecutor

class ToolRegistry:
    def register(self, tool: ToolDefinition)
    async def execute_async(self, name: str, arguments: Dict, context: ToolContext) -> str
```

### Skills

**Location:** `skills/`

- Skill folders containing `SKILL.md` (YAML frontmatter + markdown body)
- Loaded by `base/skills.py` functions
- Injected into system prompt via `build_skills_system_block()`

### Plugins

**Location:** `plugins/`

- External capabilities via HTTP subprocess or MCP
- Managed by `PluginManager` (`base/PluginManager.py`)
- Types: `http`, `subprocess`, `mcp`

---

## Memory System

**Files:** `memory/`

### Components
- `mem.py`: Main Memory class with vector + graph store
- `cognee_adapter.py`: Cognee integration for advanced memory
- `memos_adapter.py`: MemOS integration
- `embedding.py`: LlamaCppEmbedding for vectorization
- `vector_store_factory.py`: Chroma, Qdrant, Milvus, Pinecone, Weaviate support
- `graph/`: Neo4j and Kuzu graph databases

### Knowledge Base
- `knowledge_base.py`: RAG implementation for user documents
- `cognee_knowledge_base.py`: Cognee-backed knowledge base

---

## Channel System

### Architecture

Channels connect to Core via HTTP POST to `/inbound` endpoint

**Supported Channels:**
- telegram, discord, slack, whatsapp, whatsappweb, matrix, wechat, tinode, line, google_chat, signal, imessage, teams, webchat, zalo, feishu, dingtalk, bluebubbles, webhook

**Entry Point:**
```bash
python -m channels.run <channel_name>
```

### Connection Flow
1. Channel receives message from user
2. Channel formats as `InboundRequest` and POSTs to Core's `/inbound`
3. Core processes through `handle_inbound_request_impl()`
4. Response sent back to channel

---

## Session Management

**File:** `core/session_channel.py`

### Session Resolution

```python
def _resolve_session_key(core, app_id, user_id, channel_name, account_id):
    dm_scope = config.get("dm_scope")  # main | per-peer | per-channel-peer
    # Returns session key like "homeclaw:dm:user123"
```

### Chat History
- `ChatHistory` class in `memory/chat/chat.py`
- SQLite-backed storage in `database/` folder

---

## Companion App (Flutter)

**Location:** `clients/HomeClawApp/`

### Architecture
- **Framework:** Flutter with Material Design 3
- **No external state management** - uses StatefulWidget + StreamSubscriptions
- **CoreService** singleton manages all API connections, WebSocket, settings

### Connection to Core

**WebSocket:** `ws://{baseUrl}/ws?api_key={key}`
- Real-time messaging and push notifications
- Ping every 30 seconds for keepalive
- Push events: `push` (reminders), `inbound_result` (async results)

**REST API Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `POST /api/auth/login` | User authentication |
| `GET /api/me/friends` | List all friends |
| `POST /inbound` | Send message to Core |
| `GET /api/chat-history` | Load conversation history |
| `POST /api/user-message` | Send user-to-user message |
| `GET /api/skills/list` | List installed skills |
| `GET /api/clawcode/sessions` | List Claw-Code sessions |

### Key Features

#### Preset Friends
- Bundled icons: Reminder, Finder, Knowledge, Note
- Quick action chips for common tasks
- Location: `lib/utils/product_preset_chat.dart`

#### Social Network
- User-to-user chat with friend requests
- Real-time inbox polling
- **E2E encryption** (X25519 + HKDF-SHA256 + AES-256-GCM) for federated messages
- Federation across multiple HomeClaw Core instances

#### Multi-Instance Support
- QR code connection: `homeclaw://connect?url=...&api_key=...`
- Per-Core session management
- Remote friend presence with cloud icon badge

#### Dev Bridge
- Cursor/Claude Code/Trae IDE integration
- Project directory browsing
- Location: `lib/screens/bridge_project_files_tab.dart`

#### Claw-Code
- Session management for coding assistance
- Location: `lib/screens/clawcode_screen.dart`

#### Skills & Portal
- ClawHub marketplace integration
- Embedded WebView for Core administration

#### Native Plugin (homeclaw_native)
- `showNotification()` - local notifications
- `cameraSnap()`, `cameraClip()` - camera access
- `systemRun()` - shell command execution
- `getApnsToken()` - push notification token

### Key Screens

| Screen | File | Purpose |
|--------|------|---------|
| `FriendListScreen` | `friend_list_screen.dart` | Main hub |
| `ChatScreen` | `chat_screen.dart` | Full-featured chat (2000+ lines) |
| `AddFriendScreen` | `add_friend_screen.dart` | User search + federated |
| `SettingsScreen` | `settings_screen.dart` | App configuration |
| `SkillsScreen` | `skills_screen.dart` | ClawHub marketplace |
| `ClawcodeScreen` | `clawcode_screen.dart` | Coding sessions |

---

## Key Configuration Files

### config/core.yml
Main configuration (server, LLM, memory, skills, tools)

### config/llm.yml
LLM model catalog (local and cloud models)

### config/user.yml
User accounts and permissions

### config/hybrid/heuristic_rules.yml
3600+ lines of keyword-based routing for local/cloud selection

### config/friend_presets.yml
Preset friend configurations including Claw-Code

---

## Important Files Reference

### Core Processing
- `core/core.py` - Main Core class
- `core/llm_loop.py` - LLM loop (answer_from_memory)
- `core/orchestrator.py` - Intent classification
- `core/tam.py` - Scheduling/reminders
- `core/inbound_handlers.py` - Request handling
- `core/session_channel.py` - Session management

### Base Infrastructure
- `base/tools.py` - Tool registry
- `base/skills.py` - Skill loader
- `base/skill_router.py` - Skill routing
- `base/intent_router.py` - Intent categories
- `base/PluginManager.py` - Plugin management

### Memory
- `memory/mem.py` - Memory class
- `memory/embedding.py` - Embeddings
- `memory/chat/chat.py` - Chat history

### LLM
- `llm/llmService.py` - LLM service manager
- `llm/llama_cpp_platform.py` - llama.cpp integration
- `hybrid_router/` - Hybrid routing logic

### Channels
- `channels/run.py` - Channel runner
- `channels/webchat/channel.py` - WebChat implementation
- `channels/telegram/channel.py` - Telegram implementation

---

## Running Services

```bash
# Core server
python3 -m main start --no-open-browser  # Port 9000

# Portal
python3 -m main portal --no-open-browser  # Port 18472

# WebChat channel
python3 -m channels.run webchat  # Port 8014
```

### Python Environment
```bash
conda activate pytorch
```

---

## Testing

```bash
conda activate pytorch
python3 -m pytest tests/ -v
```

Tests use mocks; no running Core or LLM required.

---

## Additional Documentation

- `docs/` - General documentation
- `docs_design/` - Design documents
- `HOW_TO_USE.md` - Usage guide
- `Design.md` - System design (53KB)
- `Channel.md` - Channel documentation (26KB)
