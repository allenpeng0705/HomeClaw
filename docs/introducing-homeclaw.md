# Introducing HomeClaw

HomeClaw is an **AI assistant** that runs on your machine. One installation is one agent: the same **memory** (RAG + agent memory), tools, and plugins no matter how you connect. Use **cloud models** (OpenAI, Gemini, etc.) or **local models** (llama.cpp, GGUF), or **both together** for better capability and cost.

---

## Highlights

- **Companion app** — **Flutter-based** app for **Mac, Windows, iPhone, and Android** (`clients/HomeClawApp/`): chat, voice, attachments, and **Manage Core** (edit core.yml and user.yml from the app). Makes HomeClaw much easier to use from any device.
- **Memory** — **RAG** (vector + relational + optional graph) and **agent memory**: AGENT_MEMORY.md (long-term), daily memory (short-term). Cognee (default) or Chroma backend.
- **Plugins** — **Built-in** (Python in `plugins/`) and **external** (any language: **Node.js**, Go, Java, Python, etc.). The **system plugin** (e.g. homeclaw-browser) is one external plugin written in **Node.js**; you can write plugins in any language and register them with Core. There are many tools and ecosystems you can leverage.
- **Skills** — Full support for **OpenClaw-style skillset**: workflows in `skills/` (SKILL.md); LLM uses tools and optional `run_skill` to accomplish tasks.
- **Multi-agent** — Run **multiple HomeClaw instances** (different ports/configs); each is one agent. No special orchestration—just run more instances.
- **Cloud & multimodal** — **Gemini** and other cloud models work well. **Multimodal** (images, audio, video) is supported with both **local models** (e.g. Qwen2-VL with mmproj) and **cloud** (e.g. Gemini, GPT-4o). Tested with both; all work well.

---

## Core ideas

- **Cloud and local models** — Use **cloud models** (LiteLLM: OpenAI, Gemini, DeepSeek, etc.) or **local models** (llama.cpp, GGUF), or both; they can work together for better capability and cost. Use local-only to keep data at home, or cloud for scale and features.
- **Channels** — Reach your assistant from the **Companion app**, WebChat, Telegram, Discord, WeChat, WhatsApp, email, CLI, and more.
- **Memory** — RAG-based, per-user; agent memory (AGENT_MEMORY.md, daily memory) for long- and short-term context.
- **Plugins & skills** — Extend with built-in and external plugins (any language) and OpenClaw-style skills.

For the full intro and design details, see [IntroducingHomeClaw.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/IntroducingHomeClaw.md) in the repo.
