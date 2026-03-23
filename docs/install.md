# Install

HomeClaw runs on **macOS**, **Windows**, and **Linux**. Python 3.11 or higher required.

---

## Prerequisites

Before installing HomeClaw, make sure you have the following:

- **Python 3.11 or higher** — Check with `python --version` or `python3 --version`
- **Git** — For cloning the repository
- **pip** — Python package manager (usually comes with Python)

!!! note "Windows Users"
    If you encounter C++ build errors on Windows, install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/).

---

## Simple Installation (Recommended)

The easiest way to install HomeClaw is using the provided installation scripts. These scripts handle all the setup automatically.

### Mac & Linux

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
chmod +x install.sh
./install.sh
```

If `./install.sh` gives "Permission denied", use `chmod +x install.sh` first or run with `bash install.sh`.

The script will automatically:

- Clone the repository (if not already cloned)
- Install Python dependencies
- Copy llama.cpp binary distributions
- Download required models
- Set up configuration files

### Windows

For Windows, you can use either PowerShell or Command Prompt:

**Option 1: PowerShell**

```powershell
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
.\install.ps1
```

If PowerShell says the script "cannot be loaded" (execution policy):

- **Option A:** Run `install.bat` instead (uses Bypass automatically).
- **Option B:** `powershell -ExecutionPolicy Bypass -File .\install.ps1`
- **Option C:** One-time: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**Option 2: Command Prompt**

```cmd
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
install.bat
```

!!! success "What the scripts do"
    The installation scripts automate the entire setup process, including cloning the code, installing dependencies, setting up llama.cpp binaries, and downloading models. This is the recommended method for most users.

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

## Manual Installation

If you prefer to install HomeClaw manually without using the installation scripts, follow these steps:

### Step 1: Clone the Repository

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Copy llama.cpp Binary Distributions

Download and copy the appropriate llama.cpp binaries for your platform:

- **Mac:** Copy binaries to the appropriate directory
- **Linux:** Copy binaries to the appropriate directory
- **Windows:** Copy binaries to the appropriate directory

### Step 4: Download Models

Download the required AI models. The specific models depend on your configuration in `config/llm.yml`.

### Step 5: Configure and Run

Edit the configuration files as needed, then run HomeClaw:

```bash
python -m main start
```

!!! warning "Note"
    Manual installation requires more technical knowledge. We recommend using the installation scripts unless you have specific requirements for custom setup.

---

## Set up your LLM

HomeClaw supports **cloud** models, **local** models, or both together.

- **Cloud:** Set an API key (e.g. `OPENAI_API_KEY`, `GEMINI_API_KEY`) and configure `cloud_models` in `config/core.yml`. No extra install needed — LiteLLM is included.
- **Local:** Copy llama.cpp binaries into `llama.cpp-master/<platform>/` for your device, download GGUF model files, and configure `local_models` in `config/core.yml`. See [Models](models.md).

---

## Verify Installation

After installation, verify that everything is working correctly:

```bash
python -m main start
```

If HomeClaw starts without errors and you can access the web interface, congratulations! HomeClaw is installed successfully.

---

## Troubleshooting

### Python not found

Make sure Python is installed and added to your system PATH. On Mac, you may need to use `python3` instead of `python`.

### Pip not found

Ensure pip is installed. You can install it using: `python -m ensurepip --upgrade`

### Permission denied

On Mac/Linux, make sure the install script has execute permissions: `chmod +x install.sh`

### Build errors on Windows

Install Visual C++ Build Tools from Microsoft's website.

### Need more help?

Check the [GitHub issues](https://github.com/allenpeng0705/HomeClaw/issues) or [full documentation](https://allenpeng0705.github.io/HomeClaw/) for more detailed troubleshooting guides.

---

## Next Steps

Now that HomeClaw is installed, you can:

- [Learn how to use HomeClaw](run.md)
- [Set up the Companion app](companion-app.md)
- [Access the Portal](portal.md)
- [Read the full documentation](https://allenpeng0705.github.io/HomeClaw/)
