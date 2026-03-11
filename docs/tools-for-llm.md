# Tools for LLM Selection

This document lists all **built-in tools** with their **name** and **description** as exposed to the LLM for tool selection. Plugin tools (via `route_to_plugin`) are added at runtime from plugin config.

---

## Routing & plugins

| Tool | Description |
|------|-------------|
| **route_to_tam** | Route to TAM (time/scheduling) when time-related and too complex for remind_me/record_date/cron_schedule. Prefer: remind_me (one-shot), record_date (record event), cron_schedule (recurring) to avoid a second LLM parse. |
| **route_to_plugin** | Route this request to a specific plugin by plugin_id. Use when the user intent clearly matches one of the available plugins. You MUST call this tool (do not just reply 'I need some time' or 'working on it') — the user gets the result only when the plugin runs and returns. For PPT/slides/presentation use run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=[...]) instead. For homeclaw-browser pass capability_id and parameters (e.g. node_id, url) when the user asks for photo, video, or browser. |

---

## Browser (Playwright)

| Tool | Description |
|------|-------------|
| **browser_navigate** | Open a URL in the shared browser session and return the page text. Use only when you need to click or type on the page; for reading content prefer fetch_url (no Chromium). Use browser_snapshot next for clickable elements, then browser_click or browser_type. |
| **browser_snapshot** | Get interactive elements (buttons, links, inputs) on the current page with selectors. Use these selectors with browser_click or browser_type. Requires an open page (call browser_navigate first). |
| **browser_click** | Click an element on the current page. Use selector from browser_snapshot. |
| **browser_type** | Type text into an input or textarea on the current page. Use selector from browser_snapshot. Clears the field first. |
| **web_search_browser** | Search Google, Bing, or Baidu using the browser (no API key). Use when you want Google/Bing/Baidu results and have no API key. Fragile: may break on CAPTCHA or HTML changes. Prefer web_search with provider duckduckgo (no key) or google_cse/bing (free tier) when possible. |

---

## Sessions & channel

| Tool | Description |
|------|-------------|
| **sessions_transcript** | Get the conversation transcript for the current session (or a given session_id). Returns a list of messages with role, content, and timestamp. |
| **sessions_list** | List chat sessions for the current app/user. Returns session_id, app_id, user_name, user_id, created_at. |
| **sessions_send** | Send a message to another session and get that session's agent reply. Use session_id (from sessions_list) or app_id + user_id to target. Returns the reply from the target session. |
| **sessions_spawn** | Sub-agent run: run a one-off task and get the model reply. Select model by llm_name (ref from models_list) or capability (e.g. 'Chat' — selects a model that has that capability in config). Omit both to use main_llm. |
| **channel_send** | Send an additional message to the channel that last sent a request (same conversation channel). Use when you want to send more than one continuous message to the user in that channel. Works with full channels (async delivery); for sync /inbound the client only gets one response per request. |
| **usage_report** | Get the current usage report: hybrid router stats (mix mode) and cloud model request counts. Use when the user asks for cost, usage, or how many requests went to cloud vs local. Returns summary and by-layer breakdown. |

---

## Skills & time

| Tool | Description |
|------|-------------|
| **run_skill** | Run a script from a skill's scripts/ folder, or confirm an instruction-only skill. Use when a skill has a scripts/ directory: pass skill_name and script (e.g. run.sh, main.py). For instruction-only skills (no scripts/): call run_skill(skill_name=<name>) with no script; the tool will confirm the skill—then you MUST continue in the same turn: follow the skill's steps (e.g. document_read, generate content, file_write or save_result_page to output/ or {FriendName}/output/) and return the link to the user. Do not reply with only the confirmation message. skill_name can be folder name (e.g. html-slides-1.0.0) or short name (html-slides, html slides). |
| **time** | Get current date and time (system local, ISO format). Use when you need precise current time for age calculation, 'what day is it?', or scheduling. Returns same timezone as the system context injected in the prompt. |

---

## Scheduling & reminders (cron, remind, record)

