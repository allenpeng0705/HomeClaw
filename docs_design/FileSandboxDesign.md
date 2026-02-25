# File handling sandbox design

This document defines how HomeClaw restricts file and folder access per user and companion, and how all file-related features (including **outputs**) must behave. The implementation never crashes Core: all file tools return string messages on error.

**User-facing doc:** [docs/per-user-sandbox-and-file-links.md](../docs/per-user-sandbox-and-file-links.md) — summary for users (per-user sandbox, output folder, generate link).

## Three areas: workspace vs sandbox vs share

| Area | Purpose | Used by channel/companion? | Config / path |
|------|---------|----------------------------|---------------|
| **Workspace** | Internal working folder: IDENTITY.md, AGENTS.md, TOOLS.md, AGENT_MEMORY, daily memory. | **No** — do not use for user file access. | `workspace_dir` (e.g. `config/workspace`) |
| **Sandbox (per user)** | Main folder for each user. File search, read, write; generated files go into **output**; **knowledgebase** subfolder for KB sync. | **Yes** — default base for file tools. | `homeclaw_root/{user_id}/` (or `homeclaw_root/companion/`) |
| **Share** | Shared by all users. Use when the user says "share" or when the file is not in the user's sandbox. | **Yes** — path `share` or `share/...`. | `homeclaw_root/share/` |

