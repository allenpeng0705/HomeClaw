<p align="center">
  <img src="HomeClaw_Banner.jpg" alt="HomeClaw Banner">
</p>

# HomeClaw

**HomeClaw** is an **AI assistant** that runs on your own hardware. Each installation is an autonomous agent: it talks to you over the channels you already use, keeps **memory** (RAG + agent memory), and extends its abilities through **skills** and **plugins**. Use **local models** to save cost and keep data at home, **cloud models** for scale, or **both** with a smart router. A **companion app** on every platform and **multi-agent** by running multiple instances let you build your own AI-powered social network—decentralized, private when you want it, and fully under your control.

---

## Major Features

### 1. Save cost — Local, cloud, and mix mode

- **Local models** — Run models on your machine with **llama.cpp** (GGUF) and **Ollama**. No per-token cloud cost; full control over data.
- **Cloud models** — Use **OpenAI**, **Google Gemini**, DeepSeek, Anthropic, and more via LiteLLM when you need scale or latest capabilities.
- **Mix mode with smart router** — Route each request to local or cloud automatically: simple/private tasks → local; heavy or search tasks → cloud. **3-layer router** (heuristic → semantic → classifier/perplexity) keeps cost down while keeping quality. Multimodal (images, audio, video) works with both.

### 2. User sandbox — Privacy, safety, and multi-user

- **Privacy and safety** — User sandbox: each user gets isolated context and permissions. Your data stays where you choose (local-only possible).
- **Multi-user** — Add users in `config/user.yml` (id, name, channel identities, optional login). Support multiple people or roles talking to the same HomeClaw instance.

### 3. Skills and plugins — OpenClaw-compatible, any language

- **Skills** — **Compatible with OpenClaw skills**: workflows in `skills/` (SKILL.md). LLM uses tools and optional `run_skill` to accomplish tasks.
- **Plugins** — **Built-in** (Python in `plugins/`) and **external in any language** (Node.js, Go, Java, Python, etc.). Register via HTTP; Core routes to them like built-ins. System plugins (e.g. **homeclaw-browser**) extend with browser automation, Canvas, and more.

### 4. Companion app — All platforms, multi-role (Friend of AI)

- **All platforms** — **Mac, Windows, Linux, Android, iOS**. One Flutter app: chat, voice, attachments, and **Manage Core** (edit core.yml and user.yml) from phone or desktop.
- **Multi-role** — Configure AI as a **Friend** or other roles; one agent, many ways to interact.

### 5. Multi-agent — Run multiple HomeClaw instances

- Run **multiple HomeClaw instances** (e.g. one per user, use case, or “persona”). Each instance is one agent with its own memory and config. Simple multi-agent without a central orchestrator.

### 6. Remote connection — Pinggy, Cloudflare, Ngrok, and all channels

- **Companion app remote access** — **Built-in Pinggy** support, **Cloudflare Tunnel**, **Ngrok**, Tailscale, and more. Use the app from anywhere.
- **Channels everywhere** — **WhatsApp**, **Google Chat**, **DingTalk**, **Feishu (Lark)**, **Slack**, **Microsoft Teams**, **Telegram**, **Discord**, **Signal**, **WeChat**, **Line**, **Email**, **WebChat**, and more. One Core serves all channels.

### 7. Your own social network

- Use HomeClaw as the brain behind **your own social network**: multi-user, multi-channel, multi-agent. One place for memory, skills, and plugins; your rules, your data.

---

## Quick Start

### Supported platforms

HomeClaw runs on **macOS**, **Windows**, and **Linux**. You need:

- **Python** 3.10–3.12 (recommended).
- For **local GGUF models**: copy **llama.cpp's binary distribution** into `llama.cpp-master/<platform>/` for your device type (mac/, win_cuda/, linux_cpu/, etc.); used for both main and embedding local models. See `llama.cpp-master/README.md`. Then start servers per config.
- For **cloud models**: only network access and the right API keys in the environment.

**Recommended: Install script + Portal**

| OS | Command |
|----|--------|
| **Mac / Linux** | `./install.sh` (run from project root, or from a parent directory — the script will clone into `./HomeClaw` and continue) |
| **Windows** | `.\install.ps1` (run from project root, or from a parent directory — the script will clone into `.\HomeClaw` and continue) |

The script checks or installs **Python 3.9+**, **Node.js**, clones the repo if needed, runs `pip install -r requirements.txt`, guides you on **llama.cpp** and **GGUF/Ollama**, then starts the **Portal** and opens http://127.0.0.1:18472 in your browser.