| Tool | Description |
|------|-------------|
| **cron_schedule** | RECURRING only: 'every N hours', 'daily at 9am', '每天早上', 'every 10 minutes'. For ONE-SHOT ('in 5 minutes', 'remind me at 9am once') use remind_me instead. Schedule a reminder, skill, plugin, or tool at cron times. cron_expr: 5 fields (minute hour day month weekday), e.g. '0 7 * * *' = daily at 7:00. task_type 'message' (default): send a fixed message. 'run_tool'/'run_skill'/'run_plugin' for periodic tasks. Optional: tz, delivery_target. |
| **cron_list** | List all recurring (cron) reminders: job_id, message, cron_expr, next_run, enabled, last_run_at, last_status, delivery_target. Use so the user can see their recurring reminders and choose which to remove or disable (cron_remove, cron_update). |
| **cron_remove** | Remove a recurring (cron) reminder by job_id. Get job_id from cron_list (user can say which to remove by message, e.g. 'the 9am pills reminder'). |
| **cron_update** | Enable or disable a cron job by job_id. Get job_id from cron_list. Use enabled=false to pause, enabled=true to resume. |
| **cron_run** | Run a cron job once immediately (force run). Use cron_list to get job_ids. |
| **cron_status** | Return cron scheduler status: scheduler_enabled, next_wake_at, jobs_count. For UI or debugging. |
| **remind_me** | Schedule a ONE-SHOT reminder (single notification). USE THIS when the user says: 'remind me in N minutes', 'N分钟后提醒我', 'in 10 min tell me', '提醒我5分钟后', 'remind me at 9am', '明天早上提醒我', or any single future time. Supply minutes (integer, e.g. 5 for 'in 5 minutes') OR at_time (YYYY-MM-DD HH:MM:SS). message = short label only (e.g. '喝水', 'meeting'); do NOT put date/time in message. Do NOT use for: recurring (every day/N hours) -> use cron_schedule; recording an event -> use record_date. |
| **record_date** | Record a date/event for future reference. Use for: 'Tomorrow is national holiday', 'Girlfriend birthday in two weeks'. Optional inference: if user may want a reminder, pass event_date (YYYY-MM-DD, compute from 'when') and remind_on ('day_before' or 'on_day') to schedule a reminder; remind_message overrides default text. |
| **recorded_events_list** | List recorded dates/events (from record_date). Use when user asks 'what is coming up?' or 'what did I record?'. |

---

## Session & profile

| Tool | Description |
|------|-------------|
| **session_status** | Get current session info: session_id, app_id, user_name, user_id. |
| **profile_get** | Get the current user's stored profile (learned facts: name, birthday, preferences, families, etc.). Returns specific keys if 'keys' is provided (comma-separated). Per-user. |
| **profile_update** | Update the current user's profile with facts they told you (e.g. name, birthday, favorite_foods, families, dietary restrictions). Use when the user says 'my name is X', 'remember I like Y', 'I'm allergic to Z', etc. Pass updates as key-value pairs. Use remove_keys to forget specific keys. Per-user. |
| **profile_list** | List what we know about the current user (profile keys and a short preview). Use when the user asks 'what do you know about me?' or to show stored facts. Per-user. |

---

## Memory (RAG, agent memory, daily memory)

| Tool | Description |
|------|-------------|
| **memory_search** | Search stored memories (RAG). Returns relevant past snippets. Use when user asks what we remember or to recall context. Only works when use_memory is enabled. |
| **memory_get** | Get a single memory by id (from memory_search results). Only works when use_memory is enabled. |
| **append_agent_memory** | Append a note to the curated long-term memory file (AGENT_MEMORY.md). Use when the user says 'remember this' or to store important facts/preferences. This file is authoritative over RAG when both mention the same fact. Only works when use_agent_memory_file is true in config. |
| **append_daily_memory** | Append a note to today's daily memory file (memory/YYYY-MM-DD.md). Use for short-term notes that help avoid filling the context window; loaded as 'Recent (daily memory)' together with yesterday's file. Only works when use_daily_memory is true in config. |
| **agent_memory_search** | Semantically search AGENT_MEMORY.md and daily memory (memory/YYYY-MM-DD.md). Use before agent_memory_get to pull only relevant parts. Returns path, start_line, end_line, snippet, score. Only works when use_agent_memory_search is true in config. |
| **agent_memory_get** | Read a snippet from AGENT_MEMORY.md or memory/YYYY-MM-DD.md by path. Use after agent_memory_search to load only the needed lines. path: e.g. AGENT_MEMORY.md or memory/2025-02-16.md; optional from_line and lines for a range. Only works when use_agent_memory_search is true in config. |

---

## Web search & Tavily

| Tool | Description |
|------|-------------|
| **web_search** | Search the web (generic). Use for 'search the web', 'search for X', 'search the latest sports news'. For 'search the latest sports news every 7 am' use cron_schedule with task_type=run_tool, tool_name=web_search, tool_arguments={query: 'latest sports news', count: 10} — do NOT use run_plugin headlines. Free (no key): duckduckgo. Free tier: google_cse, bing, tavily. Set provider in config; pass search_type for Brave, engine for SerpAPI. |
| **tavily_extract** | Extract content from one or more URLs using Tavily Extract. Use when the user wants to read or summarize specific web pages (by URL). Requires TAVILY_API_KEY or tools.web.search.tavily.api_key (same as web_search). |
| **tavily_crawl** | Crawl a website from a base URL using Tavily Crawl. Use when the user wants to explore or map a site (e.g. 'crawl this docs site'). Requires TAVILY_API_KEY or tools.web.search.tavily.api_key. |
| **tavily_research** | Run a deep research task on a topic using Tavily Research. Use when the user wants a comprehensive report (e.g. 'research X', 'write a report on Y'). Creates a task and polls until done; returns content and sources. Requires TAVILY_API_KEY or tools.web.search.tavily.api_key. |

