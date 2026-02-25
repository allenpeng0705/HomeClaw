# HomeClaw vs OpenClaw: Two Paths to a Home AI Assistant

*A technical look at two sibling projects—local-first with RAG vs gateway-first with rich tools—and when to choose which.*

---

## Why this comparison?

If you want an AI assistant that runs at home and talks to you over Telegram, email, or WebChat, you’re not alone. Two open-source projects from the same ecosystem take different technical paths: **HomeClaw** (this repo) and **OpenClaw** (gateway, extensions, channels, providers). Both share a vision—*your home, your AI, your control*—but they differ in stack, architecture, and strengths. This article is for developers and technical readers who want to understand both and pick the right one.

---

## What is HomeClaw?

**HomeClaw** is a **local-first AI assistant** that runs on your own hardware. One installation is one agent: the same memory, tools, and plugins no matter whether you talk via WebChat, Telegram, Discord, email, or the CLI.

### Technical snapshot

- **Stack:** Python, FastAPI, SQLite, Cognee (default) or Chroma for RAG, llama.cpp, LiteLLM.
- **LLM:** **Local-first**—llama.cpp (GGUF) by default; cloud (OpenAI, Gemini, DeepSeek, etc.) via LiteLLM is optional. You can use local for chat and cloud for embedding (or the other way around).
- **Architecture:** A **Core** (FastAPI, port 9000) plus **separate channel processes** (or any bot that POSTs to `/inbound`). Channels are not inside the Core; they connect to it over HTTP or WebSocket.
- **Memory:** **RAG** is central. Vector store (Cognee or Chroma) + SQLite chat history + optional per-user profile and knowledge base. The model gets “relevant memories” via semantic search on every request—so it can recall “what we said about X” across sessions.
- **Extensibility:** **Tools** (exec, browser, cron, file, memory, web search, sessions, etc.) are first-class; the model calls them by name with arguments. **Plugins** (Weather, News, Mail, custom APIs) are single-feature modules selected via `route_to_plugin`. **Skills** (SKILL.md under `skills/`) describe workflows; the LLM uses tools to accomplish them or calls `run_skill` to run a script.

### Architecture at a glance

```
Channels (Email, Matrix, Telegram, WebChat, CLI, or any bot → POST /inbound)
    │
    ▼
Core (FastAPI) → Permission → RAG + LLM → Reply (or route to Plugin)
    │
    ├── LLM: llama.cpp (local) or LiteLLM (cloud)
    └── Memory: Cognee/Chroma + SQLite + transcript; optional profile, knowledge base
```

![HomeClaw simple architecture](HomeClaw_Article_Architecture.png)  
*Image: place `HomeClaw_Article_Architecture.png` in this folder, or export the "Simple overview" Mermaid from the main README to PNG.*

*Simple flow: Channels send messages to Core; Core uses permission, RAG, and the LLM to reply or route to a plugin.*

---

## What is OpenClaw?

**OpenClaw** is the sibling ecosystem built around a **Gateway**: one process, one port, with channels, providers, and skills as **extensions** loaded into (or connected to) that Gateway. It’s designed for a **cloud-first** or hybrid LLM setup and rich tooling (exec, browser, canvas, nodes, cron, webhooks, sessions).

### Technical snapshot

- **Stack:** Node/TypeScript, single Gateway (WebSocket + HTTP), pi-mono–derived agent.
- **LLM:** **Cloud-first** (e.g. Anthropic, OpenAI) with optional local (e.g. Ollama).
- **Architecture:** **Single Gateway process**; channel code runs inside the Gateway or as extensions. One entry point for all channels.
- **Memory:** Session **transcript** (e.g. JSONL) plus **workspace bootstrap** (AGENTS.md, SOUL.md, TOOLS.md). No vector RAG in core; context is “this session” plus identity and capabilities.
- **Extensibility:** **Extensions** can provide channels (WhatsApp, Telegram, Slack, etc.), providers (e.g. TTS), or skills. Skills are AgentSkills-compatible (SKILL.md); the agent uses **tools** (exec, browser, canvas, nodes, cron, sessions_*, etc.) by function-calling. ClawHub offers a skill registry.

---

## Side-by-side comparison

| Aspect | HomeClaw | OpenClaw |
|--------|----------|----------|
| **Primary LLM** | Local (llama.cpp) + optional cloud (LiteLLM) | Cloud (Anthropic/OpenAI) + optional local (e.g. Ollama) |
| **Control plane** | Core (FastAPI) + **separate** channel processes or bots calling `/inbound` | **Single** Gateway process; channels inside or as extensions |
| **Memory** | **RAG** (Cognee/Chroma) + chat (SQLite) + transcript (JSONL, prune, summarize) + optional profile/KB | Session transcript + workspace bootstrap (AGENTS, SOUL, TOOLS); no vector RAG in core |
| **Adding a new bot** | POST to Core `/inbound` or Webhook `/message` with `{ user_id, text }`; no new repo code | Implement or enable a channel in the Gateway; bot token in config |
| **Tools** | exec, browser, cron, file_*, memory_*, web_search, sessions_*, run_skill, route_to_plugin, etc. | exec, browser, canvas, nodes (camera, screen, location), cron, webhooks, sessions_* |
| **Plugins / extensions** | **Plugins** = feature modules (Weather, News, Mail); LLM selects via `route_to_plugin` | **Extensions** = channel/provider/skill packages; `register(api)` in Gateway |
| **Config** | YAML: core.yml, user.yml, channels/.env | JSON config; env vars; credentials in config directory |
| **Remote access** | Tailscale/SSH; optional auth (auth_enabled, auth_api_key) on Core | Tailscale Serve/Funnel, SSH; gateway auth |

