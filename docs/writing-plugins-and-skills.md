# Writing plugins and skills

**Plugins** and **skills** are the main ways to extend HomeClaw’s ability. Plugins add focused features (weather, email, custom APIs); skills describe task workflows the assistant follows using tools (or scripts). This page introduces how to write both and where to find examples. In the future we plan a **website to discover, upload, and download** plugins and skills for HomeClaw.

---

## Why extend with plugins and skills?

| | **Plugins** | **Skills** |
|--|-------------|------------|
| **What** | Single-feature modules (weather, news, email, browser automation). | Task workflows: the LLM uses **tools** (or **run_skill** scripts) according to a skill’s instructions. |
| **Implementation** | Code: built-in (Python) or external (any language, HTTP server). | A **folder** with **SKILL.md** (name, description, workflow) and optional **scripts/**. |
| **When to use** | New capability that needs its own logic or API. | Reusable “how to do X” that uses existing tools or small scripts. |

Both are important: plugins give you new capabilities; skills give you reusable workflows and compatibility with **OpenClaw-style skillsets** (copy skill folders into `skills/` and they work).

---

## How to write a plugin

### Two ways: built-in (Python) vs external (any language)

| Type | Language | Where it runs | Best for |
|------|----------|---------------|----------|
| **Built-in** | Python only | In-process with Core | Fast integration, Python libs (Weather, News, Mail). |
| **External** | Any (Node.js, Go, Java, Python, etc.) | Separate HTTP server | Existing service, different language, or independent deployment. |

### Built-in plugin (Python)

- **Location:** `plugins/<YourPlugin>/` with:
  - **plugin.yaml** — id, name, description, type: inline, capabilities (optional).
  - **config.yml** — runtime config (API keys, defaults).
  - **plugin.py** — class extending `BasePlugin`; Core discovers it at startup.
- The LLM routes to the plugin via **`route_to_plugin(plugin_id)`** when the user intent matches.

### External plugin (any language)

- Run your plugin as an **HTTP server** that implements:
  - **GET /health** → return 2xx.
  - **POST /run** — body = PluginRequest JSON (capability_id, parameters, etc.); response = PluginResult JSON (text, etc.).
- **Register** with Core: `POST http://<core>:9000/api/plugins/register` with plugin id, name, description, `health_check_url`, `type: "http"`, and `capabilities`. After registration, Core routes to your server like built-in plugins.

**Detailed references:** [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md), [PluginStandard.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginStandard.md), [PluginRegistration.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginRegistration.md), [PluginsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginsGuide.md) in the repo.

---

## Examples: external plugins

### Small examples: `external_plugins/`

Working samples in multiple languages (same contract: GET /health, POST /run, register with Core):

| Example | Language | Port | Description |
|---------|----------|------|-------------|
| **Quote** | Python | 3101 | Random quote; get_quote_by_topic. post_process: true. |
| **Time** | Python | 3102 | Current time, list timezones. post_process: true. |
| **Quote** | Node.js | 3111 | Same quote contract, Node.js. |
| **Time** | Go | 3112 | Same time contract, Go (stdlib). |
| **Quote** | Java | 3113 | Same quote contract, Java (JDK 11+). |

### Full-featured examples

| Example | Language | Location | Description |
|---------|----------|----------|-------------|
| **HomeClaw Browser** | Node.js | **system_plugins/homeclaw-browser** | **System plugin**: WebChat (Control UI), browser automation (Playwright), canvas, nodes. Same contract; register with Core. Port 3020. See [system_plugins/README.md](https://github.com/allenpeng0705/HomeClaw/blob/main/system_plugins/README.md) and [homeclaw-browser/README.md](https://github.com/allenpeng0705/HomeClaw/blob/main/system_plugins/homeclaw-browser/README.md). |
| **Companion plugin** | Python | See repo | A Python-based companion/utility plugin is another external plugin example (same contract). See **external_plugins/** or the repo for the latest location and run steps. |

Each small example: run the plugin server, then register with Core via the provided `register` script or module. See **[external_plugins/README.md](https://github.com/allenpeng0705/HomeClaw/blob/main/external_plugins/README.md)** for run commands and the **contract** (GET /health, POST /run, registration payload).

---

## How to write a skill

- **Location:** A **folder** under **`skills/`** (or the path set by **skills_dir** in `config/core.yml`).
- **Required:** **SKILL.md** with:
  - **Name** — short title.
  - **Description** — when to use this skill (for LLM routing).
  - **Workflow** — step-by-step instructions; the LLM uses **tools** (file_read, browser_*, cron, memory_search, etc.) to follow them.
- **Optional:** **scripts/** — scripts the LLM can run via **`run_skill`** (e.g. Python, Node.js, shell).

Enable skills in **config/core.yml**: `use_skills: true`, `skills_dir: skills`. Restart Core. The assistant sees “Available skills” and can choose and run them. **OpenClaw skills** use the same format; copy skill folders into `skills/` and they work.

**Detailed reference:** [SkillsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/SkillsGuide.md), [ToolsSkillsPlugins.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsSkillsPlugins.md) in the repo.

---

## Summary

| Goal | Where to start |
|------|-----------------|
| **Write a built-in plugin** | `plugins/<Name>/` with plugin.yaml, config.yml, plugin.py; [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md). |
| **Write an external plugin** | HTTP server (GET /health, POST /run); register with Core; see **external_plugins/** and [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md). |
| **Write a skill** | Folder under `skills/` with SKILL.md (and optional scripts/); [SkillsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/SkillsGuide.md). |

---

## Future: plugin and skill marketplace

We plan to offer a **website to discover, upload, and download** plugins and skills for HomeClaw. You will be able to share your plugins and skills with the community and install others’ with a few clicks. Stay tuned for updates.
