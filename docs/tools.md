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
| **Multi-instance** | `peer_call` (call another Core from `peers.yml`) |
| **Routing**    | `route_to_plugin`, `route_to_tam`, `run_skill` |
| **MCP**        | `mcp_list_tools`, `mcp_call` (optional; see [MCP](mcp.md)) |

Config (allowlists, timeouts, API keys) is under **`tools:`** in `config/core.yml`. MCP server config is under **`tools.mcp`** in `config/skills_and_plugins.yml` — see [Using MCP](mcp.md). See [ToolsDesign.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsDesign.md) and [ToolsAndSkillsTesting.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsAndSkillsTesting.md) in the repo.

For peer setup and pairing, see [Multi-instance peers & pairing](multi-instance-peers.md).

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
- **Converter (priority):** (1) **VMPrint** — install via **`./install.sh`** or **`install.ps1`** / **`install.bat`** (clones into `tools/vmprint`, runs **`npm install`** + **`npm run build`**; refreshes missing preview deps). **Manual install:** [VMPrint as UI runtime — Manual installation for HomeClaw](vmprint-ui-runtime.md#manual-installation-for-homeclaw). Config default: `tools.markdown_to_pdf.vmprint_dir: "tools/vmprint"`. (2) **pandoc** on PATH. (3) **pip install markdown weasyprint** (Markdown → HTML → PDF).

---

## VMPrint runtime outputs

Use **`vmprint_render`** when you want VMPrint artifacts beyond plain PDF:

- `output_format: "pdf"` — final printable file
- `output_format: "ast_json"` — transmuted VMPrint AST JSON
- `output_format: "layout_json"` — flat scene-graph style page/box layout stream (for advanced previews)
- `output_format: "browser_preview_html"` — browser-openable preview artifact generated under `output/`

For channel/Companion delivery, save under `output/` and share the returned `/files/out` link. The same link pattern works across WebChat, Companion, and other channels.

See also: [VMPrint as UI runtime](vmprint-ui-runtime.md) — includes **layout_json** sidecar + hybrid preview (**SVG / Boxes** toggle), `web_search` AST template in `magazine-render`, and how the upstream **simulation / actor** engine relates to **AI integration**.

---

## VMPrint decision matrix (recommended)

Use this quick policy for long/formatted responses.

| Input you have | Preferred call | Default output | Notes |
|---|---|---|---|
| Structured JSON (`daily_brief`, `weather`, `stock`) | `run_skill` -> `magazine-render-1.0.0` `render-template-ast` | `browser_preview_html` | **AST-first** path for best UI control. |
| Domain JSON (`daily-brief`) | `run_skill` -> `magazine-render-1.0.0` `render-daily-brief-ast` | `browser_preview_html` | Dedicated template path; stable table/header behavior. |
| AST JSON 1.1 already available | `run_skill` -> `magazine-render-1.0.0` `render-ast` | `browser_preview_html` | Use `layout_json` for diagnostics; PDF optional. |
| Only Markdown available | `vmprint_render` or `render-md` fallback | `browser_preview_html` | Markdown path is fallback when structured JSON/AST is unavailable. |
| User explicitly asks print/download/export | any VMPrint path | `pdf` | PDF is explicit opt-in target. |

Operational defaults:

- Long/formatted responses: **preview link first** (`browser_preview_html`)
- Printing/sharing file export: **PDF on request**
- Debug/QA layout issues: emit **`layout_json`**

Inline/link threshold tuning (no code edits):

- Core tool path (`vmprint_render`) reads `tools.vmprint_preview_inline` from `config/core.yml`:

```yaml
tools:
  vmprint_preview_inline:
    max_ast_chars: 120000
    max_pages: 2
```

- `magazine-render` skill path reads env vars:
  - `HOMECLAW_VMPRINT_INLINE_MAX_AST_CHARS`
  - `HOMECLAW_VMPRINT_INLINE_MAX_PAGES`

### Quick examples

```json
{
  "tool": "run_skill",
  "arguments": {
    "skill_name": "magazine-render-1.0.0",
    "script": "render_magazine.py",
    "args": [
      "render-template-ast",
      "--template",
      "weather",
      "--title",
      "Weather Brief",
      "--theme",
      "dispatch",
      "--json",
      "{\"location\":\"Beijing\",\"now\":{\"condition\":\"Cloudy\",\"temp\":\"18C\"},\"forecast\":[{\"day\":\"Fri\",\"summary\":\"Cloudy\",\"high\":\"21C\",\"low\":\"14C\"}]}",
      "--output_format",
      "browser_preview_html",
      "--out",
      "weather_brief.preview.html"
    ]
  }
}
```

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Long Summary\n\n## Highlights\n\n- ...",
    "path": "output/summary.preview.html",
    "output_format": "browser_preview_html",
    "vmprint_profile": "literature"
  }
}
```

---

## Magazine-style PDFs (skill)

If the user asks for a more **beautiful / readable / magazine-like** report layout, use the skill **`magazine-render-1.0.0`**:

- **Markdown mode:** `run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py", args=["render-md", "--title", "...", "--md", "<MARKDOWN>", "--out", "report.pdf"])`
- **JSON template mode:** `render-json --template daily_brief|weather|stock --json "{...}" --out report.pdf`

The skill uses **VMPrint** (draft2final) under the hood and writes to the user's `output/` folder; the returned result includes a view link when file serving is configured.

For **daily-brief** formatted output, default to `browser_preview_html` (channel/Companion reading), and generate PDF only when the user explicitly asks for download/print.

---

## Plugins

**Plugins** add single-feature capabilities (weather, news, email). The LLM routes to them via **`route_to_plugin(plugin_id)`**.

- **Built-in (Python):** In `plugins/` with `plugin.yaml`, `config.yml`, `plugin.py`.
- **External (any language):** HTTP server; register with Core via `POST /api/plugins/register`.

See [PluginsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/PluginsGuide.md) and [HowToWriteAPlugin.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/HowToWriteAPlugin.md) in the repo.

---

## Skills

**Skills** (SKILL.md under `skills/`) describe workflows; the LLM uses **tools** to accomplish them or calls **`run_skill`** to run a script. OpenClaw-style skills can be reused. See [SkillsGuide.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/SkillsGuide.md) and [ToolsSkillsPlugins.md](https://github.com/allenpeng0705/HomeClaw/blob/main/docs_design/ToolsSkillsPlugins.md) in the repo.
