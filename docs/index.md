# HomeClaw

**Your home, your AI, your control.**

HomeClaw is an AI assistant that runs on your own hardware. It supports cloud models (OpenAI, Gemini, DeepSeek), local models (llama.cpp), or both together. Memory, plugins, and multi-user — all self-hosted.

---

## Get started in 3 steps

### 1. Install

Clone the repo and run the install script:

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

The script installs dependencies and opens the **Portal** (web UI) when done. See [Install](install.md) for details.

### 2. Configure your LLM

Set an API key for a cloud model (fastest way to start):

```bash
# Example: Google Gemini
export GEMINI_API_KEY="your-key-here"
```

Or configure a local model — see [Models](models.md).

### 3. Start Core and use the Companion App

```bash
python -m main start
```

Then open the **[Companion App](companion-app.md)** on your Mac, Windows, iPhone, or Android — set the Core URL to `http://127.0.0.1:9000` and start chatting.

The Companion App is the easiest way to use HomeClaw: chat, voice, file attachments, manage config, and install skills — all from one app. **[Learn more about the Companion App →](companion-app.md)**

---

## Other ways to connect

Already have Telegram, Discord, or prefer a browser? Run a **[channel](channels.md)** alongside (or instead of) the Companion App — they all talk to the same Core and share the same memory.

```bash
python -m channels.run webchat     # browser at http://localhost:8014
python -m channels.run telegram    # Telegram bot
python -m channels.run discord     # Discord bot
```

---

## What makes HomeClaw different

| | |
|---|---|
| **Companion App** | Flutter app for Mac, Windows, iPhone, Android — chat, voice, manage config, install skills. [Details →](companion-app.md) |
| **Cloud + Local models** | Use OpenAI, Gemini, DeepSeek, or local GGUF models via llama.cpp — or both together. [Details →](models.md) |
| **Memory** | RAG + agent memory. Your assistant remembers context across conversations. |
| **Plugins** | Built-in (Python) and external (any language). Weather, news, email, browser, and more. [Details →](plugins.md) |
| **Skills** | OpenClaw-style workflows the LLM executes with tools. Install from ClawHub via the Companion App. |
| **Multi-user** | Each user gets isolated chat history, memory, and profile. |
| **Self-hosted** | Runs on your machine. Your data stays yours. |

---

## Learn more

- [Getting started (full walkthrough)](getting-started.md)
- [Introducing HomeClaw](introducing-homeclaw.md)
- [Story — why and how it was built](story.md)
- [Help & troubleshooting](help.md)
