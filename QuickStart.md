# HomeClaw Quick Start

This guide is the shortest path from zero to first chat.

## 1) Install

| Platform | Command |
|---|---|
| macOS / Linux | `bash install.sh` |
| Windows | `install.bat` (or `.\install.ps1`) |

What installer does:

- checks Python/Node
- installs Python deps
- installs helper CLIs (optional)
- installs VMPrint support for better PDF output
- opens Portal at `http://127.0.0.1:18472`

## 2) Configure in Portal

If you want to use **local GGUF models** (local mode or mix mode), prepare these files first:

1. **Download GGUF model files** (for example from Hugging Face).
2. Put them into the local model folder:
   - default: `models/` (because `config/core.yml` has `model_path: models`)
   - optional: if you changed `model_path`, use that folder instead
3. If you install `llama.cpp` manually, download the **llama.cpp binary distribution** and place it into:
   - `llama.cpp-master/<platform>/`
   - common platform folders: `mac/`, `win_cpu/`, `win_cuda/`, `linux_cpu/`, `linux_cuda/`
4. In `config/llm.yml`, make sure each `local_models` entry `path` matches the GGUF filename you put in `models/`.

In Portal:

1. Create admin account
2. Open **Manage settings -> LLM**
3. Choose your main model
4. Add user(s)
5. Start Core

### Optional: enable mobile coding (Cursor + Claude Code bridge)

If you want to code from your phone through HomeClaw Companion:

1. Open `config/skills_and_plugins.yml`
2. Confirm:
   - `cursor_bridge_auto_start: true`
3. (Optional but recommended) set full paths if your CLI is not found:
   - `cursor_bridge_agent_path` (Cursor `agent` CLI)
   - `claude_code_path` (Claude Code CLI)
4. Restart Core after changing this file.

Then, in Companion/WebChat, use coding requests and route to Cursor/Claude bridge tools.

## 3) Run Core

```bash
python -m main start
```

Core default address: `http://127.0.0.1:9000`

Health check:

```bash
python -m main doctor
```

## 4) Chat

### Companion app

- Open app
- Set Core URL to `http://127.0.0.1:9000`
- If auth enabled, add API key
- Login/use your configured user

### WebChat channel

```bash
python -m channels.run webchat
```

## 5) Practical examples

### Example: use mix mode

In `config/llm.yml`:

- `main_llm_mode: mix`
- `main_llm_local: local_models/<id>`
- `main_llm_cloud: cloud_models/<id>`

### Example: generate a better PDF

Use tool `vmprint_render`:

- `output_format: pdf`
- `vmprint_profile: academic | manuscript | screenplay | literature`
- optional `vmprint_style`

### Example: export VMPrint AST JSON

Use tool `vmprint_render`:

- `output_format: ast_json`
- `path: output/<name>.ast.json`

---

More docs:

- `README.md`
- `InstallationGuide.md`
- `HOW_TO_USE.md`
