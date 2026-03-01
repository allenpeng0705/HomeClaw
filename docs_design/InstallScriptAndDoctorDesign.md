# Install Script and Doctor — Design Discussion

This doc outlines a **one-time installation script** and an extended **doctor** command for HomeClaw, and how they fit with the existing Portal Guide and `main.py` commands.

---

## 1. Goals

- **Install script:** Automate (where possible) or guide the user through: Python → Node.js → clone HomeClaw → pip install → llama.cpp → GGUF/Ollama instructions. On success, open the Portal when everything passes.
- **Doctor:** A single command that checks the **whole HomeClaw environment** (Python, Node, config, workspace, skills, llama.cpp/Ollama, LLM connectivity) so users and support can quickly see what's missing or broken.

---

## 2. Current State

| Piece | What it does |
|-------|----------------|
| **`python -m main doctor`** | Checks: core.yml exists and loads; workspace_dir and skills_dir exist; if local LLM: llama-server on PATH or in `llama.cpp-master/<platform>/`; main_llm and embedding_llm health. Does **not** check Python version, Node, or "install prerequisites." |
| **Portal Guide to install** | `portal/guide.py` runs **read-only** checks: Python ≥3.9, deps (pip install), Node.js, llama.cpp binary, GGUF models folder; plus optional "Run doctor" button. No automatic installation. |
| **docs/install.md** | Manual: clone, `pip install -r requirements.txt`, optional llama.cpp/GGUF setup. |
| **Ollama** | Already supported as local model type; `main.py` has `ollama` subcommand (list, pull, set-main). |

---

## 3. Proposed Install Script Flow

Order of steps (we treat "4" as implicit between clone and requirements). **Script location:** install scripts live in **project root**: one **`.sh`** for **Mac and Linux** (`install.sh`), one for **Windows** (`install.ps1`). When run from an existing clone, the script must **detect that it is inside the repo** (e.g. presence of `requirements.txt` and `main.py` or `config/core.yml` at repo root) and support "already in repo" mode (see §3.1).

