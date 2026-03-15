# Intent router: categories vs tools/skills coverage

Review of whether current intent_router categories are enough to cover all tools and skills, and proposed expansions.

---

## Current setup

**Categories (from config):**  
`search_web`, `list_files`, `read_document`, `create_slides`, `schedule_remind`, `open_url`, `general_chat`, `coding`

**category_tools defined today:**

| Category        | Mapping |
|----------------|---------|
| search_web      | profile: minimal |
| list_files      | tools: [folder_list, file_find, document_read] |
| create_slides   | profile: minimal, skills: [html-slides-1.0.0, ppt-generation-1.0.0] |
| general_chat    | profile: full |
| coding          | profile: coding |
| read_document   | *(none — falls back to general_chat)* |
| schedule_remind | *(none — falls back to general_chat)* |
| open_url        | *(none — falls back to general_chat)* |

---

## Tools inventory (by function)

| Area | Tools |
|------|--------|
| **Web search / fetch** | web_search, fetch_url, tavily_extract, tavily_crawl, tavily_research, web_extract, web_crawl, web_search_browser |
| **Files & docs** | folder_list, file_find, file_read, document_read, file_understand, file_write, file_edit, apply_patch, save_result_page, get_file_view_link, markdown_to_pdf |
| **Skills** | run_skill |
| **Time / scheduling** | time, remind_me, cron_schedule, cron_list, cron_remove, cron_update, cron_run, cron_status, record_date, recorded_events_list, route_to_tam |
| **Browser** | browser_navigate, browser_snapshot, browser_click, browser_type, route_to_plugin (browser) |
| **Memory** | memory_search, memory_get, agent_memory_search, agent_memory_get, append_agent_memory, append_daily_memory, memory_task_summary, memory_skill_search, memory_skill_get, memory_task_list, memory_write_public, memory_skill_publish, memory_skill_unpublish, memory_viewer_url |
| **Knowledge base** | knowledge_base_search, knowledge_base_add, knowledge_base_remove, knowledge_base_list |
| **Profile** | profile_get, profile_list, profile_update |
| **Sessions** | sessions_list, sessions_send, sessions_spawn, sessions_transcript, session_status |
| **Messaging / channel** | channel_send |
| **System / dev** | exec, process_list, process_poll, process_kill, cwd, env, http_request, webhook_trigger |
| **Meta** | time, usage_report, models_list, agents_list, platform_info, echo |

---

## Skills inventory (by function)

| Area | Skills (folders) |
|------|------------------|
| **Slides / docs** | html-slides-1.0.0, ppt-generation-1.0.0, summarize-1.0.0 |
| **Search** | baidu-search-1.1.0 |
| **Weather** | weather-1.0.0 |
| **Image** | image-generation-1.0.0 |
| **API / automation** | maton-api-gateway-1.0.0, x-api-1.0.0 |
| **Social / content** | meta-social-1.0.0, linkedin-writer-1.0.0, social-media-agent-1.0.0, hootsuite-1.0.0 |
| **Other** | answeroverflow-1.0.2, ip-cameras, desktop-ui, gog-1.0.0, openai-whisper-1.0.0, apple-notes-1.0.0 |

---

## Gaps

1. **Categories with no mapping**  
   `read_document`, `schedule_remind`, `open_url` are in the list but have no `category_tools` (and no `skills`). Router can still classify to them, but tool/skill set stays “full” (or profile) instead of a focused set.

2. **Tools with no dedicated category**  
   - Memory (search, append, agent memory, etc.)  
   - Knowledge base  
   - Profile  
   - Sessions  
   - Image (vision)  
   - Browser automation (screenshot, click, type beyond “open URL”)  
   - Messaging (channel_send)  
   - Markdown/PDF (markdown_to_pdf, save_result_page)  
   All of these today only get a focused set if the router picks `general_chat` and you use profile “full”, or you add more categories.

