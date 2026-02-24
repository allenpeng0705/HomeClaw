# File handling sandbox design

This document defines how HomeClaw restricts file and folder access per user and companion, and how all file-related features (including **outputs**) must behave. The implementation never crashes Core: all file tools return string messages on error.

**User-facing doc:** [docs/per-user-sandbox-and-file-links.md](../docs/per-user-sandbox-and-file-links.md) — summary for users (per-user sandbox, output folder, generate link).

## Overview

- **One configurable base directory** (`tools.file_read_base` in `config/core.yml`). When set, all file/folder tools are restricted to paths under this base. When not set, absolute paths are allowed (no sandbox).
- Under the base we have:
  - **Shared folder** – paths starting with `share/` (or the configured `file_read_shared_dir`) are visible and writable by all users and the companion app.
  - **Per-user folders** – one folder per user (by `system_user_id` from `config/user.yml`). Paths that do not start with `share/` are resolved under `base/{user_id}/`.
  - **Companion folder** – when the request is from the companion app and not tied to a specific user, paths resolve under `base/companion/`.
  - **Default folder** – when there is no user and no companion context, paths resolve under `base/default/`.
- **Output folder** – each user and the companion have a dedicated **output** subfolder for generated files (e.g. images, reports, exports). Paths like `output/filename` resolve to `base/{user_id}/output/` or `base/companion/output/`. All future file-output features must write there (see below).

## When `file_read_base` is set

| Path form        | Resolves to                    | Who can access        |
|------------------|---------------------------------|------------------------|
| `share` / `share/...` | `base/share/` or `base/share/...` | All users + companion |
| Any other path   | `base/{user_id}/...` or `base/companion/...` or `base/default/...` | That user or companion only |
| `output/...`     | `base/{user_id}/output/...` or `base/companion/output/...` | That user or companion only |

- Folder names under the base are derived from `system_user_id` (user.yml) with a safe segment (alphanumeric, underscore, hyphen; max 64 chars). Unknown or missing user falls back to `default`.
- Companion context is detected when any of `session_id`, `user_id`, `app_id`, `channel_name`, or request metadata `conversation_type`/`session_id` is `"companion"` (case-insensitive).
- Shared directory name is configurable via `tools.file_read_shared_dir` (default `"share"`). Comparison is case-insensitive for the prefix.

## Output folder convention

- **Reserved subfolder name:** `output` (configurable in the future via e.g. `tools.file_read_output_dir`).
- **Rule:** Any feature that **writes a file as a result of user or companion interaction** (generated images, reports, exports, downloads, etc.) must write under the current workspace’s **output** folder:
  - For a **user** request: use path `output/<filename>` so the file is stored under `base/{user_id}/output/`.
  - For **companion** (no user): use path `output/<filename>` so the file is stored under `base/companion/output/`.
- No special resolution is required: the existing `_resolve_file_path(path, context, for_write=True)` already resolves `output/...` to the correct per-user or companion output directory. Skills, plugins, and built-in tools that produce files should pass paths like `output/report.pdf` or `output/image.png` so outputs stay in the user’s (or companion’s) private area and follow this design.

## When `file_read_base` is not set

- Paths can be absolute; there is no base restriction. Validation `_path_under(full, base)` receives `base=None` and allows any path. Use this only in trusted/single-user setups.

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
- **Route:** `GET /files/out?path=...&token=...` verifies the token, resolves the path under `file_read_base/{scope}/`, and either serves the **file** (HTML, Markdown, images, etc.) or, if the path is a **directory**, returns an **HTML listing** with links to each file and subfolder (each link has its own token). So “what’s in this folder?” can be answered with a link that opens a web page listing the contents.
- **HTML/MD in chat:** When a response is better shown as HTML or Markdown (e.g. a report or folder listing), the model can use **save_result_page** and return the link. In the future, the Companion app may render HTML and Markdown directly in the chat view so the user can see formatted content without opening a browser.

## How to use: reports, HTML, PPT, and file links

This feature lets HomeClaw generate files (HTML reports, exported data, and later PPT or other formats), put them in the user’s or companion’s **output** folder, and send a **link** the user can open or download. No separate server or port: the same Core URL is used.

### 1. Config (minimal for local use)

- **`config/core.yml`** (top level):
  - **`auth_api_key`** – Set to any non-empty string (e.g. a secret you choose). Required to **sign** file links so they can be opened in a browser without sending the API key. If you use **`auth_enabled: true`** for /inbound, use the same key here.
  - **`core_public_url`** – Optional. When set (e.g. `https://homeclaw.example.com`), report/folder links use this URL. When **empty**, Core uses **`http://127.0.0.1:<port>`** (or **host:port** from config) so links work on the same machine. When using **Pinggy**, leave empty and Core will use the Pinggy URL once the tunnel is up.
- **`tools.file_read_base`** – Must be set (e.g. `D:/homeclaw`) so the sandbox and output folders exist. Files are stored under `file_read_base/<user_id>/output/` or `file_read_base/companion/output/`.

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
- **Path safety:** Token path and scope are validated (no `..`, no `/` in scope); resolved path is checked to stay under **file_read_base**. Symlinks are resolved; access outside the base returns 403.
- **Token:** Signed with **auth_api_key**; expired or invalid token returns 403.

## References

- Implementation: `tools/builtin.py` (file executors, `_resolve_file_path`, `_path_under`); `core/result_viewer.py` (tokens, `generate_result_html`); `core/core.py` (`GET /files/out`).
- Config: `config/core.yml` top-level `core_public_url`, `auth_api_key`; under `tools`: `file_read_base`, `file_read_shared_dir`. Optional under `tools`: `save_result_page_max_file_size_kb` (default 500) for generated report HTML size limit.
- User identity: `config/user.yml` (`system_user_id` for per-user folder name).
- Docs: `docs/tools.md` (file tools section), `docs_design/MultiUserSupport.md` (file workspace row).