**Portal** — Use the web UI to create an admin account, manage settings (Core, users, LLM, channels), start Core and channels, and follow the built-in **Guide to install**. No need to edit YAML by hand unless you prefer it. From the same machine you can also open Core’s **/portal-ui** (when Core is running and `portal_url` is set in `config/core.yml`) or use the **Companion app** to reach the Portal via Core.

After install, run `python -m main doctor` to verify config and LLM connectivity. Full install details: **[InstallationGuide.md](InstallationGuide.md)**.

**Manual install** — Clone the repo, then `pip install -r requirements.txt`. Edit **Core**: `config/core.yml` (host, port, `main_llm`, `embedding_llm`, etc.); **Users**: `config/user.yml`; **Channels**: `channels/.env` (e.g. `CORE_URL`, bot tokens). For **models**: set cloud API keys and `main_llm`, or set up local (llama.cpp/Ollama) and `local_models`. See **[HOW_TO_USE.md](HOW_TO_USE.md)** and [InstallationGuide.md](InstallationGuide.md) for the full step-by-step.

**Run Portal** — Start the config and onboarding web UI:

```bash
python -m main portal
```

By default this opens http://127.0.0.1:18472 in your browser. Use the Portal to manage settings and **start Core** from the dashboard (or follow the in-app guide).

**Run Core** — Either start Core from the Portal dashboard, or in a terminal:

```bash
python -m main start
```

(This runs Core and the built-in CLI channel.) Or run Core only: `python -m core.core` (default port 9000).

**Run a channel** — With Core running, start each channel in its own terminal so people can talk to HomeClaw via that platform:

```bash
python -m channels.run <channel_name>
```

