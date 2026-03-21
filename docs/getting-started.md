# Getting started

This guide takes you from zero to chatting with HomeClaw. By the end, you'll have Core running and be talking to your AI from the Companion App.

---

## Step 1: Install HomeClaw

### Mac / Linux

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
bash install.sh
```

### Windows

```powershell
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
.\install.ps1
```

If PowerShell blocks the script, use `install.bat` instead, or run:
`powershell -ExecutionPolicy Bypass -File .\install.ps1`

### What the install script does

1. Checks for Python 3.9+ and Node.js (installs them if missing)
2. Runs `pip install -r requirements.txt`
3. Sets up llama.cpp (for local models)
4. Opens the **[Portal](portal.md)** in your browser at http://127.0.0.1:18472

### Manual install (if you prefer)

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
pip install -r requirements.txt
```

---

## Step 2: Use the Portal to configure

The **[Portal](portal.md)** is a web UI that opens automatically after install. If you need to open it later:

```bash
python -m main portal
```

In the Portal you can:

- **Create an admin account** (first time)
- **Set your LLM** — pick a cloud model and enter your API key, or configure a local model
- **Manage users** — add family members or yourself
- **Start Core** — launch the AI engine directly from the Portal

See the full [Portal Guide](portal.md) for details.

### Quick LLM setup (no Portal needed)

If you prefer the command line, set an API key and go:

```bash
# Google Gemini (recommended for getting started)
export GEMINI_API_KEY="your-key-here"

# Or OpenAI
export OPENAI_API_KEY="your-key-here"

# Or DeepSeek
export DEEPSEEK_API_KEY="your-key-here"
```

See [Models](models.md) for all supported providers and local model setup.

---

## Step 3: Start Core

```bash
python -m main start
```

Core is the brain of HomeClaw. It handles all conversations, memory, tools, and plugins. By default it listens on **port 9000**.

**Verify it's running:**

```bash
curl -s http://127.0.0.1:9000/ready
# Should return 200
```

**Check your setup:**

```bash
python -m main doctor
```

This checks config, workspace, and LLM connectivity. Fix any reported issues before continuing.

---

## Step 4: Connect the Companion App

The **[Companion App](companion-app.md)** is the easiest way to use HomeClaw. It works on Mac, Windows, iPhone, and Android.

### Get the app

**Build from source** (in the repo):

```bash
cd clients/HomeClawApp
flutter pub get
flutter run
```

Or install from **TestFlight / App Store** if a build is available.

### Connect to Core

1. Open the Companion App
2. Go to **Settings**
3. Set **Core URL** to:
    - `http://127.0.0.1:9000` — if the app is on the same machine as Core
    - `http://192.168.x.x:9000` — if on the same Wi-Fi (replace with your machine's local IP)
4. Start chatting!

### Connect from anywhere (phone on cellular, laptop away from home)

To use the Companion App from outside your home network, set up a tunnel:

| Method | Setup time | Best for |
|--------|-----------|----------|
| **[Pinggy](remote-access.md#pinggy-built-in)** | 1 min | Built into HomeClaw; scan QR code to connect |
| **[Cloudflare Tunnel](remote-access.md#cloudflare-tunnel)** | 5 min | Free, stable public URL |
| **[ngrok](remote-access.md#ngrok)** | 3 min | Quick testing, easy setup |
| **[Tailscale](remote-access.md#tailscale)** | 5 min | Private network, no public exposure |

See the full [Remote Access guide](remote-access.md) for step-by-step instructions.

---

## Step 5: Add a channel (optional)

Already use Telegram, Discord, or prefer a browser? Add a **[channel](channels.md)** so you can reach HomeClaw from your favorite platform:

```bash
python -m channels.run webchat     # browser at http://localhost:8014
python -m channels.run telegram    # Telegram bot
python -m channels.run discord     # Discord bot
```

The Companion App and all channels share the same Core, memory, and user identity. See [Channels](channels.md) for setup.

---

## Step 6: Set up your AI friends (optional)

HomeClaw lets you create multiple AI personalities — each with its own conversation and memory:

- **HomeClaw** — Your main general assistant (default)
- **Reminder** — Scheduling and reminders
- **Note** — Note-taking
- **Cursor** — Open projects and run agents in Cursor IDE
- **ClaudeCode** — Run Claude Code CLI tasks
- Custom friends with any personality you design

See [Friends & Family](friends-and-family.md) to add friends and set up a family AI network.

---

## What's next?

| Goal | Guide |
|------|-------|
| Learn about the Portal | [Portal Guide](portal.md) |
| Set up remote access | [Remote Access](remote-access.md) |
| Add family members and AI friends | [Friends & Family](friends-and-family.md) |
| Connect Telegram or Discord | [Channels](channels.md) |
| Use Cursor or Claude Code | [Coding with HomeClaw](coding-with-homeclaw.md) |
| Install skills from ClawHub | [Companion App → Skills](companion-app.md#skills-clawhub) |
| Troubleshoot issues | [Help](help.md) |
