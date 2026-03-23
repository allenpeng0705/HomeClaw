# QuickStart

Get HomeClaw up and running in minutes.

Follow these simple steps to install, configure, and start using HomeClaw with the Companion app, Portal, and remote access.

## Prerequisites

Before installing HomeClaw, make sure you have:

- **Python 3.11+** — Required for running HomeClaw Core
- **Git** — For cloning the repository
- **API Keys (Optional)** — For cloud LLM models (OpenAI, Anthropic, etc.)

!!! tip "Local Models Work Too"
    HomeClaw can run with local models only. Cloud API keys are optional for Mix Mode.

---

## Suggested Models

HomeClaw works with local GGUF models. **Only the main chat model is required to run HomeClaw.** Other models are optional and enhance specific features.

!!! warning "Required: Main Chat Model"
    This is the only model you need to get started. All other models below are optional enhancements.

### Main Chat Model (Required)

The main model handles conversations and tool calls. Choose one:

```
Qwen3VL-4B-Instruct-Q4_K_M.gguf
mmproj-Qwen3VL-4B-Instruct-F16.gguf
```

**Alternative options:**

- `Qwen3VL-2B-Instruct-Q4_K_M.gguf` — Lighter, faster, less VRAM
- `Qwen3-VL-8B-Instruct-Q4_K_M.gguf` — More capable, requires more VRAM
- `gpt-oss-20b-Q4_K_M.gguf` — Text-only, larger model

### Embedding Model (Optional)

Used for memory, RAG, and semantic search. Without this, memory features will be limited:

```
Qwen3-Embedding-0.6B-Q8_0.gguf
```

### Vision Model (Optional)

For image understanding. The Qwen3VL models above have built-in vision support, so you only need a separate vision model if using a text-only main model:

```
Qwen3VL-2B-Instruct-Q4_K_M.gguf
mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf
```

### Tool Selection Model (Optional)

Fine-tuned for function calling, improves tool accuracy:

```
Qwen3-4B-Function-Calling-Pro.gguf
```

!!! success "Download Models"
    Download models from [Hugging Face](https://huggingface.co/models?sort=trending&search=gguf) — Search for the GGUF versions. Place them in the `models/` folder.

---

## Step 1: Install HomeClaw

Clone the repository and run the installation script for your platform.

### Clone Repository

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
```

### Run Install Script

Choose the script for your operating system:

=== "Mac / Linux"

    ```bash
    chmod +x install.sh
    ./install.sh
    ```

    The script will:

    - Install Python dependencies
    - Download llama.cpp binaries
    - Download default models (optional)
    - Create default configuration files

=== "Windows (PowerShell)"

    ```powershell
    .\install.ps1
    ```

=== "Windows (Command Prompt)"

    ```cmd
    install.bat
    ```

[→ Detailed installation guide](install.md)

---

## Step 2: Run Core

Start the HomeClaw Core server to begin using your AI assistant.

### Start Core

```bash
python -m main start
```

### What Happens

- Core starts on default port **9000**
- WebChat becomes available at `http://127.0.0.1:9000`
- API endpoints are ready for Companion app
- Default model configuration is loaded from `config/llm.yml`

### Verify Core is Running

Open your browser and visit:

```
http://127.0.0.1:9000
```

### Configure Models (Optional)

Edit `config/llm.yml` to configure your models:

- **Local models:** Place GGUF files in `models/` folder
- **Cloud models:** Add API keys for OpenAI, Anthropic, etc.
- **Mix Mode:** Enable automatic routing between local and cloud

[→ How to configure models](models.md)

---

## Step 3: Companion App

Download and configure the Companion app for the best HomeClaw experience.

### Download Companion App

Get the app for your platform from [GitHub Releases](https://github.com/allenpeng0705/HomeClaw/releases):

| Platform | Download |
|----------|----------|
| iPhone | App Store (coming soon) or build from source |
| Android | Download APK from GitHub Releases |
| Mac | Download .dmg from GitHub Releases |
| Windows | Download .exe from GitHub Releases |

### Connect to Core

1. Open Companion app
2. Go to **Settings**
3. Enter Core URL: `http://127.0.0.1:9000` (for local)
4. If authentication is enabled, enter your API key
5. Tap **Connect**

### Features

- **Chat:** Talk to your AI assistant
- **Friends:** AI friends and family members
- **Manage Core:** Edit configuration files
- **Skills:** Install skills from ClawHub

[→ Companion app guide](companion-app.md)

---

## Step 4: Portal (Optional)

Use the Portal web UI to manage and configure HomeClaw easily.

### Start Portal

```bash
python -m main portal
```

### Access Portal

Open your browser and navigate to:

```
http://127.0.0.1:18472
```

### Portal Features

- **Configuration:** Edit core.yml, llm.yml, user.yml
- **User Management:** Add users and AI friends
- **Skills:** Search and install from ClawHub
- **Start/Stop:** Control Core and channels

!!! info "Local Only"
    Portal is for local management only. It cannot be accessed remotely.

[→ Portal guide](portal.md)

---

## Step 5: Remote Access

Set up remote access to use HomeClaw from anywhere.

### Enable Authentication

First, secure your Core with API key authentication:

```yaml
# config/core.yml
auth_enable: true
auth_api_key: your-secure-api-key-here
```

### Choose a Tunnel Method

#### Pinggy (Recommended)

Built-in support with QR code scanning:

```yaml
# config/core.yml
pinggy:
  token: your-pinggy-token
  enabled: true
```

#### Cloudflare Tunnel

Free, reliable, no account needed:

```bash
cloudflared tunnel --url http://localhost:9000
```

#### Tailscale

Private mesh VPN, works like local network:

```bash
tailscale up
```

### Connect Companion Remotely

1. Start your tunnel service
2. Get the public URL (e.g., `https://xxx.trycloudflare.com`)
3. In Companion app, enter this URL as Core URL
4. Enter your API key
5. Connect and chat from anywhere

[→ Remote access guide](remote-access.md)

---

## Step 6: Cursor & Claude Code

Use Cursor IDE and Claude Code from your phone for remote coding.

### Prerequisites

- **Cursor IDE** installed on your dev machine
- **Claude Code CLI** installed (`npm install -g @anthropic-ai/claude-code`)
- **API Keys:** Cursor API key or Anthropic/Minimax key

### Start Cursor Bridge

```bash
python -m external_plugins.cursor_bridge.server
```

### Add Friends in user.yml

```yaml
users:
  - id: yourname
    friends:
      - name: Cursor
        preset: cursor
      - name: ClaudeCode
        preset: claudecode
```

### Use from Companion

1. Open Companion app
2. Select **Cursor** or **ClaudeCode** friend
3. Say "Open /path/to/project in Cursor"
4. Send coding tasks like "Add unit tests for auth module"
5. See results returned to your phone

!!! tip "Mobile Tip"
    For mobile use, set up remote access first so your phone can reach Core, and ensure Core can reach the bridge on your dev machine.

[→ Cursor & Claude Code guide](coding-with-homeclaw.md)

---

## Next Steps

Now that you have HomeClaw running, explore more features:

| Guide | Description |
|-------|-------------|
| [Configure Models](models.md) | Set up local models, cloud APIs, and Mix Mode |
| [Family Social Network](friends-and-family.md) | Add family members and AI friends |
| [Install Skills](writing-plugins-and-skills.md) | Extend HomeClaw with skills from ClawHub |
| [Full Documentation](https://allenpeng0705.github.io/HomeClaw/) | Complete guides and API reference |
