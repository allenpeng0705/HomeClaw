# Tools

HomeClaw provides **tools** the LLM can call by name (file, exec, browser, cron, memory, web search, sessions, etc.) and **plugins** for focused features (Weather, News, Mail). Enable with **`use_tools: true`** in `config/core.yml`.

---

## Tool categories

| Category        | Examples                                      |
|----------------|-----------------------------------------------|
| **Files / folders** | `file_read`, `file_write`, `file_edit`, `folder_list`, `document_read`, `markdown_to_pdf` |
| **Web**        | `fetch_url`, `web_search`, `browser_navigate`, `browser_snapshot`, `browser_click` |
| **Memory**     | `memory_search`, `memory_get` (when use_memory) |
| **Scheduling** | `cron_schedule`, `cron_list`, `remind_me`, `record_date` |
| **Sessions**   | `sessions_list`, `sessions_transcript`, `sessions_send`, `sessions_spawn` |
| **Routing**    | `route_to_plugin`, `route_to_tam`, `run_skill` |
| **MCP**        | `mcp_list_tools`, `mcp_call` (optional; see [MCP](mcp.md)) |

Config (allowlists, timeouts, API keys) is under **`tools:`** in `config/core.yml`. MCP server config is under **`tools.mcp`** in `config/skills_and_plugins.yml` — see [Using MCP](mcp.md). See [ToolsDesign.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsDesign.md) and [ToolsAndSkillsTesting.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsAndSkillsTesting.md) in the repo.

---

## File tools and base path

File tools (`file_read`, `file_write`, `document_read`, `folder_list`, `file_find`, `file_understand`) use one of two modes:

**When `file_read_base` is set** (recommended for multi-user):

- **One base folder** (e.g. `D:/homeclaw`). Under it:
  - **Share folder:** Paths starting with `share/` (config `file_read_shared_dir`, default `share`) are accessible by **all users and the companion app**.
  - **Per-user folders:** Named by user **id** from `config/user.yml`. Each user only sees their own folder; created automatically.
  - **Companion folder:** When the companion app is not tied to a user, it uses the **companion** folder so it can access `share/` and `companion/`.
- Paths are always under the base. Use `share/readme.txt` for shared files, or `mydoc.txt` in your user or companion folder.
- **Output folder:** For generated files (reports, images, exports), use path **`output/<filename>`**. This goes to the user’s or companion’s private `output` subfolder (`base/{user_id}/output/` or `base/companion/output/`). See [FileSandboxDesign.md](../docs_design/FileSandboxDesign.md).
- **Reports and file links:** Use the **save_result_page** tool to generate HTML reports; Core saves to the user’s output folder and returns a **link** (e.g. `http://127.0.0.1:9000/files/out?path=output/report_xxx.html&token=...`). The user can open the link to view or download. Set **auth_api_key** in config so links are signed. For **Markdown → PDF** (e.g. long summaries), use **markdown_to_pdf**(content=…, path=output/filename.pdf); the tool returns the file link. For other formats (PPT), write to **output/** with **file_write**; see [FileSandboxDesign.md § How to use](../docs_design/FileSandboxDesign.md) for link and folder usage.

**When `file_read_base` is not set:**

- **Absolute paths are allowed** (whole machine). Use an absolute path to read/write anywhere. No per-user or shared structure.

```yaml
tools:
  file_read_base: "D:/homeclaw"   # when set: share + per-user + companion under it; when unset: absolute paths allowed
  file_read_shared_dir: "share"   # optional; default "share"
```
- **To list or find files:** Ask naturally, e.g. “列出 homeclaw 下所有 jpg 文件” or “find all Word documents in the homeclaw directory”. Core injects the base path and instructs the model to call **file_find** with the right **pattern** (e.g. `*.jpg`, `*.docx`, `*.pdf`) and `path: "."`. The model must report only paths returned by the tool—not invent paths.
- **Word and PDF:** To find Word docs the model should call `file_find(pattern="*.docx", path=".")` (or `*.doc` for older Word). To find PDFs use `pattern="*.pdf"`. To read the content of a found file use **document_read(path=…)** with the relative path from the tool result.
- **If you see “path must be under the configured base directory” or invented paths (e.g. wrong usernames/folders):** The model tried a path outside the base. Ensure `tools.file_read_base` in `core.yml` is the directory you want (e.g. `/Users/shileipeng/Documents/homeclaw`), and that the model uses relative paths; after the change, restart Core so the new base is injected.

---

## Markdown to PDF

The **markdown_to_pdf** tool converts Markdown text to a PDF file and saves it under the user's output folder, returning a view link. Used by the **summarize** skill when the summary is long so the user gets both the inline summary and a downloadable PDF without asking.

- **Parameters:** `content` (Markdown string), `path` (e.g. `output/summary.pdf`).
- **Converter (priority):** (1) **VMPrint** — install via **`./install.sh`** or **`install.ps1`** / **`install.bat`** (clones into `tools/vmprint`, runs `npm install`). Config default: `tools.markdown_to_pdf.vmprint_dir: "tools/vmprint"`. (2) **pandoc** on PATH. (3) **pip install markdown weasyprint** (Markdown → HTML → PDF).

---

## Plugins

**Plugins** add single-feature capabilities (weather, news, email). The LLM routes to them via **`route_to_plugin(plugin_id)`**.

- **Built-in (Python):** In `plugins/` with `plugin.yaml`, `config.yml`, `plugin.py`.
- **External (any language):** HTTP server; register with Core via `POST /api/plugins/register`.

See [PluginsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginsGuide.md) and [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md) in the repo.

---

## Skills

**Skills** (SKILL.md under `skills/`) describe workflows; the LLM uses **tools** to accomplish them or calls **`run_skill`** to run a script. OpenClaw-style skills can be reused. See [SkillsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/SkillsGuide.md) and [ToolsSkillsPlugins.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsSkillsPlugins.md) in the repo.
