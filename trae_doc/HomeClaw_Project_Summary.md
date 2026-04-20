# HomeClaw Project Summary

## Project Overview
HomeClaw is a self-hosted AI assistant platform with a modular architecture consisting of a Core server and various channel adapters. The Core server (Python/FastAPI) runs on port 9000 and handles LLM interactions, while channels (WebChat, Telegram, Discord, etc.) connect to Core to provide user interfaces.

## Key Components

### 1. Core Server
- **Location**: `core/`
- **Main Files**: 
  - `core.py`: Main Core implementation
  - `orchestrator.py`: Initializes and manages components
  - `tam.py`: Time Awareness Module (scheduling and reminders)
  - `llm_loop.py`: LLM interaction loop
- **Features**: LLM integration, session management, tool execution, memory system

### 2. Time Awareness Module (TAM)
- **Location**: `core/tam.py`
- **Purpose**: Handles scheduling and reminders
- **Key Features**:
  - One-shot reminders
  - Cron jobs for recurring tasks
  - Task types: message, run_skill, run_plugin, run_tool
  - Persistent storage for scheduled tasks

### 3. Channels
- **Location**: `channels/`
- **Supported Channels**: WebChat, Telegram, Discord, WhatsApp, WeChat, etc.
- **WebChat**: Runs on port 8014, provides chat UI and Claw-Code interface

### 4. Memory System
- **Components**:
  - Cognee memory system (knowledge graph)
  - Chroma (vector database for RAG)
  - Database storage for cron jobs and reminders
- **Key Files**:
  - `memory/tam_storage.py`: Persistent storage for TAM
  - `memory/database/models.py`: Database models

### 5. Tools
- **Location**: `tools/`
- **Built-in Tools**: `builtin.py` contains core tools including cron_schedule
- **Tool Execution**: Tools are executed through the tool registry

## Architecture Flow
1. User sends message through a channel
2. Channel forwards message to Core
3. Core processes message through LLM loop
4. LLM may call tools (e.g., cron_schedule)
5. Tools execute and return results
6. Core sends response back through the channel

## Fixes Implemented

### Cron Job Execution Fix
**Issue**: Recurring cron jobs were not executing properly

**Root Cause**: Task creation functions for `run_plugin` and `run_tool` were returning lambdas that wrapped coroutines instead of returning the coroutines directly.

**Fix Applied**:
- Modified `make_run_plugin_task` function in `core/tam.py:1233`
  - Before: `return lambda: _run()`
  - After: `return _run`

- Modified `make_run_tool_task` function in `core/tam.py:1273`
  - Before: `return lambda: _run()`
  - After: `return _run`

**Why This Fix Works**:
The `_run_one_cron_job` function expects tasks to return coroutines when called:
```python
if task and callable(task):
    coro = task()
    if coro is not None and asyncio.iscoroutine(coro):
        asyncio.run(coro)
```

With the fix, `task()` now directly returns the coroutine, which is then properly executed by asyncio.run().

## Task Types and Execution

### 1. Message Tasks
- Simple text reminders
- Executes: Sends message to user

### 2. Run Skill Tasks
- Executes skill scripts
- Can include post-processing with LLM
- Example: Weather skill

### 3. Run Plugin Tasks
- Executes plugin capabilities
- Example: News plugin

### 4. Run Tool Tasks
- Executes built-in tools
- Example: Web search for news

## Cron Job Scheduling

### Creating a Cron Job
```python
# Example: Schedule daily news at 9:00 AM
cron_schedule(
    cron_expr="0 9 * * *",
    task_type="run_tool",
    tool_name="web_search",
    tool_arguments={"query": "10 Chinese news", "count": 10}
)
```

### Execution Flow
1. Cron scheduler checks jobs every 10 seconds
2. When job is due, `_run_one_cron_job` is called
3. Task function is executed
4. Result is sent to user
5. Job state is persisted (last run time, status, etc.)

## Configuration

### Key Config Files
- `config/core.yml`: Main Core settings
- `config/llm.yml`: LLM model definitions
- `config/user.yml`: User-specific settings
- `config/skills_and_plugins.yml`: Tool and plugin configurations

### LLM Configuration
- `main_llm_mode`: `local`, `cloud`, or `mix`
- `main_llm`: Specifies which LLM to use

## Development and Testing

### Running Services
- **Core**: `python3 -m main start --no-open-browser` (port 9000)
- **WebChat**: `python3 -m channels.run webchat` (port 8014)
- **Portal**: `python3 -m main portal --no-open-browser` (port 18472)

### Testing
- Use `conda activate pytorch` before running tests
- Run tests: `python3 -m pytest tests/ -v`
- Tests use mocks; no running Core or LLM required

## Claw-Code Integration
- Special friend preset with `preset: clawcode`
- Web interface: `/clawcode` on Core or WebChat
- Allows binding workspace sessions for code assistance

## Security Considerations
- API keys should be stored in environment variables
- Cron jobs run with the same permissions as Core
- Plugin parameters are validated before execution

## Future Enhancements
- Support for more channels
- Improved memory system integration
- Enhanced LLM capabilities
- Better error handling and logging
- More robust scheduling system

## Conclusion
HomeClaw is a powerful self-hosted AI assistant platform with a modular architecture that supports multiple channels and a wide range of capabilities. The cron job execution fix ensures that recurring tasks like daily news searches now work reliably, providing users with consistent automated functionality.