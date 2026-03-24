<p align="center">
  <img src="HomeClaw_Banner.jpg" alt="HomeClaw Banner">
</p>

<p align="center">
  <a href="https://www.homeclaw.cn"><strong>www.homeclaw.cn</strong></a>
</p>

# HomeClaw

HomeClaw is a local-first AI assistant that runs on your machine.

**One Core, many ways to connect**: Companion app, WebChat, and channels all talk to the same assistant and memory.

What HomeClaw gives you:

- one `Core` backend (FastAPI)
- **local/cloud/mix** model routing
- tools, skills, and plugins (external plugins can be any language)
- companion app + channels (Mac/Windows/Linux/iPhone/Android + messaging platforms)
- Cursor + Claude Code bridge (start/continue coding tasks from mobile)
- multi-user, user sandbox, and optional multi-instance federation

---

## Start Here

- **Install first**: [QuickStart.md](QuickStart.md)
- **Portal setup**: `python -m main portal` -> `http://127.0.0.1:18472`
- **Run Core**: `python -m main start`
- **Full docs**: [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/)

## Quick Start

[Open `QuickStart.md`](QuickStart.md) for the full install and first-chat flow.

---

## Why HomeClaw

### 1) Mix mode: save cost, keep quality

HomeClaw can route each turn to local or cloud models.  
Simple/private tasks stay local; harder tasks go cloud when needed.

### 2) Plugins and skills: extend ability fast

- Plugins add capabilities (built-in or external service).
- Skills add reusable workflows (including ClawHub/OpenClaw-style skills).

### 3) Channels and Companion: one assistant everywhere

Use WebChat, Telegram/Discord/etc., and Companion app together.  
They share one Core and one memory.

### 4) Code from your phone (Cursor + Claude Code bridge)

HomeClaw can connect your coding workflow to mobile chat.  
You can start or continue coding tasks from your phone, then sync back to desktop coding tools.

### 5) Family/team and federation ready

Multi-user support in one Core, with optional multi-instance federation for remote friends/agents.

---

## What You Can Build

- Personal/local assistant (GGUF + llama.cpp)
- Cloud assistant (OpenAI/Gemini/DeepSeek/etc.)
- Mix-mode assistant (auto local vs cloud by task)
- Team assistant (multi-user in one Core)
- Channel bots (WebChat, Telegram, Discord, Slack, etc.)
- Federated network (multiple HomeClaw instances)

---

## Simple Examples

### Example A: Run WebChat channel

```bash
python -m channels.run webchat
```

Open the URL printed in terminal (default around `http://localhost:8014`).

### Example B: Local + cloud mix

In `config/llm.yml`, set:

- `main_llm_mode: mix`
- `main_llm_local: local_models/<your_local_model>`
- `main_llm_cloud: cloud_models/<your_cloud_model>`

Then ask normal questions; router chooses model per request.

### Example C: Run Companion + channel together

Run Core once, then use both:

- Companion app -> `http://127.0.0.1:9000`
- WebChat/Telegram/Discord channel process

---

## Documentation

- Main docs: [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/)
- Quick start details: `QuickStart.md`
- Install details: `InstallationGuide.md`
- Full usage: `HOW_TO_USE.md`
- Design notes: `docs_design/`

---

## Contributing / License

- Contributing: `CONTRIBUTING.md`
- License: Apache 2.0 (`LICENSE`)