3. **Skills with no dedicated category**  
   - Search (baidu-search) — could map to search_web + skill.  
   - Weather, image-generation, summarize — no specific category.  
   - Social (linkedin, meta-social, hootsuite, etc.) — no “social” or “post” category.  
   - API/automation, notes, whisper, etc. — only covered by general_chat + full skills.

4. **Overlap / boundaries**  
   - `list_files` includes `document_read`; “read this PDF” could be read_document or list_files depending on intent.  
   - `open_url` vs browser (navigate vs snapshot/click) — one category for “open URL” and optionally one for “browser automation”.

---

## Recommendation: is the intent_router enough?

**Yes, if we:**

1. **Add mappings for existing categories** so every category in the list has a defined tool (and optionally skill) set.
2. **Add a small set of extra categories** for the main tool/skill clusters that are currently only in “general”.
3. **Keep `general_chat`** for everything that doesn’t fit a narrow intent (profile: full or a broad profile).

Suggested next steps:

- **A. Minimal (enough for current list)**  
  - Add only `category_tools` (and skills where useful) for:  
    `read_document`, `schedule_remind`, `open_url`.  
  - Leave the rest to `general_chat` + full profile.

- **B. Recommended (good coverage)**  
  - Add mappings for `read_document`, `schedule_remind`, `open_url` (as below).  
  - Add categories (and mappings) for:  
    `memory`, `knowledge_base`, `schedule_remind` (already in list), `open_url` (already in list), and optionally `image`, `browser_automation`, `social_post`.  
  - Optionally add one “narrow” category for social skills (e.g. `social_post` → run_skill + channel_send + specific skills).

- **C. Max coverage**  
  - Add more granular categories (e.g. profile, sessions, system_info) and map each to a small allowlist so the model almost always gets a small, relevant set.

Below we only spell out **recommended (B)** so the intent_router is “enough” for most tools and skills without exploding the number of categories.

---

## Proposed category_tools (and skills) for full coverage

```yaml
categories:
  - search_web
  - list_files
  - read_document
  - create_slides
  - schedule_remind
  - open_url
  - memory
  - knowledge_base
  - image
  - general_chat
  - coding

category_tools:
  search_web:
    profile: minimal   # or tools: [web_search, fetch_url]
  list_files:
    tools: [folder_list, file_find, document_read]
  read_document:
    tools: [document_read, file_read, file_understand, folder_list, file_find]
  create_slides:
    profile: minimal
    skills: [html-slides-1.0.0, ppt-generation-1.0.0]
  schedule_remind:
    tools: [remind_me, cron_schedule, cron_list, cron_remove, cron_update, record_date, recorded_events_list, route_to_tam, time]
  open_url:
    tools: [fetch_url, route_to_plugin, browser_navigate]
    # route_to_plugin for in-app browser; browser_navigate if built-in
  memory:
    tools: [memory_search, memory_get, agent_memory_search, agent_memory_get, append_agent_memory, append_daily_memory]
  knowledge_base:
    tools: [knowledge_base_search, knowledge_base_add, knowledge_base_remove, knowledge_base_list]
  image:
    tools: [image]
    skills: [image-generation-1.0.0]
  general_chat:
    profile: full
  coding:
    profile: coding
```

Optional extra categories (if you want even narrower routing):

- **browser_automation**: tools: [browser_snapshot, browser_click, browser_type, route_to_plugin]
- **social_post**: tools: [run_skill, channel_send]; skills: [linkedin-writer-1.0.0, meta-social-1.0.0, social-media-agent-1.0.0, hootsuite-1.0.0]
- **profile**: tools: [profile_get, profile_list, profile_update]
- **sessions**: tools: [sessions_list, sessions_send, sessions_spawn, sessions_transcript, session_status]

---

## Summary

- **Current state:** Intent router is *not* quite enough: three categories have no mapping, and several tool/skill areas (memory, KB, image, scheduling, open_url, read_document) have no or weak dedicated category.
- **With the proposed mappings and a few extra categories (memory, knowledge_base, image, and the three missing mappings), the intent_router is enough** for most tools and skills; the rest can stay under `general_chat` (profile full) or under `coding` where appropriate.

