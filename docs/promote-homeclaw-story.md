# HomeClaw: A Python-Native AI Assistant That Grows With You

*One story for websites: Python tech stack, mix mode for cost, plugins, external plugins, multi-agent, and the companion app.*

---

You want an AI assistant that runs where you want it—on your machine, with your data—and that you can extend without leaving the ecosystem you already use. In the AI world, that ecosystem is often **Python**: models, RAG, tooling, and most of the community live there. HomeClaw was built for that.

**The core is Python.** The server is **FastAPI** and **uvicorn**; the runtime is the same stack you use for local LLMs, embeddings, and vector stores. Built-in plugins are **Python** in `plugins/<Name>/`—one folder, a small `plugin.py`, and the LLM can route to them. No Node.js required to run or extend the heart of the system. If you’re a Python developer, you’re already at home.

That doesn’t mean you’re locked in. **External plugins** can be written in **any language**—Node.js, Go, Java, or Python—and run as HTTP services. You implement `GET /health` and `POST /run`, register with Core, and the same LLM routing that calls built-in Python plugins can call your service. Reuse existing Node or Go microservices, or add a Python plugin in five minutes. HomeClaw gives you a **Python-native core** with a **polyglot plugin layer**.

**Cost is a first-class concern.** Cloud APIs are powerful but expensive; local models are free but sometimes not enough. HomeClaw’s **mix mode** fixes that: for every user message, a small router decides once—local or cloud—for the whole turn. Simple or private tasks go to your local model; complex or uncertain ones go to the cloud. You get one model per turn, automatic routing, and **usage reports** (in chat or via API) so you can see how much went to the cloud and tune rules. Default to local when in doubt and you keep cost under control without giving up cloud when you need it.

**Plugins** are how you add capabilities. **Built-in plugins** (Python) live next to Core: Weather, News, Mail, or your own `plugin.py`. **External plugins** (any language) run as separate HTTP servers and register with Core; the system plugin for browser automation is one example (Node.js). One plugin, one capability—you extend the assistant without forking the project.

**Multi-agent is native.** There’s no central orchestrator. One HomeClaw instance is one agent: one memory, one set of tools and plugins. To get more agents, you run more instances—different ports, different configs if you like. Point the Companion app, WebChat, or any channel at the right port. That’s it. Separate roles, isolation, or scale: just run more processes.

And **how do you talk to it?** The **HomeClaw Companion** is a single **Flutter** app for **Mac, Windows, iPhone, and Android**. Chat, voice, attachments, and—importantly—**Manage Core**: edit **core.yml** and **user.yml** from the app. No SSH, no hunting for config files. Same app on your phone and laptop, same Core and memory whether you use the app, WebChat, Telegram, or the CLI.

So: a **Python-based core** (FastAPI, uvicorn, Python plugins) that fits the AI world’s dominant stack; **mix mode** so you save cost without losing cloud when you need it; **plugins** (Python built-ins + **external plugins in any language**); **multi-agent by design** (more instances, no orchestrator); and **one companion app** for all devices and config. That’s the story. Try it—your home, your AI, your stack.

---

**Quick links:** [Companion app](companion-app.md) · [Plugins](plugins.md) · [Mix mode and reports](mix-mode-and-reports.md) · [Introducing HomeClaw](introducing-homeclaw.md)