---

## Major differences in practice

### 1. Local-first vs cloud-first

- **HomeClaw:** Default is **local** (llama.cpp, GGUF). Data and inference can stay on your machine; cloud is optional for when you need a stronger model or embedding.
- **OpenClaw:** Default is **cloud** for best model quality and long context; local is an option.

*Choose HomeClaw* if privacy, offline use, or “no API bill by default” matters. *Choose OpenClaw* if you want the best available models and long context out of the box.

### 2. RAG vs transcript-only memory

- **HomeClaw:** **RAG** is built in. Past conversations are embedded and retrieved by semantic similarity. The model can answer “remember when we talked about X?” across sessions. Plus session transcript (export, prune, summarize).
- **OpenClaw:** Context is **this session’s transcript** plus workspace files (who the agent is, what it can do). No vector store in core; no cross-session semantic recall.

*Choose HomeClaw* if you want long-term, semantic memory. *Choose OpenClaw* if you care mainly about “this conversation” and identity/capabilities in the prompt.

### 3. Core + channels vs single Gateway

- **HomeClaw:** **Core** is one process; **channels** are separate processes (Email, Matrix, WeChat, etc.) or any bot that POSTs to `/inbound`. You run Core and then one or more channel processes (or point external bots at Core or a Webhook).
- **OpenClaw:** **One Gateway** process; channels run inside it or as extensions. Single deployment unit.

*Choose HomeClaw* if you like a clear split (brain vs adapters) or want to scale/place channels independently. *Choose OpenClaw* if you prefer one process and one port to manage.

### 4. Adding a new bot

- **HomeClaw:** **Minimal API.** Any bot can send `POST /inbound` with `{ user_id, text }` (or use the Webhook relay). Add `user_id` to `config/user.yml`; no new code in the repo. Ready-made channel scripts (e.g. Telegram, Discord) live in `channels/`.
- **OpenClaw:** New channel is implemented in the codebase or as an extension; bot token is configured in the Gateway.

*Choose HomeClaw* if you want to wire a new bot with one HTTP contract and a config change. *Choose OpenClaw* if you’re fine with (or prefer) implementing channels inside the Gateway.

### 5. Plugins vs extensions

- **HomeClaw:** **Plugins** are feature modules (one plugin = one capability). The LLM sees plugin descriptions and calls `route_to_plugin(plugin_id)`. Plugins run in-process (Python) or as external HTTP services. **Tools** are separate: exec, browser, cron, file, memory, etc., with function-calling.
- **OpenClaw:** **Extensions** register with the Gateway and can provide channels, providers, or skills. One extension can bundle multiple of these. Skills (SKILL.md) teach the agent how to use tools.

Same idea—extensibility—different packaging: HomeClaw separates “feature plugins” from “generic tools”; OpenClaw bundles channels and skills in extensions.

---

## When to choose which?

- **Choose HomeClaw** if you want:
  - **Local LLM by default** (llama.cpp, GGUF) and optional cloud.
  - **RAG and long-term memory** (“remember what we discussed about X”).
  - A **minimal API** for bots (POST `/inbound` or Webhook) and a **Python/FastAPI** stack.
  - **Explicit separation** between Core and channels (multiple processes or external bots).

- **Choose OpenClaw** if you want:
  - **Cloud-first** models and long context.
  - A **single Gateway** with channels and skills as extensions.
  - **Device nodes** (camera, screen, location) and **canvas**-style tools.
  - **ClawHub** and a unified extension model (channels/providers/skills in one manifest).

Both are valid “home agent, accessible from anywhere” designs. The choice is mainly **local + RAG + minimal API** (HomeClaw) vs **cloud + single Gateway + rich extensions** (OpenClaw).

---

## Summary

| | HomeClaw | OpenClaw |
|---|----------|----------|
| **Tagline** | Local-first AI assistant; RAG + multi-channel. | Personal AI assistant; Gateway + extensions + tools and skills. |
| **Strength** | Local LLM, RAG memory, minimal bot API, Core/channel split. | Cloud models, single process, device nodes, ClawHub skills. |

You can run **HomeClaw** entirely on your own hardware with local models and still add Telegram, Discord, or WebChat via `/inbound` or the Webhook. You can run **OpenClaw** for a single Gateway and a rich tool/skill ecosystem. Both are open source and share the same spirit: *your home, your AI, your control.*

---

## Links and repo

- **HomeClaw:** [https://github.com/allenpeng0705/HomeClaw](https://github.com/allenpeng0705/HomeClaw)  
- **Docs:** README, Design.md, Channel.md, docs_design/Comparison.md, docs_design/ToolsSkillsPlugins.md  

*If you found this useful, star the repo or share it with others who care about local-first and home AI.*

---

## Images for this article

Use these when posting to LinkedIn, Medium, or Facebook:

| Image | File | Use |
|-------|------|-----|
| **Architecture (simple)** | `HomeClaw_Article_Architecture.png` | “Architecture at a glance” section. Generate with: *Channels → Core → LLM (left to right), Memory ↔ Core; blue / orange / green / pink boxes.* Or export the “Simple overview” Mermaid from the main README to PNG. |
| **Promo banner (optional)** | `HomeClaw_Promo_EN.jpg` (project root or social) | Header or footer: “Your home. Your AI. Your control.” |

**To add the architecture image:** Create or export a simple diagram (Channels → Core → LLM, Memory ↔ Core) and save it as `social/HomeClaw_Article_Architecture.png`. Mermaid Live Editor or the README’s “Simple overview” block can be exported to PNG.
