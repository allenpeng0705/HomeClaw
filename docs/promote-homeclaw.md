# Promote HomeClaw: Companion App, Plugins, Skills, Mix Mode, and Multi-Agent

A short guide to five strengths of HomeClaw: **one companion app on all devices**, **extend with plugins**, **reuse OpenClaw skillsets**, **save cost with mix mode**, and **run multiple agents** with no extra orchestration.

---

## 1. Companion App: One App, All Devices

The **HomeClaw Companion** is a **Flutter-based** client for **Mac, Windows, iPhone, and Android**. Same codebase, one install—chat and manage Core from any device.

- **Chat** — Send messages, attach images and files; voice input and TTS (speak replies).
- **Manage Core** — Edit **core.yml** and **user.yml** from the app (server, LLM, memory, tools, auth, etc.). No need to SSH or edit config files by hand.
- Use it **instead of** or **together with** WebChat, CLI, Telegram, and other channels—all talk to the same Core and memory.

**Takeaway:** One app for desktop and mobile; chat, voice, and config from your phone or laptop. See [Companion app](companion-app.md).

---

## 2. Plugins: Extend HomeClaw Your Way

**One plugin = one capability.** Weather, news, email, browser automation, custom APIs—you add what you need.

### Built-in plugins (Python)

- Live in `plugins/<Name>/`: `plugin.yaml`, `config.yml`, `plugin.py`.
- Core discovers them at startup. The LLM sees the list and calls **route_to_plugin(plugin_id)** when the user’s intent matches.
- Examples: Weather, News, Mail.

### External plugins (any language)

- **Write in any language:** Node.js, Go, Java, Python, etc.
- Run your plugin as an **HTTP server** with:
  - `GET /health` → 2xx
  - `POST /run` (or your path) → PluginRequest in, PluginResult out.
- **Register with Core:** `POST http://<core>:9000/api/plugins/register` with id, description, health URL, and capabilities.
- After that, Core routes to your server like built-in plugins. No need to write Python if you prefer another stack.

**Takeaway:** Add features without forking Core. Use Python for quick built-ins, or any language for external services.

---

## 3. Skills: Reuse OpenClaw Skillsets

HomeClaw supports **OpenClaw-style skills**: each skill is a folder under `config/skills/` with a **SKILL.md** (name, description, workflow). The LLM sees the skill list and uses **tools** to accomplish workflows, or calls **run_skill** to run scripts under `skill/scripts/`.

**You can reuse skillsets from OpenClaw:** put the same skill folders (with SKILL.md and any scripts) into HomeClaw’s `config/skills/` and they work. No rewrite—same format, same idea. HomeClaw loads them at startup and injects the skills block into the prompt so the model can choose and run them.

**Takeaway:** OpenClaw skills are compatible. Copy skill folders into `config/skills/` and use them in HomeClaw as-is.

---

## 4. Mix Mode: Save Cost by Routing Smart

**Problem:** Cloud APIs are powerful but cost money. Local models are free but may be weaker on hard tasks.

**Mix mode:** For **each user message**, HomeClaw decides once: use the **local** model or the **cloud** model for the whole turn. Simple or private tasks → local. Search, complex reasoning, or “I’m not sure” → cloud. You get **one model per turn**, chosen automatically.

### How it works

1. Set in `config/core.yml`:
   - `main_llm_mode: mix`
   - `main_llm_local: local_models/<your_local_id>`
   - `main_llm_cloud: cloud_models/<your_cloud_id>`
2. A **3-layer router** runs **before** tools and plugins, using only the user message:
   - **Layer 1 (heuristic):** Keywords and rules (e.g. “hello”, “thanks” → local).
   - **Layer 2 (semantic):** Similarity to example utterances (local vs cloud).
   - **Layer 3 (optional):** Small classifier or perplexity probe.
3. If no layer selects, **default_route** is used (`local` to save cost, or `cloud` for safety).

### Cost control

- **default_route: local** → when in doubt, stay local (fewer cloud calls).
- Tune **semantic threshold**: higher = fewer “semantic” matches, more fallback to default or Layer 3.
- Use **usage_report** (in chat or `GET /api/reports/usage`) to see how many requests went local vs cloud and tune rules.

**Takeaway:** Use local for cheap, simple, or private tasks; use cloud only when needed. One config, automatic per-request routing, and visibility into usage.

---

## 5. Multi-Agent: Run as Many Agents as You Need

**One HomeClaw instance = one agent** (one memory, one set of tools and plugins). To get **multiple agents**, run **multiple instances**.

### How to do it

- Start each instance with a **different port** and (if you want) a **different config**.
- Example: Agent A on port 9000, Agent B on port 9001. Different `core.yml` (or same file, different `server.port`).
- No central orchestrator: each instance is independent. Point your clients (Companion app, WebChat, Telegram, etc.) at the right port.

### When it helps

- **Separate roles:** e.g. one agent for home automation, one for work notes.
- **Isolation:** different users or projects on different instances.
- **Scale:** add more machines or more processes; each process is one agent.

**Takeaway:** Multi-agent = multi-instance. Run more processes (different ports/configs); no extra orchestration layer.

---

## Summary

| Topic        | In one sentence |
|-------------|------------------|
| **Companion app** | Flutter app for Mac, Windows, iPhone, Android: chat, voice, attachments, and edit core.yml/user.yml from the app. |
| **Plugins** | Add capabilities with built-in (Python) or external (any language) plugins; register once, LLM routes to them. |
| **Skills**  | Reuse **OpenClaw skillsets**: same SKILL.md format in `config/skills/`; copy skill folders over and they work. |
| **Mix mode**| Per-request routing: local for simple/private, cloud for hard tasks; 3-layer router + usage reports to control cost. |
| **Multi-agent** | One instance = one agent; run multiple instances (different ports/configs) for multiple agents, no orchestrator. |

For details, see [Companion app](companion-app.md), [Plugins](plugins.md), [Tools](tools.md) (skills), [Mix mode and reports](mix-mode-and-reports.md), and [Introducing HomeClaw](introducing-homeclaw.md).
