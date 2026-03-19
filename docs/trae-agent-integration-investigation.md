# Trae Agent integration – investigation

This doc summarizes what [trae-agent](https://github.com/bytedance/trae-agent) is, what you need to install and configure, and whether integrating it into HomeClaw is worth doing.

---

## 1. What is Trae Agent?

- **Repo:** https://github.com/bytedance/trae-agent  
- **What it is:** Open-source CLI agent for software engineering. You run a natural-language task in a project directory; it uses an LLM and tools (bash, file edit, etc.) and **prints the result to stdout**.
- **Difference from Trae IDE (`trae-cn`):** Trae IDE is a desktop app; its `chat` subcommand does not return the model reply on the terminal. Trae Agent is headless-first: `trae-cli run "task"` is designed to be scriptable and to output to the terminal, so we can capture the reply in the bridge and show it in Companion.

**Relevant CLI commands:**

```bash
trae-cli run "Create a hello world Python script"
trae-cli run "Fix the bug in main.py" --working-dir /path/to/project
trae-cli show-config
trae-cli interactive
```

---

## 2. What you need to install

### 2.1 Requirements (from README)

- **Python 3.12+**
- **UV** (package manager): https://docs.astral.sh/uv/
- **API key** for at least one provider (OpenAI, Anthropic, Doubao, OpenRouter, Ollama, Google Gemini, etc.)

### 2.2 Install steps

```bash
# 1. Install UV (if not already)
# Windows (PowerShell):
irm https://astral.sh/uv/install.ps1 | iex

# 2. Clone and set up trae-agent
git clone https://github.com/bytedance/trae-agent.git
cd trae-agent
uv sync --all-extras

# 3. Run from repo (no global install)
uv run trae-cli run "your task"

# Optional: install so trae-cli is on PATH
# uv pip install -e .   # from inside trae-agent repo, then trae-cli is available
```

There is **no PyPI package** named `trae-agent` that gives you a global `trae-cli`; the project expects to be run from the clone via `uv run trae-cli` or from a local editable install.

**For the bridge we need either:**

- **Option A:** Run from repo: e.g. `uv run trae-cli run "task"` with `cwd` = path to the trae-agent repo (so `uv` and `trae-cli` are found). Working directory for the *task* is passed with `--working-dir`.
- **Option B:** User does `uv pip install -e .` inside the clone so `trae-cli` is on PATH; then the bridge just runs `trae-cli run "task" --working-dir <project>`.

---

## 3. What you need to configure

### 3.1 Config file

- **File:** `trae_config.yaml` (or `trae_config.json`).
- **Default location:** The CLI looks for `trae_config.yaml` in the **current working directory** when you pass a relative `--config-file` (default is `trae_config.yaml`). So either:
  - Put `trae_config.yaml` in each project dir, or
  - Pass **`--config-file`** with an **absolute path** to a single shared config (e.g. `C:\Users\You\trae_config.yaml` or inside the trae-agent repo).

### 3.2 Supported model providers

The **README** lists: **OpenAI, Anthropic, Doubao, Azure, OpenRouter, Ollama, Google Gemini**. It does not list every compatible service; any **OpenAI-compatible** API can be used by setting `provider: openai` with a custom **base_url** and **api_key**.

| Provider | In README? | How to use |
|----------|------------|------------|
| OpenAI, Anthropic, Doubao, Azure, OpenRouter, Ollama, Google Gemini | Yes | Use the matching `model_providers` entry and env vars (see README). |
| **DeepSeek** | No (as named provider) | Use `provider: openai` + `base_url` for DeepSeek’s API (OpenAI-compatible). |
| **Minimax** | No | Use `provider: openai` + `base_url: https://api.minimaxi.com/v1` + your Minimax API key; model e.g. `MiniMax-M2.7`. |
| Other OpenAI-compatible gateways | No | Same pattern: `provider: openai`, `base_url`, `api_key`, and the model id the endpoint expects. |

For **Doubao**, use `base_url: https://ark.cn-beijing.volces.com/api/v3` (see [issue #308](https://github.com/bytedance/trae-agent/issues/308) if you see connection errors). For **Minimax**, the official OpenAI-compatible endpoint is `https://api.minimaxi.com/v1`. **Note:** trae-agent’s OpenAI client uses the **Responses API** (`client.responses.create`), not the **Chat Completions API** (`/v1/chat/completions`). Minimax (and many other gateways) only support Chat Completions, so with provider `openai` and `base_url` pointing at Minimax you get **404 page not found**. Use **Anthropic** or **OpenAI** directly in trae_config.yaml, or another provider that supports the Responses API, until trae-agent adds a Chat Completions path for openai-compatible endpoints.

### 3.3 Minimal config (from README / example)

```yaml
agents:
  trae_agent:
    enable_lakeview: true
    model: trae_agent_model
    max_steps: 200
    tools:
      - bash
      - str_replace_based_edit_tool
      - sequentialthinking
      - task_done

model_providers:
  anthropic:
    api_key: your_anthropic_api_key
    provider: anthropic
  # Or openai, doubao, openrouter, ollama, google, etc.

models:
  trae_agent_model:
    model_provider: anthropic
    model: claude-sonnet-4-20250514
    max_tokens: 4096
    temperature: 0.5
```

### 3.4 Custom base URL (e.g. OpenRouter, DeepSeek, Minimax)

You can point a provider at a gateway:

```yaml
openai:
  api_key: your_openrouter_api_key
  provider: openai
  base_url: https://openrouter.ai/api/v1
```

So you can reuse the same API keys / base URLs you use elsewhere (e.g. Minimax-style endpoints if supported by the provider name and trae-agent’s code).

### 3.5 Environment variables (alternative to config file)

From README:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export ANTHROPIC_BASE_URL="your-anthropic-base-url"
# etc.
```

So the bridge could **either** pass `--config-file <path>` **or** ensure these env vars are set when it spawns `trae-cli`.

---

## 4. How we would integrate

### 4.1 Bridge behavior

- **One new “backend”** in the existing dev bridge (same server as Cursor/Claude/Trae IDE), e.g. `trae_agent`.
- When a request comes in for **trae-agent** (e.g. plugin_id `trae-agent-bridge` or similar):
  - **run_agent:** run  
    `trae-cli run "<task>" --working-dir <project_cwd> [--config-file <path>] [--console-type simple]`  
    and capture stdout/stderr, then return that text to Core/Companion.
  - **set_cwd / get_status:** re-use the same “active cwd” idea as for Trae IDE / Claude Code.
- **open_project** is less relevant (trae-agent has no GUI to “open”); we could either skip it or keep it for consistency and document that it only sets the active project for later `run_agent`.

### 4.2 Config we’d add (on Core/bridge side)

- **Path to `trae-cli` or to repo**
  - Either: `cursor_bridge_trae_agent_cli_path` = full path to `trae-cli` executable (if user did `pip install -e .`),  
  - Or: `cursor_bridge_trae_agent_repo` = path to trae-agent repo, and we run `uv run trae-cli` with `cwd` = that repo.
- **Config file for trae-agent**
  - `cursor_bridge_trae_agent_config` = absolute path to `trae_config.yaml` (so one shared config for all projects).

Core would pass these into the bridge’s environment (same pattern as `cursor_bridge_trae_cli_path` for Trae IDE), and the bridge would build the `trae-cli run ...` invocation accordingly.

### 4.3 Plugin and friend preset

- New plugin, e.g. **trae-agent-bridge**, same `base_url` (port 3104) as the existing bridge, capabilities: `run_agent`, `set_cwd`, `get_status`, maybe `run_command`.
- New friend preset, e.g. **trae_agent**, with `tools_preset: bridge` and `plugins: [trae-agent-bridge]`, so the user can pick “Trae Agent” in Companion and get headless task runs with replies shown in chat.

### 4.4 Output format

- Use **`--console-type simple`** so the CLI emits plain text instead of Rich formatting, making it easier to show in Companion.
- We already capture stdout/stderr in the bridge; no change to that part.

---

## 5. Is it worth doing?

### Pros

- **Real replies in Companion:** Trae Agent is built for headless use; we get the model’s answer on stdout and can show it in the app, unlike Trae IDE’s `chat`.
- **Same UX as Cursor/Claude Code:** “Ask in Companion → get answer in Companion” for coding tasks.
- **Reuse existing bridge:** One more backend and one more plugin; no new server or port.
- **Flexible LLM/config:** User brings their own API key and model (Anthropic, OpenAI, Doubao, OpenRouter, Ollama, etc.) via `trae_config.yaml` or env.

### Cons / effort

- **Install story:** User must clone trae-agent and run `uv sync`, and either run via `uv run trae-cli` or install with `pip install -e .`. We should document this clearly.
- **Config story:** User must create and maintain at least one `trae_config.yaml` (or set env vars). We can document a minimal example and the `--config-file` path.
- **Two “Trae” concepts:** We’ll have “Trae” (IDE, open project + limited chat) and “Trae Agent” (headless, run task and get reply). Naming in the UI (e.g. “Trae Agent” vs “Trae”) can make this clear.
- **Implementation effort:** Small: one backend in the bridge (~50–80 lines), one plugin YAML, one friend preset, and config keys + docs. No change to Core routing beyond adding the new plugin and preset.

### Verdict

**Worth doing** if you want a single “ask in Companion and get a text reply” flow for an agent that edits files and runs bash in a project (like Cursor agent / Claude Code). Trae Agent fits that use case and is designed to be scriptable. The main cost is user setup (clone, uv sync, one config file); the code change is contained and follows the same pattern as the existing Trae IDE and Claude Code bridges.

---

## 6. References

- Repo: https://github.com/bytedance/trae-agent  
- README (install, config, usage): https://github.com/bytedance/trae-agent/blob/main/README.md  
- Example config: `trae_config.yaml.example` in the repo  
- CLI entry: `trae-cli` from `trae_agent.cli:main` (pyproject.toml)