| Step | Action | Notes |
|------|--------|--------|
| **1** | **Python** | Check if Python is installed and version **≥ 3.9** (enforce 3.9+; docs recommend 3.10+). **If already satisfied, skip.** If missing or too old: install via OS method or print clear instructions and exit. |
| **2** | **Node.js** | Check if Node.js is installed (e.g. `node --version`). **If already present, skip.** Otherwise install via **official method** (see §5). |
| **3** | **HomeClaw source** | Download from GitHub: `git clone` (if git present) or suggest "Download ZIP" and extract. **If download/clone fails, report clearly what happened** (e.g. "git clone failed: &lt;stderr&gt;", "network error", "destination not writable") so the user can fix it. |
| **4** | *(implicit)* | — |
| **5** | **Requirements** | `pip install -r requirements.txt` (from project root). Prefer current Python/venv. Optionally create venv first. |
| **6a** | **llama.cpp** | Try install via **command line** per [llama.cpp install guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md): **Windows** → `winget install llama.cpp`; **Mac** → `brew install llama.cpp` or `sudo port install llama.cpp`; **Linux** → `brew install llama.cpp` or Nix. **If CLI install fails**, tell the user they can use **Method A — Copy binary into project:** "Download the executable for your platform from https://github.com/ggml-org/llama.cpp/releases (e.g. llama-b...-bin-macos-arm64.tar.gz for Mac Apple Silicon, llama-b...-bin-win-cuda-12.4-x64.zip for Windows CUDA). Unzip and copy llama-server (or llama-server.exe on Windows) into llama.cpp-master/&lt;platform&gt;/ in this repo (mac, win_cpu, win_cuda, linux_cpu, or linux_cuda). See llama.cpp-master/README.md for folder layout." |
| **6b** | **GGUF / Ollama** | **No automatic install.** Print instructions. **GGUF:** "Local GGUF models are used by llama.cpp. To add more: Download GGUF models from Hugging Face (huggingface.co). In China you can use ModelScope (modelscope.cn) or HF Mirror (https://hf-mirror.com/). Put .gguf files in the models folder and add entries in config/llm.yml under local_models with path set to the filename (e.g. model.gguf)." **Ollama:** Install from https://ollama.com; then `python -m main ollama pull &lt;model&gt;` and set as main_llm via Portal or config. |
| **7** | **Done** | Print success summary. **If everything passed, open the Portal directly** (start `python -m main portal` and open http://127.0.0.1:18472 in the browser). |

### 3.1 "Already in repo" mode

- The install script is **in the project root** (`install.sh` or `install.ps1`). Before running steps 1–7, **detect if we are inside the HomeClaw repo** (e.g. `requirements.txt` and `main.py` or `config/core.yml` exist relative to script).
- **If we are in the repo:** Support "already cloned" mode: skip step 3 (source download); run steps 1, 2, 5, 6a, 6b as needed (skip 1 and 2 if Python/Node already OK).
- **If we are not in the repo:** Full install from scratch (clone into a target dir, then run remaining steps from there). User must run the script from a location where we can clone, or run from inside an existing clone.

### 3.2 Idempotency

- **Steps 1 & 2:** If acceptable Python version or Node.js is already present, **skip** (no install attempt).
- Other steps: skip or no-op where already satisfied (e.g. requirements already installed, llama-server on PATH or in llama.cpp-master/...) so re-running the script is safe.

### 3.3 Decisions (locked in)

- **Python:** Script enforces **3.9+**; docs recommend **3.10+**.
- **Node:** Use the **official** install method (e.g. from nodejs.org).
- **Scripts:** **Two scripts** in project root: one **`.sh`** for **Mac and Linux** (`install.sh`), one for **Windows** (`install.ps1`).
- **Already in repo:** **Yes** — script must detect repo (see §3.1) and skip clone when run from project root.
- **After install:** **Open Portal when everything passes** (start Portal and open browser to http://127.0.0.1:18472).

---

## 4. Doctor: "Whole Environment" Check

Extend **`python -m main doctor`** so it reports a single "environment" summary, aligned with Portal Guide + connectivity:

| Check | Current doctor | Proposed |
|-------|----------------|----------|
| core.yml | ✅ | Keep |
| workspace_dir | ✅ | Keep |
| skills_dir | ✅ | Keep |
| Python version | ❌ | Add (e.g. "Python 3.11.x") |
| Dependencies (pip) | ❌ | Add (e.g. try import key packages or `pip check`) |
| Node.js | ❌ | Add (optional; "node not in PATH" or version) |
| llama-server (if local LLM) | ✅ | Keep |
| GGUF models folder / Ollama | ❌ | Add (e.g. model_path exists, has .gguf or Ollama reachable) |
| main_llm / embedding_llm health | ✅ | Keep |

Options:

- **Single command:** `python -m main doctor` runs all of the above and prints OK/Issue list (like now, plus new lines).
- **Flag for "install prereqs only":** e.g. `python -m main doctor --prereqs` to only check Python, Node, llama.cpp, models dir (no Core config or LLM health), for use before first run.
- **Structured output:** Optional `--json` for scripts/Portal to consume.

Reuse logic from **`portal/guide.py`** where possible (Python version, Node, llama binary, models dir) so doctor and Portal Guide stay in sync; doctor can call into a small shared module or duplicate the checks to avoid pulling Portal into Core startup.

---

## 5. Script Location and OS Support

- **Location:** **Two scripts** in project root — `install.sh` (Mac and Linux) and `install.ps1` (Windows). Optionally a small launcher (e.g. `curl ... | bash` or `irm ... | iex`) that clones repo and runs the appropriate script.
- **OS:** Explicitly support **macOS**, **Windows**, **Linux**. Each step's "install" path differs:
  - **Python:** python.org installers, or winget (Windows), brew/apt (Mac/Linux). Script can detect and suggest; only auto-install where safe (e.g. winget/brew).
  - **Node:** Use the **official** install method (e.g. from nodejs.org).
  - **llama.cpp:** Follow [install.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md): **Winget** (Windows), **Homebrew** (Mac/Linux), **MacPorts** (Mac), **Nix** (Mac/Linux). If CLI install fails, show Method A (copy binary into llama.cpp-master/&lt;platform&gt;/) as fallback.

---

## 6. GGUF / Ollama Step (No Auto-Install)

- **GGUF:** Use the expanded text: "Local GGUF models are used by llama.cpp. To add more: Download GGUF models from Hugging Face (huggingface.co). In China you can use ModelScope (modelscope.cn) or HF Mirror (https://hf-mirror.com/). Put .gguf files in the models folder and add entries in config/llm.yml under local_models with path set to the filename (e.g. model.gguf)."
- **Ollama:** "Install Ollama from https://ollama.com; then run `python -m main ollama pull <model>` and set as main_llm via Portal or config." No scripted Ollama install to keep script simple and avoid platform-specific installers.

---

## 7. After Install: Open Portal

When all steps succeed:

- Print: "Installation complete. Starting Portal..."
- **Open Portal when everything passes:** Automatically start Portal and open http://127.0.0.1:18472 in the default browser (like `python -m main portal` with browser open).

---

## 8. Summary

| Deliverable | Description |
|-------------|-------------|
| **Install script** | Steps 1–7; skip Python/Node if already OK; clear error on clone failure; llama.cpp fallback = Method A (copy binary); GGUF text with Hugging Face / ModelScope / HF Mirror; **two scripts** (`.sh` for Mac and Linux, `.ps1` for Windows); detect repo for "already in repo" mode; open Portal when all pass. |
| **Doctor** | Extend `run_doctor()` to include Python, deps, Node, llama.cpp, models/Ollama; keep existing config and LLM health checks; optional `--prereqs` and `--json`. |
| **Docs** | Update docs/install.md (and README if needed) to mention scripted install and `python -m main doctor`. |

Next steps: (1) ~~Implement install scripts~~ Done — `install.sh` and `install.ps1` in project root. (2) Extend doctor and optionally add a shared "environment checks" module used by both doctor and Portal guide.
