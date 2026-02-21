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

## File tools and base path

File tools (`file_read`, `file_write`, `document_read`, `folder_list`, `file_find`) only access paths **under** a configured base directory. Set it in `config/core.yml`:

```yaml
tools:
  file_read_base: "/Users/you/Documents/homeclaw"   # or "." for current working directory
```

- **You do not need to give the full path every time.** The model is told the current `file_read_base` and must use **relative paths** (e.g. `"."` for the base, `"subdir"` for a subfolder).
- **To list or find files:** Ask naturally, e.g. “列出 /Users/.../homeclaw 下所有 jpg 文件” or “find all jpg files in the homeclaw directory”. Core injects the actual base path into the system prompt so the model should call `file_find` with `pattern: "*.jpg"` and `path: "."` (relative to the base), not an absolute path.
- **If you see “path must be under the configured base directory”:** The model tried a path outside the base. Ensure `tools.file_read_base` in `core.yml` is the directory you want (e.g. `/Users/shileipeng/Documents/homeclaw`), and that the model uses relative paths; after the change, restart Core so the new base is injected.

---

## Plugins

**Plugins** add single-feature capabilities (weather, news, email). The LLM routes to them via **`route_to_plugin(plugin_id)`**.

- **Built-in (Python):** In `plugins/` with `plugin.yaml`, `config.yml`, `plugin.py`.
- **External (any language):** HTTP server; register with Core via `POST /api/plugins/register`.

See [PluginsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginsGuide.md) and [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md) in the repo.

---

## Skills

**Skills** (SKILL.md under `config/skills/`) describe workflows; the LLM uses **tools** to accomplish them or calls **`run_skill`** to run a script. OpenClaw-style skills can be reused. See [SkillsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/SkillsGuide.md) and [ToolsSkillsPlugins.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsSkillsPlugins.md) in the repo.
