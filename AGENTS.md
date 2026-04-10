# HomeClaw Development

## Cursor Cloud specific instructions

### Overview

HomeClaw is a self-hosted AI assistant platform. The main service is **Core** (Python/FastAPI on port 9000). Channels (WebChat, Telegram, Discord, etc.) connect to Core. The recommended dev testing path is Core + WebChat channel.

### Python environment (Conda)

For **all** Python commands in this repo (Core, Portal, channels, pytest, scripts, `python3 -m main …`), use the **`pytorch`** conda env unless you know your own env matches `requirements.txt`:

```bash
conda activate pytorch
```

That env already includes **`mcp`** (official SDK), so `tests/test_homeclaw_mcp_optional.py` runs instead of skipping, and `python3 -m main homeclaw_mcp` works without an extra `pip install mcp`. Agents and CI should assume commands are run **after** `conda activate pytorch` when executing Python on this project.

### Missing `memory/chat` module (gitignored)

The `memory/chat/` directory is listed in `.gitignore` and was never committed. However, `base/util.py`, `core/core.py`, and other modules import from `memory.chat.message` and `memory.chat.chat`. If the directory is missing, **Core cannot start and most tests fail**. The update script regenerates it automatically. If you see `ModuleNotFoundError: No module named 'memory.chat'`, re-run the update script or check that `memory/chat/__init__.py`, `memory/chat/message.py`, and `memory/chat/chat.py` exist.

### Running services

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| **Core** | `python3 -m main start --no-open-browser` | 9000 | Takes ~2 min to start (waits 120s for embedding health check when local models are absent). Check readiness: `curl http://127.0.0.1:9000/ready` |
| **Portal** | `python3 -m main portal --no-open-browser` | 18472 | Config/onboarding web UI |
| **WebChat** | `python3 -m channels.run webchat` | 8014 | `/` chat UI; optional **`/clawcode`** (same HTML as Core). **Claw-Code UI on Core:** `http://<core>:9000/clawcode` — no WebChat port needed when only 9000 is published |

**Claw-Code:** Add **`preset: clawcode`** friend in `config/user.yml` (see `config/friend_presets.yml` — like Cursor/ClaudeCode). Companion: open **Clawcode** chat → **terminal** icon / **More → Claw-Code** to bind a workspace session; same chat UI as other AI friends. Tools screen / browser: optional. Operator flow: `docs/clawcode-operator-checklist.md`. Security: `docs/clawcode-ui-security.md`.

### LLM configuration

- Config files: `config/core.yml` (main settings) and `config/llm.yml` (model definitions). Core merges both.
- `main_llm_mode` in `llm.yml` controls routing: `local`, `cloud`, or `mix`. Default is `mix` (requires both local GGUF models + llama.cpp and cloud API keys).
- Without local GGUF model files or llama.cpp binary, Core logs errors for missing models but still starts. The cloud LLM (DeepSeek via LiteLLM) starts on port 14005.
- To use cloud-only: set `main_llm_mode: cloud` and `main_llm: cloud_models/DeepSeek-Chat` in `config/llm.yml`. Set `DEEPSEEK_API_KEY` env var (or use the hardcoded key in the config).

### Testing

- Use **`conda activate pytorch`**, then from project root: `python3 -m pytest tests/ -v`
- Tests use mocks; no running Core or LLM required.
- **Portal tests:** `fastapi.testclient.TestClient` can fail when **httpx ≥ 0.28** is installed (Starlette passes `app=` to `httpx.Client`, which removed that API). Portal route tests use **`tests/sync_asgi_client.SyncASGIClient`** (`httpx.AsyncClient` + `ASGITransport`) instead. Repo `requirements.txt` still pins `httpx<0.28` for Core compatibility; CI/dev machines may override.
- **MCP (optional test):** With **`pytorch`**, `mcp` is present — `tests/test_homeclaw_mcp_optional.py` should **pass**. Without `mcp`, that test is skipped. Stdio server for IDEs: `python3 -m main homeclaw_mcp` — see `clients/homeclaw_mcp/README.md`.
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
- `docs/response-output-policy.md` — When to use plaintext vs Markdown vs VMPrint preview links for long responses; `tools.response_output_policy_in_prompt` in `skills_and_plugins.yml` injects a short version into the system prompt
- **VMPrint AST reference:** `tools/vmprint/documents/SKILL.md` (upstream practitioner guide, ~1300 lines). Not in the default skills prompt body; skill **`vmprint-ast-layout-1.0.0`** points agents to read that file on demand via `document_read` / `file_read`
- **VMPrint roadmap (templates vs AI-AST):** `docs/vmprint-ui-runtime.md` — ship and extend **Python → AST** templates for now; move toward **model-generated AST** via `render-ast` + the same validation pipeline (see section *Python templates now → AI-generated AST later*).