---

## Models, agents, image, debug

| Tool | Description |
|------|-------------|
| **models_list** | List available model refs and main_llm. For sessions_spawn: omit llm_name to use main_llm; to use a different model pass one ref from the list — prefer a smaller/faster one (e.g. 7B in the id) for quick sub-tasks. |
| **agents_list** | List agent ids. In HomeClaw returns single-agent note. |
| **image** | Analyze an image with the vision/multimodal model. Provide image as path (relative to homeclaw_root) or url, and optional prompt (e.g. 'What is in this image?'). Requires a vision-capable LLM. |
| **echo** | Echo back the given text. Useful for testing. |
| **platform_info** | Get platform info: Python version, system (Darwin/Linux/Windows), machine. |
| **cwd** | Get current working directory of the Core process. |
| **env** | Get the value of an environment variable (read-only). |

---

## Process (exec, background jobs)

| Tool | Description |
|------|-------------|
| **exec** | Run a shell command. Only commands in the allowlist (config: tools.exec_allowlist) are allowed. Set background=true to run in background and get job_id; use process_list/process_poll/process_kill with that job_id. |
| **process_list** | List background exec jobs (job_id, command, started_at, status). Use after exec with background=true. |
| **process_poll** | Poll a background job: get output and returncode when done, or status running. Use job_id from exec(background=true) or process_list. |
| **process_kill** | Kill a background job by job_id. |

---

## File & document (sandbox)

| Tool | Description |
|------|-------------|
| **file_read** | Read contents of a file. Paths relative to user sandbox. When path not given: use user sandbox root or infer (e.g. 'my documents' → documents/). When user mentions a friend: use path '{FriendName}/...'. When user says 'share' or 'shared folder (for all users)': use path 'share' or 'share/...' to access the global share (homeclaw_root/share/). User sandbox: downloads/, documents/, output/, work/, share/, knowledge/; per friend: {FriendName}/output/, {FriendName}/knowledge/. |
| **document_read** | Read document content from PDF, PPT, Word, MD, HTML, XML, JSON, Excel, and more. When the user wants to summarize, edit, or use a file but does not give a path: pass the file name or a short description (e.g. 'resume', 'Allen_Peng_resume_en.docx') as path — the tool will search the sandbox first and read the file if exactly one match. When path is a full path: use the **path** from folder_list or file_find. User sandbox: documents/, output/, work/, share/, etc. Use 'share/...' for global share. For long files, increase max_chars. |
| **file_understand** | Classify a file as image, audio, video, or document and return type + path. When path not given: use user sandbox root or infer. When user mentions a friend, use path '{FriendName}/...'. User sandbox: downloads/, documents/, output/, work/, share/, knowledge/; per friend: {FriendName}/output/, {FriendName}/knowledge/. Use 'share/...' for global share. For images, use image_analyze(path) if user asks to describe. |
| **file_write** | Write content to a file. When path not given: use user sandbox root, or infer (e.g. 'save to my output' → output/). When user mentions a friend (e.g. 'save for Sabrina'), use path '{FriendName}/output/...'. User sandbox: downloads/, documents/, output/, work/, share/, knowledge/; per friend: {FriendName}/output/, {FriendName}/knowledge/. Use 'share/...' only when user says share folder. |
| **file_edit** | Replace old_string with new_string in a file. When path not given: use user sandbox root or infer. When user mentions a friend, use path '{FriendName}/...' or '{FriendName}/output/...'. User sandbox: downloads/, documents/, output/, work/, share/, knowledge/; per friend: {FriendName}/output/. Use 'share/...' for global share. Use replace_all=true to replace all occurrences. |
| **apply_patch** | Apply a unified diff patch to a file. Patch should be a single-file unified diff (---/+++ and @@ hunks). Path in patch is relative to user sandbox (e.g. output/file.txt, documents/readme.md); use 'share/...' when user says share folder. Provide patch or content. |
| **folder_list** | List one level of a directory (subfolders and files). Use when the user asks for **folder structure** or **what folders/directories exist** (e.g. 'what folders are in my sandbox'). When the user asks for a **named folder** (e.g. 'what files in documents folder', 'list documents', 'files in my documents'): pass path='documents' (or the folder they said: documents, downloads, output, images, work, knowledge, share) — do NOT omit path or use '.' or you will list the sandbox root. When path not given: lists user sandbox root. User sandbox: downloads/, documents/, output/, work/, share/, knowledge/; per friend: {FriendName}/. Use path 'share' for global share. Returned 'path' is the exact path to pass to document_read/file_read. |
| **file_find** | Find or list files by name pattern (glob). Use when the user asks to **list files**, **list images**, **search for files**, or **list all images** — use path (e.g. 'images') and pattern (e.g. '*' or '*.png'), and set files_only=true to return only files (not folders). Use folder_list when they ask for **folder structure** or **what folders exist**. When path not given: search user sandbox root. User sandbox: downloads/, documents/, output/, images/, work/, share/, knowledge/. Use path 'share' for global share. Use the **exact path** from the result in document_read. |

