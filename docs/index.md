# HomeClaw

**Your home, your AI, your control.**

HomeClaw is a self-hosted AI assistant that runs on your own hardware — your Mac, Windows PC, or Linux server. Use cloud models (OpenAI, Gemini, DeepSeek), local models (llama.cpp), or both. Memory, plugins, multi-user, and full privacy — all under your roof.

---

## How people use HomeClaw

<div class="grid cards" markdown>

- **Personal assistant on your phone**

    Install HomeClaw on your home computer, connect the [Companion App](companion-app.md) on your iPhone or Android, and chat with your AI from anywhere — at home on Wi-Fi or on the go via a [secure tunnel](remote-access.md).

- **Family AI network**

    Add family members as users, give each person their own [AI friends](friends-and-family.md) with different personalities, and share a single HomeClaw server. Everyone gets private conversations and memory.

- **Developer workstation**

    Use HomeClaw to drive [Cursor and Claude Code](coding-with-homeclaw.md) from your phone or any device. Open projects, run agents, execute commands — all through chat.

- **Team or group chat**

    Connect HomeClaw to [Telegram, Discord, or Slack](channels.md) so your group can talk to the same AI. Each user gets their own identity and memory.

</div>

---

## Get started in 5 minutes

### 1. Install HomeClaw

**Mac / Linux:**

```bash
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
bash install.sh
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/allenpeng0705/HomeClaw.git
cd HomeClaw
.\install.ps1
```

The install script sets up everything and opens the **[Portal](portal.md)** — a web UI where you configure your LLM, create users, and start Core.

### 2. Set up your LLM

The fastest way to start: set a cloud API key.

```bash
export GEMINI_API_KEY="your-key-here"
```

Or use any supported provider (OpenAI, DeepSeek, Anthropic, etc.) — see [Models](models.md). You can also run a local model with llama.cpp for full privacy.

### 3. Start Core

```bash
python -m main start
```

Core is the brain of HomeClaw. It listens on port 9000 and handles all conversations, memory, tools, and plugins.

### 4. Connect the Companion App

Download or build the **[Companion App](companion-app.md)** on your phone or desktop:

1. Set **Core URL** to `http://127.0.0.1:9000` (same machine) or your local IP (same Wi-Fi).
2. Start chatting.

Want to use it from outside your home? Set up a [tunnel with Cloudflare, Pinggy, or ngrok](remote-access.md) — takes 2 minutes.

### 5. Explore

| What to do next | Guide |
|-----------------|-------|
| Use the Portal to manage settings | [Portal Guide](portal.md) |
| Add AI friends with unique personalities | [Friends & Family](friends-and-family.md) |
| Connect Telegram, Discord, or WebChat | [Channels](channels.md) |
| Access HomeClaw from anywhere | [Remote Access (tunnels)](remote-access.md) |
| Use Cursor or Claude Code via HomeClaw | [Coding with HomeClaw](coding-with-homeclaw.md) |
| Browse and install skills from ClawHub | [Companion App → Skills](companion-app.md#skills-clawhub) |

---

## Architecture at a glance

```
┌─────────────────────────────────────────────────┐
│                  HomeClaw Core                   │
│  LLM · Memory · Tools · Plugins · Skills        │
│                  (port 9000)                     │
└────────┬──────────┬──────────┬──────────┬───────┘
         │          │          │          │
    Companion   WebChat    Telegram   Discord
      App       (browser)    bot        bot
   (phone/      :8014
    desktop)
```

All clients talk to the same Core. They share the same AI, memory, and configuration — but each user gets private conversations.

---

## What makes HomeClaw different

| Feature | Description |
|---------|-------------|
| **Companion App** | Flutter app for Mac, Windows, iPhone, Android — chat, voice, manage settings, install skills. [Details →](companion-app.md) |
| **Portal** | Web UI to configure HomeClaw, manage users, start services. [Details →](portal.md) |
| **Cloud + Local models** | Use OpenAI, Gemini, DeepSeek, or local GGUF models — or both together. [Details →](models.md) |
| **AI Friends** | Create multiple AI personalities — study buddy, note-taker, coding assistant. [Details →](friends-and-family.md) |
| **Memory** | RAG + agent memory. Your assistant remembers context across conversations. |
| **Channels** | Reach HomeClaw from Telegram, Discord, Slack, email, WebChat, or CLI. [Details →](channels.md) |
| **Plugins & Skills** | Weather, news, browser, email, and more. Install skills from ClawHub. [Details →](plugins.md) |
| **Remote Access** | Cloudflare Tunnel, Pinggy, ngrok, Tailscale — use HomeClaw from anywhere. [Details →](remote-access.md) |
| **Coding Bridge** | Drive Cursor and Claude Code from your phone. [Details →](coding-with-homeclaw.md) |
| **Multi-user** | Each user gets isolated chat history, memory, and profile. |
| **Self-hosted** | Runs on your machine. Your data stays yours. |

---

## Learn more

- [Getting started (full walkthrough)](getting-started.md)
- [Introducing HomeClaw (vision and design)](introducing-homeclaw.md)
- [Story — why and how it was built](story.md)
- [Help & troubleshooting](help.md)
