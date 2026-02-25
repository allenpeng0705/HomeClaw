# Why and How I Built HomeClaw: A Story

*From GPT4People to HomeClaw—local LLM, channels, memory, plugins, and learning from OpenClaw.*

---

I’d like to tell you the story of **HomeClaw**: why I started it, how it evolved, and where it’s going. It began as **GPT4People** more than half a year ago. Today it’s a self-hosted AI assistant that runs at home, talks to you over the channels you already use, and keeps your data on your side. Here’s how it happened.

---

## Why I Started: Security and Simplicity

I wanted two things from the start.

**First: security using a local LLM.** I didn’t want every conversation to go to someone else’s cloud. I wanted the model to run on my own machine so that what I say stays with me. So the core idea was: **local LLM first**.

**Second: simple ways to reach that LLM from anywhere.** A model running at home isn’t useful if you have to sit at that computer. I wanted **channels**—ways to talk to your home computer from your phone, from work, from anywhere—and to use the local LLM through those channels without a lot of setup. So: **channels to reach your home computer and use the local LLM simply**.

That combination—local LLM + channels—became the heart of the project. I called it **GPT4People**.

---

## The Beginning: Chatting and a Simple Memory

At first I focused on **chatting**. Get a message from a channel, send it to the local LLM, get a reply, send it back. To make conversations useful across sessions, I added a **simple RAG-based memory**: embed past turns, store them, and retrieve relevant bits when answering. So the assistant could say things like “last time you mentioned…” without me re-explaining everything.

I also hooked up **major IMs** so people could talk to the assistant the way they already talk to friends: **WeChat**, **WhatsApp**, and the like. The idea was: you message your “home assistant” the same way you message anyone else. No new app, no new habit—just another contact that happens to be your local AI.

So early on we had: local LLM, channels (WeChat, WhatsApp, etc.), and a small RAG-based memory. That was already useful for daily chat and light recall.

---

## Reality Check: The Home Computer Isn’t Always Enough

After a while I ran into a practical issue: **the home computer often has weak computing power**. No GPU, or an old one. Running a big model locally was slow or impossible. Some users only had a laptop; others had a NAS or a small server. Pushing everyone to “local only” would have limited who could use it.

So I asked: what if we **also** support **cloud models**? Use local when you can, and when the machine is too weak or the task is too heavy, use a cloud API (OpenAI, Gemini, DeepSeek, etc.). I added **cloud model support** via **LiteLLM** so you can point the same assistant at a local model or a cloud model—or both, with different roles (e.g. chat on local, embedding on cloud). That kept the “local when possible” idea but made the system usable on more hardware.

---

## Doing Real Things: Plugins (and the Cost of Extending)

Chatting and memory were good, but I wanted the assistant to **do real things**: “book a hotel for me,” “remind me tomorrow at 9,” “what’s the weather?” So I designed a **simple plugin framework**: one plugin = one capability. Plugins could be **hot-loaded** and **extended** without restarting the whole system. The LLM would decide when a user request matched a plugin and route to it; the plugin would run (call an API, send an email, etc.) and return the result.

The framework worked. The catch: **each new capability meant writing a new plugin**. Weather, email, booking—each one needed to be designed and developed. So extensibility was there, but the cost of adding features was still on the developer. I kept that in mind for later: we’d need both a clear plugin model and ways to reuse what others had already built.

---

## From the Start: Multi-User and Multiple Models

Two design choices were there from the beginning and stayed.

**Multi-users and permission control.** I wanted several people (e.g. family) to use the same HomeClaw instance without seeing each other’s data. So I added **multi-user support** and **permission control** from day one, driven by a **simple configuration file** (today it’s `config/user.yml`). Each user has an identity (email, IM id, etc.); chat history and memory are scoped per user. No fancy auth server—just a clear, file-based allowlist and strict isolation in storage.

**Multiple models.** I also designed the system so it could **load and use multiple models** if needed: one for chat, one for embedding, and later perhaps different models for different tasks. That way we could mix local and cloud, or small and large models, without rewriting the core. That design is what made “add cloud later” and “one agent, many LLMs” possible.

---

## OpenClaw Got Hot: Learning and Keeping What Worked

