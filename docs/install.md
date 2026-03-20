# Install

HomeClaw runs on **macOS**, **Windows**, and **Linux**. Python 3.10–3.12 recommended.

---

## Install script (recommended)

### Mac / Linux

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
bash install.sh
```

If `./install.sh` gives "Permission denied", use `chmod +x install.sh` first or run with `bash install.sh`.

### Windows

Use **PowerShell** (not Command Prompt):

```powershell
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
.\install.ps1
```

If PowerShell says the script "cannot be loaded" (execution policy):

- **Option A:** Run `install.bat` instead (uses Bypass automatically).
- **Option B:** `powershell -ExecutionPolicy Bypass -File .\install.ps1`
- **Option C:** One-time: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

The script checks Python, installs dependencies, and opens the **Portal** at http://127.0.0.1:18472.

### Optional: Dev CLIs

To install Cursor CLI or Claude Code CLI alongside HomeClaw:

```bash
# Mac/Linux
HOMECLAW_INSTALL_CURSOR_CLI=1 HOMECLAW_INSTALL_CLAUDE_CODE=1 bash install.sh
```

```powershell
# Windows
$env:HOMECLAW_INSTALL_CURSOR_CLI="1"; $env:HOMECLAW_INSTALL_CLAUDE_CODE="1"; .\install.ps1
```

---

## Manual install

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
pip install -r requirements.txt
```

---

## Set up your LLM

HomeClaw supports **cloud** models, **local** models, or both together.

- **Cloud:** Set an API key (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`) and configure `cloud_models` in `config/core.yml`. No extra install needed — LiteLLM is included.
- **Local:** Copy llama.cpp binaries into `llama.cpp-master/<platform>/` for your device, download GGUF model files, and configure `local_models` in `config/core.yml`. See [Models](models.md).

---

## Next step

After install: [Run Core](run.md), then open the **[Companion App](companion-app.md)** and start chatting. Or follow the full [Getting started](getting-started.md) walkthrough.
