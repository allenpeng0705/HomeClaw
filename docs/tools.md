# Tools

HomeClaw provides **tools** the LLM can call by name (file, exec, browser, cron, memory, web search, sessions, etc.) and **plugins** for focused features (Weather, News, Mail). Enable with **`use_tools: true`** in `config/core.yml`.

---

## Tool categories

| Category        | Examples                                      |
|----------------|-----------------------------------------------|
| **Files / folders** | `file_read`, `file_write`, `file_edit`, `folder_list`, `document_read` |
| **Web**        | `fetch_url`, `web_search`, `browser_navigate`, `browser_snapshot`, `browser_click` |
| **Memory**     | `memory_search`, `memory_get` (when use_memory) |
| **Scheduling** | `cron_schedule`, `cron_list`, `remind_me`, `record_date` |
| **Sessions**   | `sessions_list`, `sessions_transcript`, `sessions_send`, `sessions_spawn` |
| **Routing**    | `route_to_plugin`, `route_to_tam`, `run_skill` |

Config (allowlists, timeouts, API keys) is under **`tools:`** in `config/core.yml`. See [ToolsDesign.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsDesign.md) and [ToolsAndSkillsTesting.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsAndSkillsTesting.md) in the repo.

---

## Plugins

**Plugins** add single-feature capabilities (weather, news, email). The LLM routes to them via **`route_to_plugin(plugin_id)`**.

- **Built-in (Python):** In `plugins/` with `plugin.yaml`, `config.yml`, `plugin.py`.
- **External (any language):** HTTP server; register with Core via `POST /api/plugins/register`.

See [PluginsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginsGuide.md) and [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md) in the repo.

---

## Skills

**Skills** (SKILL.md under `config/skills/`) describe workflows; the LLM uses **tools** to accomplish them or calls **`run_skill`** to run a script. OpenClaw-style skills can be reused. See [SkillsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/SkillsGuide.md) and [ToolsSkillsPlugins.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsSkillsPlugins.md) in the repo.
