# Per-user sandbox and file links

HomeClaw gives each user (and the Companion app when not tied to a user) a **private workspace**: a **per-user sandbox** for file access and a dedicated **output** folder for generated files. When the assistant saves a report or export, it can return a **shareable link** so you can open or download the file in a browser. No separate file server: Core serves files from the same URL you use for chat.

**Design reference:** [docs_design/FileSandboxDesign.md](../docs_design/FileSandboxDesign.md).

---

## What is the per-user sandbox?

When **`tools.file_read_base`** is set in **config/core.yml** (e.g. `D:/homeclaw` or `/home/user/homeclaw`), all file and folder tools are restricted to paths under that base:

| Path form | Resolves to | Who can access |
|-----------|-------------|----------------|
| **share/** or **share/...** | `base/share/` | All users + Companion |
| **output/...** | `base/{user_id}/output/` or `base/companion/output/` | That user or Companion only |
| Any other path | `base/{user_id}/...` or `base/companion/...` | That user or Companion only |

- **User folder:** Derived from **system_user_id** in **config/user.yml** (safe segment: alphanumeric, underscore, hyphen; max 64 chars).
- **Companion folder:** When the request is from the Companion app and **not** combined with a user, paths resolve under **base/companion/**.
- **Shared folder:** Paths starting with **share/** (or configured `file_read_shared_dir`) are visible and writable by everyone.

So: each user has a private area under **base/{user_id}/**; the Companion app has **base/companion/** when not combined. Skills, plugins, and tools that write files must use **output/<filename>** so files land in the correct user or companion output folder.

---

## Output folder and generated files

- **Reserved path:** **output/** (e.g. `output/report_123.html`, `output/summary.md`).
- **Rule:** Any feature that writes a file as a result of user or Companion interaction (reports, images, exports, summaries) must write under the current context’s **output** folder:
  - **User:** path **output/<filename>** → stored under **base/{user_id}/output/**.
  - **Companion (no user):** path **output/<filename>** → stored under **base/companion/output/**.

The assistant uses tools like **file_write** or **save_result_page** with path **output/<filename>**. No need to know the full disk path; Core resolves it per user or companion.

---

## Generate a link for the response

When the assistant saves a report or file, it can return a **link** you can open in a browser or share (time-limited, signed).

### Config (minimal for links)

In **config/core.yml** (top level):

- **`auth_api_key`** — Set to any non-empty string. Required to **sign** file links so they can be opened without sending the API key. If you use **auth_enabled** for /inbound, use the same key here.
- **`core_public_url`** — Optional. When set (e.g. `https://homeclaw.example.com`), report/file links use this URL. When **empty**, Core uses **http://127.0.0.1:<port>** so links work on the same machine. With **Pinggy** tunnel, leave empty and Core uses the tunnel URL when it’s up.
- **`tools.file_read_base`** — Must be set so the sandbox and output folders exist (e.g. `D:/homeclaw`). Files are stored under **file_read_base/<user_id>/output/** or **file_read_base/companion/output/**.

### How it works

1. **Assistant writes to output:** e.g. **save_result_page** (HTML/Markdown report) or **file_write** with path **output/<filename>**. The file is saved in your (or companion’s) output folder.
2. **Core returns a link:** e.g. `https://your-core/files/out?path=output/report_xxx.html&token=...`. The **token** is signed with **auth_api_key** and is time-limited (default 24 hours; max 7 days).
3. **You open the link:** In a browser, or “Open in app” / “Download” in the Companion app. **GET /files/out** verifies the token and serves the file (or an HTML listing if the path is a directory).

### Markdown vs HTML

- **Markdown** — Best for short or medium text (summaries, lists). The tool can return the **content** in the chat so you see it there, plus the link to open the full file.
- **HTML** — Best for long or complex reports (tables, multi-section). The assistant typically returns “Report is ready. Open: <link>”; you open the link in a browser.

### Safety

- **No path escape:** Token path and scope are validated (no `..`, no `/` in scope). Resolved path must stay under **file_read_base**.
- **Token:** Signed with **auth_api_key**; expired or invalid token returns 403.
- **Core never crashes:** File tools and **GET /files/out** return HTTP and messages on error; no uncaught exceptions.

---

## Summary

| Topic | Summary |
|-------|---------|
| **Per-user sandbox** | When **file_read_base** is set, each user has **base/{user_id}/**; Companion has **base/companion/** when not combined. **share/** is shared. |
| **Output folder** | Use path **output/<filename>** for any generated file; it goes to **base/{user_id}/output/** or **base/companion/output/**. |
| **Generate link** | Set **auth_api_key** and optionally **core_public_url**. Tools like **save_result_page** write to output and return a signed link; open it in a browser or app. |
| **Full design** | [docs_design/FileSandboxDesign.md](../docs_design/FileSandboxDesign.md) |
