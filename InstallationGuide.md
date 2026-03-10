# HomeClaw Installation Guide

Short guide to installing HomeClaw and checking your environment.

---

## Quick start: install scripts

| OS | Command |
|----|--------|
| **Mac / Linux** | From project root: `./install.sh` — or from a parent directory: the script will clone into `./HomeClaw` and continue. |
| **Windows** | From project root in **PowerShell**: `.\install.ps1`. If you get "cannot be loaded... not digitally signed", run: `powershell -ExecutionPolicy Bypass -File .\install.ps1` or once: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`. |

The script will:

1. **Python** — Check for 3.9+ (skip if OK); try to install if missing.
2. **Node.js** — Check for Node (skip if OK); try to install if missing.
3. **Source** — Use existing clone or clone from GitHub (if clone fails, the script reports what went wrong).
4. **Dependencies** — Run `pip install -r requirements.txt`.
5. **llama.cpp** — Try package manager (e.g. `brew install llama.cpp`, `winget install llama.cpp`); if that fails, the script prints how to download the binary and put it in `llama.cpp-master/<platform>/`.
6. **GGUF / Ollama** — Prints where to get GGUF models (Hugging Face; in China: ModelScope, HF Mirror) and how to use Ollama.
7. **Portal** — When everything passes, starts the Portal and opens http://127.0.0.1:18472 in your browser.

**Already in the repo?** Run the script from the project root; it will skip cloning and only run the steps that are still needed (Python/Node are skipped if already OK).

**pip 403 Forbidden (e.g. Tsinghua mirror)?** The install script will retry with official PyPI. Or run manually: `pip install -r requirements.txt -i https://pypi.org/simple`.

**Dependency conflicts about semantic-kernel?** Pip may warn that `semantic-kernel` expects older versions of aiofiles, numpy, openai, pydantic, etc. HomeClaw does not use semantic-kernel (it is a transitive dependency of Cognee). You can ignore these warnings; Core and Cognee memory work with the installed versions. If you hit a real runtime error, try a fresh venv or report the issue.

---

## Manual install (summary)

1. **Clone:** `git clone https://github.com/allenpeng0705/HomeClaw.git && cd HomeClaw`
2. **Python:** 3.9+ (3.10–3.12 recommended). Install from python.org or your package manager.
3. **Dependencies:** `pip install -r requirements.txt`. In China you can use a mirror (e.g. `-i https://pypi.tuna.tsinghua.edu.cn/simple`). If you get **403 Forbidden** from a mirror, use official PyPI: `pip install -r requirements.txt -i https://pypi.org/simple`.
4. **Node.js** (optional, for some plugins): Install from [nodejs.org](https://nodejs.org).
5. **llama.cpp** (for local GGUF): Install via [llama.cpp install guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md) (e.g. `brew install llama.cpp`, `winget install llama.cpp`), or download a binary from [releases](https://github.com/ggml-org/llama.cpp/releases) and put `llama-server` (or `llama-server.exe`) in `llama.cpp-master/<platform>/`.
6. **GGUF models:** Put `.gguf` files in the `models/` folder and add entries in `config/llm.yml` under `local_models`. Or use **Ollama**: install from [ollama.com](https://ollama.com), then `python -m main ollama pull <model>` and set as main in config.

---

## Check your environment: doctor

After installing, run:

```bash
python -m main doctor
```

This checks config, workspace, skills dir, llama-server (if using local LLM), and main/embedding LLM connectivity. Fix any reported issues before starting Core.

---

## Configure and run: Portal

The **Portal** is the local web UI for config, onboarding, and starting Core and channels.

- **Start:** `python -m main portal` — by default it opens http://127.0.0.1:18472 in your browser.
- **First time:** Create an admin account (username/password); then use Dashboard, **Guide to install**, **Manage settings**, and **Start channel** as needed.

For using the Portal from a **web browser** (same machine) or from the **Companion app** (remote via Core), see **[docs_design/PortalUsage.md](docs_design/PortalUsage.md)**.

---

## Summary

| What | Where |
|------|--------|
| **Install script (Mac/Linux)** | `./install.sh` (project root) |
| **Install script (Windows)** | `.\install.ps1` (project root) |
| **Manual install** | Clone → pip install → optional Node, llama.cpp, GGUF/Ollama (see above) |
| **Environment check** | `python -m main doctor` |
| **Portal (config & onboarding)** | `python -m main portal` → http://127.0.0.1:18472 |
| **Portal usage (web & Companion)** | [docs_design/PortalUsage.md](docs_design/PortalUsage.md) |
| **Install design (scripts, doctor)** | [docs_design/InstallScriptAndDoctorDesign.md](docs_design/InstallScriptAndDoctorDesign.md) |
| **Mac/Linux Homebrew (tap + formula)** | [docs_design/DistributionMacLinuxChecklist.md](docs_design/DistributionMacLinuxChecklist.md) |
