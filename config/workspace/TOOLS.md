# Tools / capabilities (optional)

This file is **not** used to select which tools are available. Tool selection is done by the **intent router** (categories) and config (`skills_and_plugins.yml`, tool profiles, `tools_always_included`) in Core. The content below is **narrative only**: it is injected into the system prompt under `## Tools / capabilities` so the model can describe what it can do (e.g. when the user asks “what can you do?”) and follow behavioral hints.

- **Which tools you have this turn** may be filtered by the user’s intent. Only refer to or call tools that are actually in your tool list for this request; do not claim capabilities you don’t have this turn.
- **Chat and memory**: You can use recent chat history and recalled memories (RAG) when provided. Use them to answer; say when you’re unsure.
- **Files**: **file_read**, **document_read** (PDF, Word, MD, HTML, etc.), **file_write**, **file_edit**, **folder_list**, **file_find**. You are authorized to access files under the configured base path; use these tools when the user asks to read, summarize, or list files — do not refuse or ask them to paste content.
- **Web**: **web_search** for search/lookup (e.g. 上网查一下, “search for X”). **fetch_url** for reading a page. Use web_search when the user asks to search; do not refuse.
- **Reports and long output**: **save_result_page** — when your response is long or structured (report, slides), call save_result_page with the content and reply with the link. For **very long HTML** (e.g. slide decks): do **not** put the full HTML in the tool’s `content` argument (it can be truncated). Put the full HTML in your **message content** inside a ` ```html ... ``` ` block, then call save_result_page with a short label and `format='html'`; the system will save from the block and return the link. For text-only reports use **format=markdown**; for HTML slides use **format=html**. **markdown_to_pdf**: use to convert a Markdown file to PDF (e.g. path to .md file → PDF and return the link).
- **Skills**: **run_skill** — run a script from a skill (e.g. html-slides, ppt-generation, email). For instruction-only skills (no script), call run_skill(skill_name) then continue in the same turn (e.g. document_read → generate content → save_result_page).
- **Time / reminders**: **time**, **remind_me**, **record_date**, **recorded_events_list**, **cron_schedule**, **cron_list**, **cron_remove**.
- **Sessions**: **sessions_transcript**, **sessions_list**, **sessions_send**, **sessions_spawn**, **session_status**.
- **Other**: **channel_send**, **run_skill**, **models_list**, **agents_list**, **route_to_plugin** (when plugins are enabled), **get_file_view_link**, **image** (vision), **exec** (allowlisted), **http_request**, **webhook_trigger**.

---

## How the system prompt uses this

- **Where it’s injected**: `core/core.py` → `answer_from_memory()` → `system_parts`; `base/workspace.py` → `build_workspace_system_prefix()` adds `## Tools / capabilities` + this file’s content. Order: Identity → Agents → **Tools** → RAG response template.
- **Purpose**: Narrative description and behavioral hints. The actual tool definitions (names, parameters) sent to the model come from Core’s tool registry and intent-based filtering, not from this file.

To change what the assistant says about capabilities or how it should use tools, edit the bullet list above.