If you want, the next step is to add the recommended `category_tools` (and optional `skills`) to `skills_and_plugins.yml` and, if you choose, the optional categories (browser_automation, social_post, profile, sessions).

---

## Multi-category tasks (tasks that need tools from several categories)

**Problem:** The router returns **one** category. If the user’s task needs tools from **several** categories (e.g. “search the web for X and save the result to a file” → needs `search_web` + file tools), a single category would filter out needed tools.

**Options:**

1. **Union of multiple categories**  
   Allow the router to return **comma-separated** categories (e.g. `search_web, list_files`). Core parses this into a list and **merges** tool/skill sets: tools = union of tools from each category; skills = union of skills from each category. So “search and save” can be classified as `search_web, general_chat` or `search_web, list_files` and the LLM gets both search + file tools.  
   - **Implementation:** Router prompt can say: “If the request clearly needs multiple types of actions (e.g. search then save, read then create slides), reply with the two most relevant category names separated by a comma, e.g. search_web, list_files.” Parse the response in Core; if multiple categories, use `get_tools_filter_for_categories` / `get_skills_filter_for_categories` to merge (union).  
   - **Merging rules:** If any category has `profile: full` → no tool filter (full tools). Otherwise: for each category, resolve to tool names (from profile via TOOL_PROFILES or from explicit `tools` list); take the **union**. Skills: union of each category’s `skills` list (categories with no `skills` add nothing to the union).

2. **Always include a baseline set**  
   In config, define `tools_always_included` (e.g. `file_write`, `save_result_page`) that are **added to every category’s** tool set. So `search_web` would get minimal profile **plus** baseline tools; “search and save” works without multi-category.  
   - Simpler (config-only), but baseline can grow and bloat narrow intents.

3. **Fallback to general_chat for complex queries**  
   Router prompt: “If the request clearly requires multiple distinct actions (e.g. search then save, read doc then make slides), reply with general_chat.” So multi-step tasks get full tools.  
   - Easiest, but many requests would get `general_chat` and full tool set.

**Chosen approach:** **Option 1 (union of multiple categories)** so that:
- The router can return e.g. `search_web, list_files` or `read_document, create_slides`.
- Core parses comma-separated categories, normalizes to a list, and uses merged tools/skills (union).
- Single-category response (e.g. `search_web`) continues to work as today (one category → one filter).
- No change to config schema: existing `category_tools` and `skills` per category are reused; merging is in code.

---

## Fallbacks when tools/categories are not selected at the start

If a needed tool or skill is **not** in the set chosen at the start of the turn (by the intent router + category_tools/skills), the LLM **cannot** select it later — it is simply not in the prompt. Fallbacks reduce under-selection or recover when the router fails.

| Fallback | Status | What it does |
|----------|--------|----------------|
| **Router failure → general_chat** | In place | On parse failure, timeout, or any exception, `route()` returns `"general_chat"`. `general_chat` uses `profile: full`, so the LLM gets **all tools**. |
| **Multi-category** | In place | Router can return two comma-separated categories; Core takes the **union** of tools and skills. |
| **tools_always_included** | Optional (config) | In `intent_router` set `tools_always_included: [file_write, save_result_page, ...]`. These tools are **added to every category’s** set so narrow categories still get e.g. save. |
| **Router prompt: “when uncertain use general_chat”** | Optional | Add to router prompt: “If the request is ambiguous or could need many tools, reply with general_chat.” |
| **Mid-turn re-route** | Not implemented | Re-running the router after the first tool round to expand tools would allow a second chance; not implemented. |

**Recommendation:** Use **router failure → general_chat** and **multi-category** first. If narrow categories still miss common tools (e.g. “search then save”), add **tools_always_included** (e.g. `save_result_page`, `file_write`, `folder_list`).
