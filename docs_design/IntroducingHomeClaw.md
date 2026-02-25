# Welcome to the HomeClaw Wiki

This document is dedicated to **introducing HomeClaw**: where it came from, what it stands for, and what it does. It’s the place to get the big picture before diving into the README, Design.md, or how-to guides.

---

## 1. Origin

HomeClaw comes from a project called **GPT4People**, which we designed and implemented more than half a year ago. After many changes and improvements, we renamed it to **HomeClaw**. The core idea stayed the same: an AI assistant that runs at home, talks to you over the channels you already use, and keeps your data and privacy on your side.

---

## 2. What We’re About (and What We’re Not)

Some design ideas are similar to **OpenClaw**: **channels** (how you reach the assistant), **accessing your home computer** from anywhere, and **letting the LLM do things for you**. But we didn’t set out to “control” the computer. We want the **home computer to do things for us**—and to **protect our privacy** at the same time. So: your machine, your data, your assistant.

---

## 3. Local LLM First, Then Cloud

At the beginning we focused on **local LLM** running on your own hardware (e.g. llama.cpp, GGUF). Later we added support for **cloud model** services via **LiteLLM** (OpenAI, Google Gemini, DeepSeek, Anthropic, etc.). So you can run entirely on local models, entirely on cloud, or **mix both**—for example local for chat and cloud for embedding, or the other way around. It’s configurable.

---

## 4. Memory: A Sandbox for Each User

We added a **memory system** that acts as a **sandbox per user**. If several family members use the same HomeClaw instance, each person’s data is isolated: your conversations and memories don’t leak to another user. That’s enforced in software. Of course, if someone has physical access to your computer and looks at the files, we can’t control that—but within the system, users are separated and safe.

Memory is **RAG-based** (retrieval-augmented): the assistant can recall “what we said about X” across sessions using a vector store plus chat history. So it’s not only “this session”; it’s **long-term, semantic memory** per user.

---

## 5. In One Sentence

HomeClaw is a **local- and cloud-LLM supported, multi-user, memory-based, self-hosted** system. You run it on your machine (or several machines); you talk to it over email, Telegram, Discord, WebChat, CLI, or any bot that can POST to it; and it remembers, reasons, and uses tools and plugins—all with your privacy in mind.

---

## 6. Learning from OpenClaw and Extending HomeClaw

We learned from **OpenClaw** and made it easy to **reuse Skills** from OpenClaw directly. HomeClaw skills live under `skills/` with a **SKILL.md** (name, description, workflow). If a skill can be described as “use these tools in this way,” you can often drop it in without code changes.

We also support **extending** HomeClaw in two ways:

- **Built-in plugins** (Python): live in the `plugins/` folder; one plugin = one focused feature (e.g. Weather, News, Mail). The LLM routes to them via `route_to_plugin`.
- **External plugins** (any language): run as a separate HTTP service (Node.js, Go, Java, etc.); you register with the Core and implement a simple request/response contract. See docs_design/PluginsGuide.md and docs_design/PluginStandard.md.

So you get **one agent**, but you can extend it simply with skills and plugins—and you can **run more HomeClaw instances** on the same computer or on multiple computers if you need more capacity or isolation.

---

## 7. Plugins: Extending the Power of HomeClaw

**Plugins** are how you add focused capabilities to HomeClaw—weather, news, email, custom APIs, or anything else you want the assistant to do. They are important for extending the power of HomeClaw without changing the core.

- **What a plugin is:** One plugin = **one focused feature**. When the user asks something that clearly matches a plugin (e.g. “What’s the weather in Paris?”), the LLM routes to that plugin; the plugin runs, fetches data or calls an API, and returns the answer. So the assistant can do much more than chat: it can get weather, send email, fetch news, or call your own services.

- **Built-in plugins (Python):** Live in the `plugins/` folder. Each has a **plugin.yaml** (id, description), **config.yml** (API keys, defaults), and **plugin.py** (a class that extends `BasePlugin` and implements `run()`). Core discovers them at startup; no registration step. Examples: **Weather**, **News**, **Mail**. You can add your own by dropping a new folder under `plugins/` and following the same structure.

- **External plugins (any language):** Run as a **separate HTTP server** (Node.js, Go, Java, Rust, etc.). You implement a simple contract: accept a request (user input, context) and return a result. You **register** with Core via `POST /api/plugins/register`; after that, Core routes to your server like built-in plugins. So you can extend HomeClaw in the language you prefer, or plug in an existing service.

Plugins work alongside **tools** (exec, browser, cron, file, memory, web search, etc.) and **skills** (workflows described in SKILL.md). Together they give you one agent that can chat, remember, and do things—and you extend that power by adding plugins. For details, see **docs_design/PluginsGuide.md**, **docs_design/HowToWriteAPlugin.md**, and **docs_design/PluginStandard.md**.

---

## 8. One Agent, Multiple LLMs

We are **one agent** (one identity, one memory, one set of tools and skills), but we support **multiple LLMs** that you can configure. You can set a main model and an embedding model (each can be local or cloud), and in the future we’ll support using different models for different tasks (e.g. simple tasks on local, hard ones on cloud). So: one assistant, many models—all configurable.

---

## 9. Memory: Simple or Enterprise

For **memory** we offer a simple default and an enterprise-style option:

- **Simple:** **SQLite** (chat history, sessions) + **Chroma** (vector store for RAG) + **Kuzu** (optional graph). No extra services; good for home and small setups.
- **Enterprise:** You can switch to **PostgreSQL** (relational), **Qdrant** or **LanceDB** (vector), and **Neo4j** (graph). We also support **Cognee** as the default memory engine, which unifies relational, vector, and graph and can use the same backends. See docs_design/MemoryAndDatabase.md.

So you can start simple and scale up when you need to.

---

## 10. What You Can Do Today

- **Talk** to HomeClaw via **WebChat**, **CLI**, **Telegram**, **Discord**, **Slack**, **email**, **Matrix**, **Tinode**, **WeChat**, **WhatsApp**, or any bot that POSTs to **/inbound** (or to our Webhook relay).
- **Remember:** RAG + chat history + optional per-user profile and knowledge base.
- **Do things:** **Tools** (exec, browser, cron, file, memory, web search, sessions, etc.) and **plugins** (Weather, News, Mail, custom APIs). The LLM calls tools by name with arguments and routes to plugins when the intent matches.
- **Use skills:** Drop in SKILL.md-based workflows (including ones from OpenClaw) so the assistant knows how to combine tools for a task.
- **Multi-user:** Add users in `config/user.yml`; each user has isolated chat, memory, and profile.

---

## 11. Next Steps (Our Direction)

1. **Easier to use**  
   We want to make HomeClaw much easier to use by providing **tools and UIs**—e.g. better onboarding, setup wizards, and a solid WebChat so you can get started without reading the whole manual.

2. **Mix local and cloud models**  
   We want to investigate **how to mix local and cloud models** so that **most things are done by the local model**, and we **use the cloud model only when needed** (e.g. harder questions, longer context, or when the user asks for it). That keeps cost and privacy under control while still giving you the option to lean on the cloud.

---

## 12. Where to Go Next

- **README.md** — Overview, quick start, channels, plugins, skills.  
- **Design.md** — Architecture, Core, channels, memory, tools, plugins.  
- **Channel.md** — How to use and configure channels.  
- **HOW_TO_USE.md** — Step-by-step setup and usage.  
- **docs_design/** — PluginsGuide, SkillsGuide, MemoryAndDatabase, ToolsSkillsPlugins, etc.

Thank you for your interest in HomeClaw. We hope it helps you bring AI home—your way.