- **homeclaw_root** (in `config/core.yml`, top-level) is **required** for file and folder access from channel/companion. When it is not set, file tools return a clear message: set homeclaw_root so that each user has a subfolder (e.g. `homeclaw_root/{user_id}/` for private files, `homeclaw_root/share` for shared). Core does **not** fall back to workspace_dir for user files — workspace is internal only.
- Under **homeclaw_root** we have:
  - **Per-user sandbox** – `homeclaw_root/{user_id}/` (or `homeclaw_root/companion/` when not tied to a user). Path `"."` or `"subdir"` resolves here. Subfolders: **output/** (generated files; use path `output/<filename>` and return a link), **knowledgebase/** (for KB folder sync).
  - **Share** – `homeclaw_root/share/`. Path `share` or `share/...` resolves here. Visible and writable by all users and companion.
- When the user asks for file search, list, or read **without specifying a folder**: search/list in the user's sandbox first (path `"."`); if not found or the user says "share", use path `"share"` or `"share/..."`. Results (e.g. generated reports, PPT) go into **output/** and Core generates a link and sends it back.

## Overview

- **One configurable root** (`homeclaw_root` in `config/core.yml`, top-level). When set, all file/folder tools are restricted to paths under this root. When **not** set, file tools return a clear error — do not use workspace for user files.
- Under the root we have:
  - **Shared folder** – paths starting with `share/` (or the configured `tools.file_read_shared_dir`) are visible and writable by all users and the companion app.
  - **Per-user folders** – one folder per user (by `system_user_id` from `config/user.yml`). Paths that do not start with `share/` are resolved under `homeclaw_root/{user_id}/` (or `companion/` when not tied to a user).
  - **Default folder** – when there is no user and no companion context, paths resolve under `homeclaw_root/default/`.
- **Output folder** – each user and the companion have a dedicated **output** subfolder for generated files (e.g. images, reports, exports). Paths like `output/filename` resolve to `homeclaw_root/{user_id}/output/` or `homeclaw_root/companion/output/`. All file-output features must write there and return a link (see below).

## When `homeclaw_root` is set

| Path form        | Resolves to                    | Who can access        |
|------------------|---------------------------------|------------------------|
| `share` / `share/...` | `homeclaw_root/share/` or `homeclaw_root/share/...` | All users + companion |
| Any other path   | `homeclaw_root/{user_id}/...` or `homeclaw_root/companion/...` or `homeclaw_root/default/...` | That user or companion only |
| `output/...`     | `homeclaw_root/{user_id}/output/...` or `homeclaw_root/companion/output/...` | That user or companion only |

- Folder names under the root are derived from `system_user_id` (user.yml) with a safe segment (alphanumeric, underscore, hyphen; max 64 chars). Unknown or missing user falls back to `default`.
- Companion context is detected when any of `session_id`, `user_id`, `app_id`, `channel_name`, or request metadata `conversation_type`/`session_id` is `"companion"` (case-insensitive).
- Shared directory name is configurable via `tools.file_read_shared_dir` (default `"share"`). Comparison is case-insensitive for the prefix.

## Output folder convention

- **Reserved subfolder name:** `output` (configurable in the future via e.g. `tools.file_read_output_dir`).
- **Rule:** Any feature that **writes a file as a result of user or companion interaction** (generated images, reports, exports, downloads, etc.) must write under the current workspace’s **output** folder:
  - For a **user** request: use path `output/<filename>` so the file is stored under `base/{user_id}/output/`.
  - For **companion** (no user): use path `output/<filename>` so the file is stored under `base/companion/output/`.
- No special resolution is required: the existing `_resolve_file_path(path, context, for_write=True)` already resolves `output/...` to the correct per-user or companion output directory. Skills, plugins, and built-in tools that produce files should pass paths like `output/report.pdf` or `output/image.png` so outputs stay in the user’s (or companion’s) private area and follow this design.

## When `homeclaw_root` is not set

- File and folder tools return a clear message: set **homeclaw_root** in config/core.yml so that each user has a subfolder (e.g. `homeclaw_root/{user_id}/` for private files, `homeclaw_root/share` for shared). Core does **not** use workspace_dir for user file access — workspace is internal only.

## Safety and robustness

- **No crashes:** All file-tool executors (e.g. `file_read`, `file_write`, `file_edit`, `folder_list`, `file_find`, `document_read`, `file_understand`, `apply_patch`, `image_analyze`) call `_resolve_file_path()`, then `_path_under(full, base)`, and are wrapped in `try/except`. They return string messages only (e.g. “You don’t have permission…”, “That file or path wasn’t found…”) and never raise.
- **Path traversal:** Resolved paths are checked with `_path_under(full, base)` so that paths like `../etc/passwd` or `output/../../../other` cannot escape the base. Cross-platform (Windows and Unix) via `Path.resolve()` and `relative_to()`.
- **Resolution errors:** `_resolve_file_path()` never raises; it returns `None` on any exception. Callers treat `None` as “invalid path” and return a polite message.

## Future file/folder features

- Any new file or folder feature (built-in tools, skills, plugins) must:
  - Use `_resolve_file_path(path, context, for_write=...)` for resolution and then `_path_under(full, base)` for validation.
  - On resolution or validation failure, return a string message and never raise.
- Any feature that **produces a file as output** (e.g. “save this report”, “generate image”, “export to file”) must write under the **output** folder for the current context:
  - User context → path like `output/<filename>` (resolves to `base/{user_id}/output/`).
  - Companion context → path like `output/<filename>` (resolves to `base/companion/output/`).

## Serving files and folder listings (same URL as Core)

Core serves sandbox files and folder listings from **its own server** at `GET /files/out`. One public URL (e.g. the one the Companion app uses) is enough; no separate report server or second port.

- **Config (top-level in config/core.yml):**
  - **`core_public_url`** – Public URL that reaches Core (e.g. from Cloudflare Tunnel, Tailscale Funnel). Used to build shareable links. Leave empty for local-only. When you use **Pinggy** (`pinggy.token`), Core does **not** write this to config; instead, when the Pinggy tunnel is up, Core sets a **runtime public URL** so the same Pinggy URL is used for file/report links, folder listing links, and the /pinggy scan-to-connect page.
  - **`auth_api_key`** – Used to sign file-access tokens so links can be opened in a browser without sending the API key. When `auth_enabled` is true, the same key protects `/inbound` and `/ws`. Set both for shareable report/folder links.
- **Flow:** Tools (e.g. **save_result_page**) write files into the user’s or companion’s **output** folder, then return a link: `core_public_url/files/out?path=output/report_xxx.html&token=...`. The token is signed (scope + path + expiry) with `auth_api_key`.
- **Route:** `GET /files/out?path=...&token=...` verifies the token, resolves the path under `homeclaw_root/{scope}/`, and either serves the **file** (HTML, Markdown, images, etc.) or, if the path is a **directory**, returns an **HTML listing** with links to each file and subfolder (each link has its own token). So “what’s in this folder?” can be answered with a link that opens a web page listing the contents.
- **HTML/MD in chat:** When a response is better shown as HTML or Markdown (e.g. a report or folder listing), the model can use **save_result_page** and return the link. In the future, the Companion app may render HTML and Markdown directly in the chat view so the user can see formatted content without opening a browser.

## How to use: reports, HTML, PPT, and file links

This feature lets HomeClaw generate files (HTML reports, exported data, and later PPT or other formats), put them in the user’s or companion’s **output** folder, and send a **link** the user can open or download. No separate server or port: the same Core URL is used.

### 1. Config (minimal for local use)

- **`config/core.yml`** (top level):
  - **`auth_api_key`** – Set to any non-empty string (e.g. a secret you choose). Required to **sign** file links so they can be opened in a browser without sending the API key. If you use **`auth_enabled: true`** for /inbound, use the same key here.
  - **`core_public_url`** – Optional. When set (e.g. `https://homeclaw.example.com`), report/folder links use this URL. When **empty**, Core uses **`http://127.0.0.1:<port>`** (or **host:port** from config) so links work on the same machine. When using **Pinggy**, leave empty and Core will use the Pinggy URL once the tunnel is up.
- **`homeclaw_root`** (top-level in config/core.yml) – Must be set (e.g. `D:/homeclaw`) so the sandbox and output folders exist. Files are stored under `homeclaw_root/<user_id>/output/` or `homeclaw_root/companion/output/`. When not set, file tools return a clear error; Core does not use workspace for user files.

### 2. Markdown vs HTML: when to use which

- **`format=markdown`** (default): Saves as **`.md`** (raw Markdown). Best for **short or medium** text, summaries, lists — content suitable for **display in the chat view**. The tool **returns the markdown content in its result** so the model can include it in the reply; the channel/Companion/web chat then **display it directly in the chat view** (no need to open the link for the content). The link is also returned for opening the full report. Use when the response is simple text/markdown and not very long.
- **`format=html`**: Saves as **`.html`** (styled page). Best for **long or complex** output: multi-section reports, tables, or when the model generates full HTML. The user typically opens the link in a browser. Use when the output is complex or very long.
- **Rule for the model:** If the output is complex or very long → **html**. If it is simple text suitable for in-chat display → **markdown**.

### 3. Generate a report and send a link

- **Model uses the tool:** **`save_result_page`** with `title`, `content`, and `format` (`"markdown"` or `"html"`). Core writes to the user’s or companion’s **output** folder (e.g. `output/report_<id>.md` or `output/report_<id>.html`). **Markdown:** The tool returns the **markdown content** (capped for reply length) plus the link; the model includes the content in its reply so the channel/Companion/web chat can display it directly in the chat view; the link is for opening the full report. **HTML:** The tool returns only **"Report is ready. Open: &lt;link&gt;"**; the user opens the link in a browser.
- **User:** Opens the link in a browser to view the report, or uses “Open in app” / “Download” in the Companion app. The link is **signed** (token in the URL) and **time-limited** (default 24 hours; max 7 days).
- **Same flow for:** Any generated HTML, exported data as HTML, or (in the future) PPT/PDF written to **output** and a link returned. The model should write to path **`output/<filename>`** and then the app or a small helper can build the same kind of link (or use **save_result_page** for HTML).

### 4. Generate other files (e.g. PPT) and give a link

- **Today:** For non-HTML files (e.g. PPT, PDF), the model can use **`file_write`** with path **`output/<filename>`** (e.g. `output/presentation.pptx`). The file is saved in the user’s output folder. To give the user a **link**, we need a signed token for that path: the same token logic as **save_result_page** applies. So either:
  - Add a small tool or convention that, after writing `output/foo.pptx`, returns **`get_core_public_url() + "/files/out?path=output/foo.pptx&token=" + create_file_access_token(scope, "output/foo.pptx")`**, or
  - Have the model call **save_result_page** for HTML; for PPT/PDF the model can **file_write** to **output/** and tell the user “File saved to your output folder; open it from the folder link” and optionally provide a **folder** link (see below).
- **Folder link:** The user can ask “show my output folder” or “what’s in my output folder?”. The model can call **folder_list** and then either describe the list or (when we support it) return a link to **GET /files/out** with path **`output`** and a token for **`output`**, which shows an HTML listing of the output folder; from there the user can click files to open or download them.

### 5. Open link vs download

- **Open in browser:** The link opens in the default browser. For HTML/Markdown, the page is displayed; for other types (e.g. PDF, PPT), the browser may open or download depending on the app.
- **Download:** User can right-click the link → “Save link as” / “Download” to save the file.
- **In Companion app:** The app can open the link in an in-app WebView (for HTML) or hand off to the system (open in browser / external app, or download).

### 6. Safety (no crash, no escape)

- **Core never crashes:** All file tools and **GET /files/out** return JSON or HTML responses; errors return HTTP 4xx/5xx and a message, never an uncaught exception.
- **Path safety:** Token path and scope are validated (no `..`, no `/` in scope); resolved path is checked to stay under **homeclaw_root**. Symlinks are resolved; access outside the root returns 403.
- **Token:** Signed with **auth_api_key**; expired or invalid token returns 403.

## Checking the sandbox without combining a user

When the Companion app is used **without** combining a user, requests are routed to the companion plugin (e.g. Friends), which does not run Core’s file tools. To **check the file sandbox** for the companion (or any scope) without going through the LLM or combining a user, use:

- **`GET /api/sandbox/list?scope=companion&path=.`**  
  Lists the companion’s private folder (same as `homeclaw_root/companion/`). Use `path=output` to list only the output subfolder.
- **`GET /api/sandbox/list?scope=companion&path=output`**  
  Lists `homeclaw_root/companion/output/`.
- **`GET /api/sandbox/list?scope=<user_id>&path=.`**  
  Lists a specific user’s folder (use the same `scope` as in user.yml / `system_user_id`).

Auth: when `auth_enabled` and `auth_api_key` are set, send `X-API-Key` or `Authorization: Bearer` as for `/inbound`. Response: JSON `{ "scope", "path", "entries": [ { "name", "type", "path" }, ... ] }`.

## References

- Implementation: `tools/builtin.py` (file executors, `_resolve_file_path`, `_path_under`); `core/result_viewer.py` (tokens, `generate_result_html`); `core/core.py` (`GET /files/out`, `GET /api/sandbox/list`).
- Config: `config/core.yml` top-level `core_public_url`, `auth_api_key`, **`homeclaw_root`** (required for file/sandbox access); under `tools`: `file_read_shared_dir`. Optional under `tools`: `save_result_page_max_file_size_kb` (default 500) for generated report HTML size limit.
- User identity: `config/user.yml` (`system_user_id` for per-user folder name).
- Docs: `docs/tools.md` (file tools section), `docs_design/MultiUserSupport.md` (file workspace row).
