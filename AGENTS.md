# HomeClaw Development

## Cursor Cloud specific instructions

### Overview

HomeClaw is a self-hosted AI assistant platform. The main service is **Core** (Python/FastAPI on port 9000). Channels (WebChat, Telegram, Discord, etc.) connect to Core. The recommended dev testing path is Core + WebChat channel.

### Missing `memory/chat` module (gitignored)

The `memory/chat/` directory is listed in `.gitignore` and was never committed. However, `base/util.py`, `core/core.py`, and other modules import from `memory.chat.message` and `memory.chat.chat`. If the directory is missing, **Core cannot start and most tests fail**. The update script regenerates it automatically. If you see `ModuleNotFoundError: No module named 'memory.chat'`, re-run the update script or check that `memory/chat/__init__.py`, `memory/chat/message.py`, and `memory/chat/chat.py` exist.

### Running services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| **Core** | `python3 -m main start --no-open-browser` | 9000 | Takes ~2 min to start (waits 120s for embedding health check when local models are absent). Check readiness: `curl http://127.0.0.1:9000/ready` |
| **Portal** | `python3 -m main portal --no-open-browser` | 18472 | Config/onboarding web UI |
| **WebChat** | `python3 -m channels.run webchat` | 8014 | Browser chat UI; requires Core running |

### LLM configuration

- Config files: `config/core.yml` (main settings) and `config/llm.yml` (model definitions). Core merges both.
- `main_llm_mode` in `llm.yml` controls routing: `local`, `cloud`, or `mix`. Default is `mix` (requires both local GGUF models + llama.cpp and cloud API keys).
- Without local GGUF model files or llama.cpp binary, Core logs errors for missing models but still starts. The cloud LLM (DeepSeek via LiteLLM) starts on port 14005.
- To use cloud-only: set `main_llm_mode: cloud` and `main_llm: cloud_models/DeepSeek-Chat` in `config/llm.yml`. Set `DEEPSEEK_API_KEY` env var (or use the hardcoded key in the config).

### Testing

- Run tests from project root: `python3 -m pytest tests/ -v`
- Tests use mocks; no running Core or LLM required.
- One test (`test_clawhub_search_parses_json`) requires `clawhub` CLI on PATH (optional).
- See `tests/README.md` for details.

### Key directories

- `config/` — YAML configs (core.yml, llm.yml, user.yml, memory_kb.yml, skills_and_plugins.yml)
- `core/` — Core server (FastAPI routes, LLM loop, session management)
- `channels/` — Channel adapters (webchat, telegram, discord, etc.)
- `memory/` — Memory backends (Cognee, Chroma, database)
- `llm/` — LLM abstraction (llama.cpp, Ollama, LiteLLM)
- `portal/` — Portal web UI (config/onboarding)
- `plugins/` — Built-in plugins
- `skills/` — Built-in skills
- `vendor/cognee/` — Vendored Cognee (memory/knowledge graph)
- `tests/` — Pytest test suite