Recently **OpenClaw** got a lot of attention. When I looked at it, I saw that **many ideas were similar** to what I’d been building: channels to reach your assistant, the home computer as the place where the AI runs, and the LLM doing things for you (tools, skills). That was encouraging—it meant the direction made sense to others too.

I decided to **learn from OpenClaw** without throwing away what already worked in GPT4People. OpenClaw had a rich **skills** ecosystem (SKILL.md, workflows, ClawHub). So I made HomeClaw **support the same skillset format**: you can take skills from OpenClaw, put them under `skills/`, and the assistant can use them. We kept our own strengths: **local-first**, **RAG memory**, **multi-user sandbox**, and the **plugin model** we’d already built. The result wasn’t “clone OpenClaw,” but “take the best of both.”

---

## Where HomeClaw Is Today

After a lot of upgrades and a rename to **HomeClaw**, the system today looks like this:

- **Distributed deployment:** You can run the Core on one machine and channels on another, or run multiple HomeClaw instances on one or many computers. One agent per instance, but you scale by adding instances.

- **Local and cloud LLM:** You can use only local models (llama.cpp, GGUF), only cloud (LiteLLM → OpenAI, Gemini, DeepSeek, etc.), or both. Main model and embedding model are configurable; you can switch at runtime.

- **Built-in and external plugins:** **Built-in plugins** (Python) live in the `plugins/` folder—Weather, News, Mail, and your own. **External plugins** can be written in **any language** (Node.js, Go, Java, Rust, etc.) and run as a separate HTTP service; you register with the Core and implement a simple request/response contract. So you extend either by dropping in a Python plugin or by connecting an existing service.

- **OpenClaw skills:** You can reuse **skills from OpenClaw** (SKILL.md under `skills/`). The assistant sees “available skills” and uses tools to follow those workflows. No need to port everything—if it’s expressible as “use these tools in this way,” it can run on HomeClaw.

- **Multi-user, RAG memory, permission:** Still there. Each user has isolated chat and memory; permission is a simple config file; RAG gives long-term, semantic recall across sessions.

So: **one agent**, but it can be **deployed in a distributed way**, use **local and cloud LLMs**, be extended with **built-in and external plugins**, and use **OpenClaw-style skills**. It’s a good time to introduce it and to invite others to try it and build on it.

---

## How You Can Use It Today

You can **run HomeClaw** on your own machine (or a server), **talk to it** via WebChat, CLI, Telegram, Discord, Slack, email, Matrix, WeChat, WhatsApp, or any bot that can POST to its `/inbound` API. You **configure** users in `config/user.yml`, **choose** local and/or cloud models in `config/core.yml`, and **add** plugins and skills as you need. The assistant **remembers** (RAG + chat history), **reasons** (with the LLM you chose), and **does things** (via tools and plugins). All of that can stay on your hardware if you want, or mix in cloud when you need more power.

It’s **self-hosted**, **multi-user**, and **extensible**. The docs (README, Design.md, Channel.md, HOW_TO_USE.md, and the guides in `docs/`) walk you through setup and extension.

---

## What’s Next: Easier to Use, Smarter Use of Local and Cloud

HomeClaw is usable today, but there’s still a lot to improve. Two directions matter most to me right now.

**First: make it much easier to configure and run.** Right now you edit YAML and run a few commands. I want **better tools and UIs**—wizards, clearer defaults, and a solid WebChat—so that more people can get HomeClaw running without reading the whole manual. The goal is “get your home assistant up in minutes,” not “read the design doc first.”

**Second: use local and cloud LLMs together without wasting money.** The dream is: **most things done by the local model**, and **cloud only when we really need it** (harder questions, longer context, or when the user explicitly asks). That means smarter routing, fallbacks, and maybe simple policies (e.g. “embedding always local,” “chat: local first, cloud if confidence is low”). I want to explore how to mix local and cloud so that we **save cost as much as possible** while still giving a good experience.

So the story doesn’t end here. HomeClaw will keep evolving—easier to use, and smarter about when to use local vs cloud. If you’re interested in a local-first, channel-based, multi-user home assistant, I hope you’ll try it, star it, or contribute. Your home, your AI, your control.

---

*Thank you for reading. HomeClaw is open source (Apache 2.0). Repo: [https://github.com/allenpeng0705/HomeClaw](https://github.com/allenpeng0705/HomeClaw).*