Examples: **WebChat** (browser UI at http://localhost:8014), **Slack**, **WhatsApp**, **Telegram**, **Discord**, **Signal**, **Google Chat**, **Teams**, **WeChat**, **Line**, **Feishu**, **DingTalk**, and more. For example:

```bash
python -m channels.run webchat    # → http://localhost:8014
python -m channels.run slack
python -m channels.run whatsapp
python -m channels.run telegram
python -m channels.run discord
```

Copy `channels/.env.example` to `channels/.env` and set `CORE_URL` (e.g. `http://127.0.0.1:9000`) and any bot tokens (e.g. `SLACK_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`). Each channel has a README in `channels/<name>/` with setup steps. Full list: [channels/README.md](channels/README.md).

### Use the Companion app to chat

Install the app from `clients/HomeClawApp/` or a release. Open the app → **Settings** → set **Core URL** to `http://127.0.0.1:9000` when on the same machine as Core, or to your [remote URL](#remote-access-tailscale-cloudflare-tunnel) (Tailscale, Cloudflare Tunnel, Ngrok, etc.) when away. Add your user in `config/user.yml` (or via Portal / **Manage Core** → Users) so Core accepts your messages. Then open **Chat** — the app sends messages to Core; you get the same AI and memory as WebChat and other channels.

---

**Other languages / 其他语言 / 他の言語 / 다른 언어:** [简体中文](README_zh.md) | [日本語](README_jp.md) | [한국어](README_kr.md)

**Documentation:** [https://allenpeng0705.github.io/HomeClaw/](https://allenpeng0705.github.io/HomeClaw/) — Full docs (install, run, mix mode, reports, tools, plugins) are built with MkDocs and published there. You can also browse the source in the **`docs/`** folder on GitHub.

---

## Table of Contents

- [Major Features](#major-features) — Save cost · User sandbox · Skills & plugins · Companion app · Multi-agent · Remote & channels · Your social network
- [Quick Start](#quick-start) — Install script & Portal · Run Core · Run a channel · Companion app
1. [What is HomeClaw?](#1-what-is-homeclaw)
2. [What Can HomeClaw Do?](#2-what-can-homeclaw-do) — Channels (WhatsApp, Slack, Telegram, etc.), multi-user
3. [Mix mode: Smart local/cloud routing](#3-mix-mode-smart-localcloud-routing) — 3-layer router
4. [How to Use HomeClaw](#4-how-to-use-homeclaw) — includes [Remote access (Pinggy, Cloudflare, Ngrok, Tailscale)](#remote-access-tailscale-cloudflare-tunnel)
5. [Companion app (Flutter)](#5-companion-app-flutter)
6. [System plugin: homeclaw-browser](#6-system-plugin-homeclaw-browser)
7. [Skills and Plugins](#7-skills-and-plugins-make-homeclaw-work-for-you)
8. [Plugins: Extend HomeClaw](#8-plugins-extend-homeclaw)
9. [Skills: Extend HomeClaw with Workflows](#9-skills-extend-homeclaw-with-workflows)
10. [Acknowledgments](#10-acknowledgments)
11. [Contributing & License](#11-contributing--license)
12. [Contact](#12-contact)

---

## 1. What is HomeClaw?

### Design idea

HomeClaw is built around a few principles:

- **Cloud and local models** — The core runs on your machine. You can use **cloud models** (LiteLLM: OpenAI, Gemini, DeepSeek, etc.) or **local models** (llama.cpp, GGUF), or both; they can work together for better capability and cost. Use local-only to keep data at home, or cloud for scale and features.
- **Channel-agnostic** — The same Core serves all channels. Whether you talk via WebChat, Telegram, email, or Discord, the AI is one agent with one memory and one set of tools and plugins.
- **Modular** — The LLM layer, memory, channels, plugins, and tools are separate. You can choose cloud or local models (or both), enable or disable skills and plugins, and add new channels without changing the core logic.
- **Extensible** — **Plugins** add focused features (weather, news, email, custom APIs). **Skills** add application-style workflows (e.g. “social media agent”) that the LLM follows using tools. Both are designed so you can tailor HomeClaw to your needs.

### Architecture

**Channels** and the **Companion app** connect to **Core**. Inside Core: **memory** (RAG + Markdown files), **tools** (base for skills), **skills & plugins** (registered in RAG, filtered per request), and the **LLM** (cloud or local). **Layer 1:** Channels + Companion app → Core. **Layer 2:** Memory (RAG + Markdown), Tools, Skills & Plugins (in RAG, filtered), Local/Cloud LLM. [Full design →](docs_design/ToolsSkillsPlugins.md) · [Doc site →](https://allenpeng0705.github.io/HomeClaw/)



---

## 2. What Can HomeClaw Do?

### Channels and multi-user

Talk to HomeClaw via **WebChat**, **CLI**, **Telegram**, **Discord**, **Signal**, **WhatsApp**, **Google Chat**, **DingTalk**, **Feishu (Lark)**, **Slack**, **Microsoft Teams**, **WeChat**, **Line**, **Email**, and more—all use the same Core. Add users in `config/user.yml` (id, name, email, im, phone; optional **username**/ **password** for Companion login; **friends** list with optional **identity** file per friend). [Channels →](https://allenpeng0705.github.io/HomeClaw/channels/) · [Multi-user →](docs_design/MultiUserSupport.md)

### Cloud and local models

Use **cloud** (LiteLLM: OpenAI, Gemini, DeepSeek, etc.) or **local** (llama.cpp, GGUF), or both. Set `main_llm` and `embedding_llm` in `config/core.yml`. [Models →](https://allenpeng0705.github.io/HomeClaw/models/) · [Remote access](#remote-access-tailscale-cloudflare-tunnel) (Tailscale, Cloudflare Tunnel) for the Companion app.

---

## 3. Mix mode: Smart local/cloud routing

**Mix mode** lets HomeClaw choose **per request** whether to use your **local** or **cloud** main model. A **3-layer router** runs before tools and plugins, using only the user message, so you get one model for the whole turn—local for simple or private tasks, cloud when you need search or heavy reasoning. You see **reports** (router decisions and cloud usage) via REST API or the built-in **usage_report** tool.

### Three layers

| Layer | Name | What it does |
|-------|------|----------------|
| **1** | **Heuristic** | Fast keyword and long-input rules (YAML). Example: “screenshot”, “锁屏” → local; “search the web”, “最新新闻” → cloud. First match wins. |
| **2** | **Semantic** | Embedding similarity: compare the user message to example **local** vs **cloud** utterances. Good for paraphrases and intent without listing every phrase. |
| **3** | **Classifier or Perplexity** | When L1 and L2 don’t decide: either a **small local model** answers “Local or Cloud?” (**classifier**), or the **main local model** is probed with a few tokens and **logprobs**—if it’s confident (high avg logprob), stay local; otherwise escalate to cloud (**perplexity**). |

**Powerful Layer 3 design:** With a strong local model, you can set Layer 3 to **perplexity** mode: the same model that might answer is asked to “vote” by confidence. Core sends a tiny probe (e.g. 5 tokens with `logprobs=true` to your llama.cpp server), computes the average log probability, and routes **local** if above a threshold (e.g. -0.6) or **cloud** if below. No extra classifier model needed; the main model’s own uncertainty drives the decision. For weak local models, use **classifier** mode (small 0.5B judge) instead.

**Enable:** Set `main_llm_mode: mix`, `main_llm_local`, `main_llm_cloud`, and `hybrid_router` in `config/core.yml`. Full guide (how to use, how to see reports, how to tune every parameter): **[Mix mode and reports](https://allenpeng0705.github.io/HomeClaw/mix-mode-and-reports/)**.

---

## 4. How to Use HomeClaw

For a **step-by-step guide** (install, config, local/cloud models, memory, tools, workspace, testing, plugins, skills), see **[HOW_TO_USE.md](HOW_TO_USE.md)** (also [中文](HOW_TO_USE_zh.md) | [日本語](HOW_TO_USE_jp.md) | [한국어](HOW_TO_USE_kr.md)). For getting started quickly, see [Quick Start](#quick-start) above.

### Remote access (Pinggy, Cloudflare Tunnel, Ngrok, Tailscale)

To use the **Companion app** or WebChat from another network (e.g. phone on cellular, laptop away from home), expose Core so the client can reach it. Options include **built-in Pinggy** support, **Cloudflare Tunnel**, **Ngrok**, and **Tailscale**.

**Pinggy (built-in)** — HomeClaw can use [Pinggy](https://pinggy.io/) for instant public tunnels; see the docs or Companion app settings for Pinggy options.

**Tailscale (recommended for home + mobile)**

1. Install [Tailscale](https://tailscale.com/download) on the machine that runs Core and on your phone/laptop; log in with the same account.
2. On the Core host, get the Tailscale IP: `tailscale ip` (e.g. `100.x.x.x`).
3. In the Companion app **Settings**, set **Core URL** to `http://100.x.x.x:9000` (replace with your IP). Optional: use **Tailscale Serve** for HTTPS: `tailscale serve https / http://127.0.0.1:9000` and set Core URL to the URL Tailscale shows (e.g. `https://your-machine.your-tailnet.ts.net`).
4. If Core has `auth_enabled: true`, set the same **API key** in the app.

**Cloudflare Tunnel (public URL)**

1. Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/local/) on the Core host.
2. Run: `cloudflared tunnel --url http://127.0.0.1:9000` and copy the URL (e.g. `https://xxx.trycloudflare.com`). If Slack or other channels get **502** (tunnel took port 9000), use port **9001** instead: in `config/core.yml` set `port: 9001`, in `channels/.env` set `core_port=9001`, and run `cloudflared tunnel --url http://127.0.0.1:9001` — Companion app keeps using the same tunnel URL; Slack and channels use 9001.
3. Enable Core auth: in `config/core.yml` set `auth_enabled: true` and `auth_api_key: "<long-random-key>"`.
4. In the Companion app **Settings**, set **Core URL** to the tunnel URL and the **API key** to match.

**Ngrok** — Run `ngrok http 9000` (or your Core port) and set **Core URL** in the app to the HTTPS URL Ngrok provides. Enable Core auth when using a public URL.

The app only needs **Core URL** and optional **API key**; no tunnel SDK in the app. For more (SSH tunnel, auth details, Pinggy), see the docs: **[Remote access](https://allenpeng0705.github.io/HomeClaw/remote-access/)** and **docs_design/RemoteAccess.md**.

### More: models, database, CLI, platforms

- **CLI** (`python -m main start`): `llm` / `llm set` / `llm cloud`, `channel list` / `channel run <name>`, `reset`. [HOW_TO_USE.md](HOW_TO_USE.md)
- **Local GGUF** and **cloud (OpenAI, Gemini, etc.)**: [Models doc](https://allenpeng0705.github.io/HomeClaw/models/) · config in `config/core.yml`.
- **Postgres, Neo4j, enterprise vector DB**: [MemoryAndDatabase.md](docs_design/MemoryAndDatabase.md)
- **Windows** (Visual C++ Build Tools, WeChat): [Install VSBuildTools](https://github.com/bycloudai/InstallVSBuildToolsWindows) · **China** (pip mirror): [getting-started](https://allenpeng0705.github.io/HomeClaw/getting-started/).

---

## 5. Companion app (Flutter)

**Companion** is a Flutter app for **Mac, Windows, Linux, Android, and iOS**: chat, voice, attachments, and **Manage Core** (edit core.yml and user.yml from the app). Supports **multi-role** (e.g. AI as **Friend**). [Companion app doc](https://allenpeng0705.github.io/HomeClaw/companion-app/) · [Build from source](clients/HomeClawApp/README.md)

To use it: set **Core URL** in Settings (same machine: `http://127.0.0.1:9000`; remote: see [Remote access](#remote-access-tailscale-cloudflare-tunnel)), ensure your user is in **config/user.yml** (or add via Portal / **Manage Core** → Users), then open **Chat** to talk to HomeClaw. The app talks to Core; same AI and memory as WebChat and other channels. You can also open **Manage Core** in the app to edit config or go to **/portal-ui** when Core is running with `portal_url` set.

---

## 6. System plugin: homeclaw-browser

**homeclaw-browser** (Node.js) in `system_plugins/homeclaw-browser`: WebChat UI at http://127.0.0.1:3020/, browser automation (LLM can open URLs, click, type), Canvas, and Nodes. Set `system_plugins_auto_start: true` in `config/core.yml` to start with Core, or run `node server.js` and `node register.js` manually. [system_plugins/README.md](system_plugins/README.md) · [homeclaw-browser README](system_plugins/homeclaw-browser/README.md) · [§8 Plugins](#8-plugins-extend-homeclaw)

---

## 7. Skills and Plugins: Make HomeClaw Work for You

**Tools** (file, memory, web search, cron, browser), **plugins** (Weather, News, Mail, etc.), and **skills** (workflows in SKILL.md) let the agent answer, remember, route to plugins, and run workflows. Just ask naturally; the LLM chooses tools, skills, or plugins. [ToolsSkillsPlugins.md](docs_design/ToolsSkillsPlugins.md)

---


---

## 8. Plugins: Extend HomeClaw

**Built-in plugins** (Python): `plugins/<Name>/` with plugin.yaml, config.yml, plugin.py; Core discovers them at startup. **External plugins** (any language): run an HTTP server (`GET /health`, `POST /run`), register with `POST /api/plugins/register`; Core routes to it like built-in. [PluginStandard.md](docs_design/PluginStandard.md) · [PluginsGuide.md](docs_design/PluginsGuide.md) · [external_plugins/](external_plugins/README.md)

---

## 9. Skills: Extend HomeClaw with Workflows

**Skills** are folders under `skills/` with **SKILL.md** (name, description, workflow). The LLM sees "Available skills" and uses tools (or **run_skill** for scripts) to accomplish them. Set `use_skills: true` in `config/core.yml`. [SkillsGuide.md](docs_design/SkillsGuide.md) · [ToolsSkillsPlugins.md](docs_design/ToolsSkillsPlugins.md)

---


---

## 10. Acknowledgments

HomeClaw would not exist without two projects that inspired it:

- **GPT4People** — The author’s earlier project that explored decentralized, people-centric AI and channel-based interaction. Many of HomeClaw’s ideas—local-first agents, channels, memory, and the vision of AI “for the people“—grew from that work.
- **OpenClaw** — A sibling ecosystem (gateway, extensions, channels, providers). OpenClaw and HomeClaw share a similar spirit: extensible, channel-based AI that users can run and customize. The contrast between OpenClaw’s gateway/extensions model and HomeClaw’s core/plugins model helped clarify HomeClaw’s design (see **docs_design/ToolsSkillsPlugins.md** §2.8).

Thank you to everyone who contributed to GPT4People and OpenClaw, and to the open-source communities behind llama.cpp, LiteLLM, Cognee, and the many channels and tools we build on.

---

## 11. Contributing & License

- **Contributing** — We welcome issues, pull requests, and discussions. See **CONTRIBUTING.md** for guidelines.
- **License** — This project is licensed under the **Apache License 2.0**. See the **LICENSE** file.

### Roadmap (summary)

**Done**

- **Mix mode** — 3-layer router (heuristic → semantic → classifier or perplexity) chooses local vs cloud per request. Reports (API + `usage_report` tool) for cost and tuning. See [Mix mode and reports](https://allenpeng0705.github.io/HomeClaw/mix-mode-and-reports/).

**Next**

**Later**

- Simpler setup and onboarding (`python -m main onboard`, `python -m main doctor`).
- More channels and platform integrations.
- Stronger plugin/skill discovery and multi-agent options.
- Optional: directory, trust/reputation, and blockchain-based verification for agent-to-agent use cases.

We’re at the beginning of a long journey. Stay tuned and join us as we grow.

---

## 12. Contact

Questions or feedback? Get in touch:

- **Email:** [shilei.peng@qq.com](mailto:shilei.peng@qq.com)
- **WeChat:** shileipeng
