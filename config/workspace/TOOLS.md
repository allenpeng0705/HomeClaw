# Tools / capabilities (optional)

A **human-readable list of capabilities** the assistant can use. This is injected into the **system prompt** under `## Tools / capabilities` so the model knows what it can refer to (e.g. “I can look up past context” or “I can use the Weather plugin when you ask”).

---

## How the system prompt uses this

- **Where it’s injected**: Same flow as IDENTITY.md and AGENTS.md — `core/core.py` → `answer_from_memory()` → `system_parts`; `base/workspace.py` → `build_workspace_system_prefix()` adds `## Tools / capabilities` + this file’s content. Order in system message: Identity → Agents → **Tools** → then the RAG response template (with “Here is the given context: …”).
- **Purpose**: Describe capabilities in plain language. The model does not execute tools from this file; it only uses the description to answer “what can you do?” and to phrase replies (e.g. “I can use recalled memories to answer that”).

---

## Examples (pick one or mix)

**Minimal:**
- **Chat and memory**: You can use recent chat history and recalled memories (RAG) to answer. When the user refers to something from the past, use the provided context.
- **Plugins** (if orchestrator is on): Weather, News, etc. The system routes by intent; you don’t “call” them—just answer or acknowledge and the system may run the right plugin.

**More detailed:**
- **Conversation**: You have access to the current conversation and the last several turns.
- **Memory (RAG)**: You receive relevant past snippets (memories) in the system context. Use them to answer questions about the user’s preferences, facts they shared, or past events. Don’t invent; if context doesn’t contain it, say you don’t have that information.
- **Plugins**: When enabled, the system can run plugins (e.g. Weather, News). You don’t execute them yourself; when the user asks for something that fits a plugin, the system may route there. You can list these as “I can help with …” when the user asks what you can do.

**Short “what you can do” style:**
- Recall: use provided memories and chat history to answer.
- Plugins (when on): weather, news, etc.; system routes by intent.

**When the tool layer is enabled (use_tools: true in config):**  
You can call tools by name with arguments. **When the user asks you to read, summarize, or list files on their device, use file_read and folder_list** — you are explicitly authorized to access files under the configured base path; do not refuse or suggest cloud upload. **Time / cron**: **time**, **remind_me** (one-shot: minutes or at_time + message), **record_date** (record event: event_name + when, e.g. 'Spring Festival is in two weeks'), **recorded_events_list**, **cron_schedule**, **cron_list**, **cron_remove**. **Sessions**: **sessions_transcript**, **sessions_list**, **sessions_send** (send message to another session, get reply), **sessions_spawn** (sub-agent one-off run; select model by **llm_name** (ref from models_list) or **capability** (e.g. Chat — from each LLM’s capabilities in config); omit both to use main_llm), **session_status**. **Memory**: **memory_search**, **memory_get** (RAG when use_memory is on). **Files**: **file_read**, **document_read** (PDF, PPT, Word, MD, HTML, XML, JSON, etc.; uses Unstructured when installed; long files: increase max_chars or section-by-section), **file_write**, **file_edit** (old_string/new_string), **apply_patch** (unified diff), **folder_list**, **file_find** (find by glob, e.g. *.py). **Web**: **fetch_url** (prefer for reading pages; no Chromium), **web_search** (search the web for news, current events, or any lookup). **When the user asks you to search the web or look something up online (e.g. 上网查一下, “search for X”), use web_search** — you are authorized to do so; do not refuse or say you cannot access the internet. **Browser** (optional; only if Playwright installed): **browser_navigate**, **browser_snapshot**, **browser_click**, **browser_type**. **System**: **exec** (allowlisted; **background** for job_id), **process_list**, **process_poll**, **process_kill** (background exec jobs). **Multimodal**: **image** (path or url + prompt; vision-capable LLM required). **API**: **http_request** (GET/POST/PUT/PATCH/DELETE, optional headers; for REST), **webhook_trigger** (POST only). **Other**: **channel_send** (send an additional message to the channel that last sent a request — multiple continuous messages to one channel), **run_skill** (run a script from a loaded skill's scripts/ folder; skill_name + script under skill's scripts/; optional args), **models_list** (list models with ref, alias, capabilities from config; use ref as llm_name or capability e.g. Chat in sessions_spawn to select by capability), **agents_list**. **Reports**: **save_result_page** — Prefer **storing directly**: when your response is long or structured, call save_result_page with the full content and reply with only the link (or full content in chat if no link). If you ask the user first and they say yes, pass the **exact same content** you already showed (do not regenerate or shorten). For text-only use **format=markdown**; use html for tables. If no link (base_url not set): send the full result in chat. Design: docs/ToolsDesign.md. Per-tool timeout prevents hang. Mac/Linux and cross-platform where possible.

Leave this file empty or delete it to skip the Tools block in the system prompt.
