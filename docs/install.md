# Install

HomeClaw runs on **macOS**, **Windows**, and **Linux**. The **first step** for most users is to run the install script.

---

## 1. Install script (recommended)

Run the install script from the project root. It checks Python (3.9+), installs dependencies, and opens the **Portal** at http://127.0.0.1:18472 when done.

### Mac / Linux

1. Clone the repo and go into it:
   ```bash
   git clone https://github.com/allenpeng0705/HomeClaw.git
   cd HomeClaw
   ```
2. Run the install script. Either:
   - **Option A:** Make it executable (one-time), then run:
     ```bash
     chmod +x install.sh
     ./install.sh
     ```
   - **Option B:** Run with `bash` (no chmod needed):
     ```bash
     bash install.sh
     ```

If `./install.sh` fails with "Permission denied", use `chmod +x install.sh` or `bash install.sh`. You can also run from a parent directory (e.g. `cd ~/projects && bash install.sh`); the script will clone the repo into `./HomeClaw` if needed.

#### Optional: install Dev CLIs (Cursor CLI / Claude Code CLI)

- Cursor CLI (for Cursor Bridge): set `HOMECLAW_INSTALL_CURSOR_CLI=1`
- Claude Code CLI (for ClaudeCode friend): set `HOMECLAW_INSTALL_CLAUDE_CODE=1`

Example:

```bash
HOMECLAW_INSTALL_CURSOR_CLI=1 HOMECLAW_INSTALL_CLAUDE_CODE=1 bash install.sh
```

### Windows

1. **Use PowerShell** (not Command Prompt). Open **PowerShell**: Win + X → "Windows PowerShell" or "Terminal", or search for "PowerShell".
2. Clone the repo and go into it:
   ```powershell
   git clone https://github.com/allenpeng0705/HomeClaw.git
   cd HomeClaw
   ```
3. Run the install script: **`.\install.ps1`** or **`install.bat`** (double-click in Explorer or run `install.bat` in CMD):
   ```powershell
   .\install.ps1
   ```

#### Optional: install Dev CLIs (Cursor CLI / Claude Code CLI)

- PowerShell:

```powershell
$env:HOMECLAW_INSTALL_CURSOR_CLI="1"
$env:HOMECLAW_INSTALL_CLAUDE_CODE="1"
.\install.ps1
```

- Or using `install.bat` flags:
  - `install.bat cursor`
  - `install.bat claude`
  - `install.bat cursor claude`

**If PowerShell says the script "cannot be loaded" or "is not digitally signed" (execution policy):**

- **Option A:** Run **`install.bat`** instead (uses Bypass automatically).
- **Option B:** Bypass for this run only:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\install.ps1
  ```
- **Option C:** Allow scripts for your user (one-time): `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`, then run `.\install.ps1` again.

You can also run the script from a parent directory; it will clone into `.\HomeClaw` if needed. After the script finishes, use the Portal to manage config and start Core, or continue with [Run](run.md) and [Getting started](getting-started.md).

---

## 2. Manual install (alternative)

If you prefer not to use the script:

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
pip install -r requirements.txt
```

You need **Python** 3.10–3.12 (recommended). For faster installs in China, use a mirror (e.g. `-i https://pypi.tuna.tsinghua.edu.cn/simple`).

---

## 3. Optional: cloud or local LLM

HomeClaw supports **cloud** and **local** models (or both together for better capability and cost).

- **Cloud:** Set the API key as an environment variable (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`) and add the model to `cloud_models` in `config/core.yml`. No extra install beyond `requirements.txt` (LiteLLM is included).
- **Local:** To run **local GGUF models**, you need a llama.cpp server. **Copy llama.cpp's binary distribution** into `llama.cpp-master/<platform>/` for your device type (e.g. `mac/`, `win_cuda/`, `linux_cpu/` — see `llama.cpp-master/README.md` in the repo); this is used for both main and embedding local models. Download GGUF model files (e.g. from Hugging Face) into a `models/` folder and configure `local_models` in `config/core.yml`. See [Models](models.md) for paths and ports.

---

## 4. Next step

After install, see [Run](run.md) to start Core, then use the **Companion app** (set Core URL in Settings, add your user) and/or run a **channel** (e.g. `python -m channels.run webchat`). If you used the install script, the Portal is already open at http://127.0.0.1:18472—you can manage config and start Core from there. For full setup (config, users, memory), see [Getting started](getting-started.md) and the main [HOW_TO_USE.md](https://github.com/allenpeng0705/HomeClaw/blob/main/HOW_TO_USE.md) in the repo.
