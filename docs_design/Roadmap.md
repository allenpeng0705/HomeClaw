# Roadmap

A simple overview of planned directions. See **README.md** § Roadmap for the short list.

---

## Next big feature: External plugins with UIs (v1.x)

**Goal:** Allow external plugins (e.g. Node.js) to implement **Dashboard, WebChat, Control UI, TUI**—so HomeClaw can have rich UIs without baking them into Core.

**Investigation and design:** [OpenClawInvestigationAndPluginUI.md](OpenClawInvestigationAndPluginUI.md). **Detailed plan (phases, Core WS API, Node.js plugin):** [PluginUIImplementationPlan.md](PluginUIImplementationPlan.md).

- **Plugin UI contract:** Extend registration with optional `ui` (dashboard, webchat, control, tui, custom URLs/commands). Core (or a UI host) discovers and proxies/links to plugin UIs.
- **Sessions and memory:** Session lifecycle, secure multi-user DMs, session API for UIs.
- **Bootstrapping:** Optional first-run wizard to seed workspace and identity.

**Status:** Design documented. **Plugin UI contract and launcher** implemented in Core; **HomeClaw Browser** system plugin (WebChat, Control UI, browser, canvas, nodes) in **system_plugins/homeclaw-browser**. See [PluginUIsAndHomeClawControlUI.md](PluginUIsAndHomeClawControlUI.md) for overview and [system_plugins/README.md](../system_plugins/README.md) for usage.

**Browser, canvas, nodes:** Implemented in **system_plugins/homeclaw-browser** (browser automation + canvas + nodes + Control UI/WebChat). See [BrowserCanvasNodesPluginDesign.md](BrowserCanvasNodesPluginDesign.md) and [system_plugins/homeclaw-browser/README.md](../system_plugins/homeclaw-browser/README.md).

---

## Later: Local + cloud model mix (routing and cost)

**Goal:** Use local and cloud models together so that work is done **efficiently** and **cost stays low**.

**Ideas (to be designed):**

- **Routing by task** — Use local model for high-volume or simple tasks (e.g. intent classification, short replies, embedding). Use cloud model for complex reasoning, long answers, or when local is not good enough.
- **Fallback** — Prefer local; call cloud when local fails or when the request explicitly needs a stronger model.
- **Cost control** — Limit cloud usage by budget or by routing rules (e.g. only use cloud for “hard” queries or when the user asks for it).
- **Config** — Allow rules or policies (e.g. “embedding always local”, “chat: local first, cloud if confidence low”) without hardcoding.

**Status:** Design phase. No implementation yet.

---

## Later

- Simpler setup and onboarding.
- More channels and platform integrations.
- Stronger plugin/skill discovery and multi-agent options.
- Optional: directory, trust/reputation, blockchain-based verification for agent-to-agent use cases.
