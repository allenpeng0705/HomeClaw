# HomeClaw

**AI assistant that runs on your machine. Your data, your control.**

HomeClaw is a self-hosted AI assistant that runs on your own hardware — your Mac, Windows PC, or Linux server. Use cloud models (OpenAI, Gemini, DeepSeek), local models (llama.cpp), or both. Memory, plugins, multi-user, and full privacy — all under your roof.

[GitHub](https://github.com/allenpeng0705/HomeClaw){ .md-button .md-button--primary } [Get Started](getting-started.md){ .md-button } [Documentation](https://allenpeng0705.github.io/HomeClaw/){ .md-button }

## Features

### Local-First
Runs on Mac, Windows, Linux. Your data stays on your machine.

### Mix Mode
Auto-route between local and cloud models. Save cost, keep quality.

### Plugins & Skills
Extend with plugins in any language. Install skills from ClawHub.

### Family Social
Private social network. AI friends, family members, secure messaging.

### Companion App
Mac, Windows, iPhone, Android. Chat, manage, and control remotely.

### Cursor & ClaudeCode
Remote coding from your phone. AI agents on your dev machine.

---

## Start here — find what you need

### [How to install](install.md)
**First step:** Clone repo, then run install script. **Mac/Linux:** `chmod +x install.sh` then `./install.sh`. **Windows:** use **PowerShell**, run `.\install.ps1` or `install.bat`.

### [How to use HomeClaw](run.md)
Run Core, then chat via Companion app or channels (WebChat, Telegram, etc.). All use the same Core and memory.

### [Companion app](companion-app.md)
Where to find it: **clients/HomeClawApp/** in the repo. Available for Mac, Windows, iPhone, and Android.

### [Portal](portal.md)
Web UI to manage config and start Core/channels. Run `python -m main portal` → http://127.0.0.1:18472

### [Family Social Network](friends-and-family.md)
Create a private social network for your family. Share moments, chat, and stay connected securely within your home network.

### [Remote Access](remote-access.md)
Access HomeClaw from anywhere using Pinggy, Cloudflare Tunnel, or Ngrok. Set up secure remote connections easily.

### [Skills from ClawHub](writing-plugins-and-skills.md)
Extend HomeClaw with skills from ClawHub registry. Search, download, convert and install OpenClaw skills easily.

### [Cursor and ClaudeCode](coding-with-homeclaw.md)
Use Cursor IDE and Claude Code CLI from your phone. Open projects, run AI agents, and see results remotely.

---

## Why HomeClaw

HomeClaw is a local-first AI assistant: one installation is one agent, with the same memory, tools, and plugins no matter how you connect. It runs on **Mac, Windows, and Linux** (Python), and you can extend it with **external plugins in any language**. Below are the main reasons to use it, in order of impact.

### 1. Mix mode — save cost

![Mix mode](assets/section-mix-mode.png){ align=right width=280 }

Cloud APIs are powerful but expensive; local models are free but sometimes not enough. HomeClaw's **mix mode** fixes that: for every user message, a small router decides once—local or cloud—for the whole turn. Simple or private tasks go to your local model; complex or uncertain ones go to the cloud. You get one model per turn, automatic routing, and **usage reports** (in chat or via API) so you can see how much went to the cloud and tune rules. Default to local when in doubt and you keep cost under control without giving up cloud when you need it.

[Learn more about mix mode](mix-mode-and-reports.md)

### 2. Plugins and skills — extend ability

![Plugins and skills](assets/section-plugins-skills.png){ align=right width=280 }

**Plugins** add one capability at a time. Built-in plugins (Python) live in `plugins/`; external plugins can be written in **any language** (Node.js, Go, Java, Python) and run as HTTP servers. Register with Core and the LLM routes to them. Examples: weather, news, email, browser automation.

**Skills** let you reuse OpenClaw-style workflows: folders under `config/skills/` with SKILL.md. You can reuse skillsets from OpenClaw—copy skill folders into HomeClaw's `config/skills/` and they work. No rewrite. The LLM uses tools and optional `run_skill` to accomplish tasks.

[Learn more about plugins and skills](plugins.md)

### 3. Channels — remote access

![Channels](assets/section-channels.png){ align=right width=280 }

Reach your assistant from anywhere. HomeClaw supports **channels**: WebChat, Telegram, Discord, WeChat, WhatsApp, email, CLI, and more. All talk to the same Core and memory. Use a tunnel (e.g. Cloudflare) or expose your Core so you can chat from your phone or another network. One agent, many ways to connect.

[Learn more about channels](channels.md)

### 4. Companion app

![Companion app](assets/section-companion.png){ align=right width=280 }

The **HomeClaw Companion** is a Flutter-based client for Mac, Windows, iPhone, and Android. Chat, voice, attachments, and **Manage Core**: edit core.yml and user.yml from the app. No SSH needed. Use it instead of or together with WebChat, CLI, Telegram, and other channels—all talk to the same Core and memory.

[Learn more about Companion app](companion-app.md)

### 5. Multi-agent

![Multi-agent](assets/section-multi-agent.png){ align=right width=280 }

One HomeClaw instance = one agent. To get more agents, run more instances—different ports, different configs if you like. No central orchestrator. Point the Companion app or any channel at the right port. Separate roles, isolation, or scale: just run more processes.

[Multi-instance: peers, pairing, peer_call](multi-instance-peers.md)

[Cross-instance Companion user messaging](federated-companion-messaging.md)

### 6. Memory

![Memory](assets/section-memory.png){ align=right width=280 }

HomeClaw keeps **RAG-style memory** (vector + relational) and **Markdown file–based memory** (e.g. AGENT_MEMORY.md, daily memory files) so the assistant remembers and recalls past context. All memory is scoped per user. Backend: Cognee (default) or Chroma.

### 7. Knowledge base

![Knowledge base](assets/section-knowledge-base.png){ align=right width=280 }

Per-user **knowledge base**: ingest documents, URLs, and manual content for RAG. Tools like `knowledge_base_add` and retrieval; optional auto-add when the user sends files. Same backends as memory (Cognee/Chroma).

### 8. Profile

![Profile](assets/section-profile.png){ align=right width=280 }

Per-user **profile**: learned facts (name, birthday, preferences, family) stored in a JSON file per user. The assistant can read and update profile via tools for personalization. Enable with `profile.enabled: true` in `config/core.yml`.

---

## Quick links

### [Deploy to cloud](deploy-cloud.md)
Run on Aliyun ECS, AWS EC2, or any VPS. Always on, same install.

### [Writing plugins & skills](writing-plugins-and-skills.md)
How to write plugins (any language) and skills. Examples and future marketplace.

### [Model selection & lifecycle](model-selection-and-lifecycle.md)
When HomeClaw uses main vs embedding vs vision vs spawn, mix mode, and (planned) on-demand specialists — with diagrams.

### [LLM catalog how-to](llm-catalog-howto.md)
How to list models in `llm.yml`, use `available`, capabilities, and `sessions_spawn`.

---

## Channels & Companion App

Talk to HomeClaw from WebChat, Telegram, Discord, the Companion app, and more. All use the same Core and memory. Remote access options: Tailscale, Cloudflare Tunnel, Pinggy, SSH tunnel.

[Channels & Companion — full guide](channels.md)

---

## Contact

Questions or feedback? Get in touch.

- **Email:** [shileipeng@gmail.com](mailto:shileipeng@gmail.com) | [shilei.peng@qq.com](mailto:shilei.peng@qq.com)
- **WeChat:** shileipeng
- **Website:** [https://www.homeclaw.cn](https://www.homeclaw.cn)