---

## Web fetch & crawl (no browser)

| Tool | Description |
|------|-------------|
| **fetch_url** | Fetch a URL and return the page content as plain text (HTML stripped). Prefer this for reading web pages; no Chromium or JavaScript. Use web_search for search. Use browser_navigate only when you need to click or type on the page (requires Playwright). |
| **web_extract** | Extract main content from one or more URLs using free Python libs (trafilatura or BeautifulSoup). No API key. Use when you have specific URLs to read or summarize. Prefer over fetch_url for article-style pages. Optional: pip install trafilatura (better) or beautifulsoup4. |
| **web_crawl** | Crawl from a start URL: fetch pages, follow links up to max_pages and max_depth. Free; no API key. Uses same extract as web_extract. Use when the user wants to explore or map a site. same_domain_only=true (default) limits to same domain. |

---

## HTTP & webhook

| Tool | Description |
|------|-------------|
| **http_request** | Send an HTTP request (GET, POST, PUT, PATCH, DELETE). Use for REST APIs: read data (GET), create/update (POST/PUT/PATCH), delete (DELETE). Optional headers (e.g. Authorization: Bearer <token>). |
| **webhook_trigger** | Send an HTTP POST request to a URL (webhook). Optional JSON body. For full REST (GET/PUT/DELETE, headers) use http_request. |

---

## Knowledge base

| Tool | Description |
|------|-------------|
| **knowledge_base_search** | Search the user's personal knowledge base (saved documents, web snippets, URLs). Use when the user asks about something they may have saved earlier. Returns relevant chunks; only available when knowledge base is enabled. |
| **knowledge_base_add** | Add content to the user's knowledge base. Only use when the user explicitly asks to save or remember this content (e.g. 'add this to my knowledge base', 'save this for later'). Do not auto-add every document_read or web result. Provide source_type (e.g. document, web, url) and optional source_id to remove or update later. |
| **knowledge_base_remove** | Remove all entries for a given source from the user's knowledge base. Use source_id that was used when adding (e.g. file path or URL). |
| **knowledge_base_list** | List documents/sources saved in the user's knowledge base, or check if a specific document is saved. Use when the user asks 'was this saved?', 'what do I have in my knowledge base?', or 'is this document in my KB?'. Pass source_id to check a specific document (e.g. file path or URL used when adding). |

---

## Output & sharing

| Tool | Description |
|------|-------------|
| **save_result_page** | Save the result as a page and get a shareable link. **format=markdown:** Saves as .md; the tool returns the content so the companion app can display it directly in chat (include the returned content in your reply). **format=html:** Saves as .html; the tool returns only the link—share that link with the user so they can open the page in a browser. For html slide requests use format='html' and full HTML content. Link when auth_api_key is set. |
| **get_file_view_link** | Get a view/download link for any file in the user sandbox or share. Use when the user asks to send or get a file (e.g. 'send me that file', '发给我 ID1.jpg'). Pass the **path** value from folder_list/file_find (not the name). For images, the image is also sent inline. Reply with only the URL from this tool. |
| **markdown_to_pdf** | Convert Markdown content to a PDF file and save it. Use when the user or a skill produces long Markdown (e.g. a summary or report) and you want to give them a downloadable PDF. Pass the Markdown as content and a path under output/ (e.g. output/summary.pdf). Returns the file link so you can include it in your reply. Prefer VMPrint when configured (config: tools.markdown_to_pdf.vmprint_dir to path of github.com/cosmiciron/vmprint clone); else uses pandoc or pip install markdown weasyprint. |

---

## Note

- **Plugin tools** are not listed here; they are exposed via **route_to_plugin** with `plugin_id` and optional `capability_id`/`parameters`. The list of available plugins and their descriptions is injected into the system prompt at runtime.
- Tool **parameters** (JSON schema) are sent to the LLM in the same structure as in `tools/builtin.py`; this doc only lists name and description for quick reference.
