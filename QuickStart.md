# HomeClaw Quick Start

Get from zero to running HomeClaw in a few steps. This doc is kept short on purpose; we improve it over time.

---

## 1. Run the install script

| OS | Command |
|----|--------|
| **Mac / Linux** | `./install.sh` (from project root, or from a parent directory — script will clone into `./HomeClaw` and continue) |
| **Windows** | `.\install.ps1` (from project root, or from a parent directory — script will clone into `.\HomeClaw` and continue) |

The script sets up **Python 3.9+**, **Node.js**, **tsx** (for TypeScript skill scripts), **pip dependencies**, and optionally **llama.cpp** and **VMPrint**. It then starts the **Portal** and opens your browser at http://127.0.0.1:18472.

---

## 2. Local models (if you use llama.cpp)

**If llama.cpp was installed via brew (Mac/Linux) or winget (Windows):**  
You only need to add your **models**. No need to copy any binary into the repo.

1. **Download GGUF models** (e.g. from [Hugging Face](https://huggingface.co) or [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)).
2. **Put `.gguf` files** in the project’s `models/` folder (create it if it doesn’t exist).
3. **Add entries in `config/llm.yml`** under `local_models:` with a `path` set to the filename (e.g. `path: my-model-Q4_K_M.gguf`). Use the Portal **Manage settings → LLM** to pick `main_llm` and `embedding_llm` from your local or cloud models.

**If the install script could not install llama.cpp:**  
Follow the instructions it printed: download the pre-built binary for your platform, unzip, and copy `llama-server` (or `llama-server.exe` on Windows) into `llama.cpp-master/<platform>/` in this repo. See `llama.cpp-master/README.md` for the folder layout. Then add models as above.

**Alternative: Ollama**  
Install [Ollama](https://ollama.com), run `ollama pull <model>`, and set `main_llm` in the Portal or `config/llm.yml` to use an Ollama model.

---

## 3. First-time setup in the Portal

In the browser (http://127.0.0.1:18472):

1. **Create an admin account** (first run).
2. **Manage settings** — Core, **LLM** (choose model, set cloud API keys if you use cloud), Users.
3. **Start Core** from the dashboard (or run `python -m main start` in a terminal).

---

## 4. Run HomeClaw

- **Core + web UI:** `python -m main start` (or start Core from the Portal).
- **Portal only:** `python -m main portal`
- **Channels** (Telegram, Slack, WebChat, etc.): with Core running, in another terminal run `python -m channels.run <channel_name>`. See `channels/README.md`.

After setup, run `python -m main doctor` to verify config and LLM connectivity.

---

## 5. Import OpenClaw / ClawHub skills (optional)

HomeClaw can **search and import OpenClaw skills** from **ClawHub**, then **convert** them into HomeClaw skills under `external_skills/` (config key: `external_skills_dir`).

### Portal UI

1. Ensure the `clawhub` CLI is available on PATH (install OpenClaw/ClawHub).
2. Start the Portal: `python -m main portal`
3. Open **Portal → Skills** → search → **Install**.

### CLI

```bash
python -m main skills search "summarize"
python -m main skills install summarize
```

---

## More

- **Full install and usage:** [InstallationGuide.md](InstallationGuide.md), [HOW_TO_USE.md](HOW_TO_USE.md)
- **Models and mix mode:** [config/llm.yml](config/llm.yml), [README.md](README.md) § Quick Start
