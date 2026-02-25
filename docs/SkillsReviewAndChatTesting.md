# Skills review and how to test them via chat

Summary of bundled skills and example chat prompts to test each one. Ensure **use_skills: true** and **skills_dir** (e.g. `skills`) in `config/core.yml`; optionally **skills_use_vector_search: true** so the model retrieves skills by query.

---

## Instruction-only skills (no scripts/)

The model uses the skill’s instructions from SKILL.md to guide its response. No `run_skill` script is required; just ask in natural language.

| Skill folder | Name | What it does | How to test in chat |
|--------------|------|--------------|---------------------|
| **linkedin-writer-1.0.0** | LinkedIn Writer | Writes LinkedIn posts that sound human (story, list, lesson, etc.). | “Write a LinkedIn post about [topic]” or “Draft a short LinkedIn post about learning from failure.” |
| **summarize-1.0.0** | summarize | Summarize URLs, PDFs, images, audio, YouTube via `summarize` CLI. | “Summarize https://example.com” or “Summarize this YouTube link: [url].” (Requires `summarize` CLI + API key.) |
| **weather-1.0.0** | weather | Get weather via wttr.in or Open-Meteo (no API key). | “What’s the weather in London?” or “Weather in New York?” |
| **example** | example | Minimal example skill (format only). | “Use the example skill” — model may refer to it or say it’s a demo. |
| **ppt-generator-1.0.0** | ppt-generator | Turn a script into a Jobs-style minimal HTML slides (Chinese-oriented). | “把这段讲稿生成乔布斯风竖屏PPT” or “Generate a minimal tech-style slide deck from this script: [paste].” |
| **file-search-1.0.0** | file-search | Fast file/content search with `fd` and `rg` (ripgrep). | “Find all .py files under my project” or “Search for ‘TODO’ in src/.” (Requires `fd`, `rg`.) |
| **notion-1.0.0** | notion | Notion API: pages, databases, blocks. | “Search my Notion for [query]” or “Create a Notion page titled X.” (Requires Notion integration + API key.) |
| **trello-1.0.0** | trello | Trello API: boards, lists, cards. | “List my Trello boards” or “Add a card to list X.” (Requires TRELLO_API_KEY, TRELLO_TOKEN.) |
| **outlook-api-1.0.3** | outlook | Outlook/Microsoft Graph: email, calendar, contacts. | “Check my Outlook inbox” or “Send an email to X.” (Requires MATON_API_KEY / OAuth.) |
| **apple-notes-1.0.0** | apple-notes | Apple Notes via `memo` CLI (macOS only). | “Add a note: buy milk” or “List my notes.” (macOS + `memo`.) |
| **gog-1.0.0** | gog | Google Workspace CLI: Gmail, Calendar, Drive, Sheets, Docs. | “Search my Gmail for X” or “List my calendar events.” (Requires `gog` + OAuth.) |
| **openai-whisper-1.0.0** | openai-whisper | Local speech-to-text with Whisper CLI. | “Transcribe this audio file: /path/to/audio.mp3.” (Requires `whisper` CLI.) |
| **answeroverflow-1.0.2** | answeroverflow | Search indexed Discord discussions (Answer Overflow). | “Search Answer Overflow for [topic]” or “Find Discord discussions about Prisma.” |
| **social-media-agent-1.0.0** | social-media-agent | Autonomous X/Twitter management with browser + cron + memory. | “Post a tweet about X” or “Schedule a tweet for tomorrow.” (Uses browser + tools; no API key.) |

---

## Script-based skills (have `scripts/`)

The model can call **run_skill(skill_name, script, args)**. Use the folder name as `skill_name` and the script filename (e.g. `run.py`, `search.py`) as `script`.

| Skill folder | Name | Script | What it does | How to test in chat |
|--------------|------|--------|--------------|---------------------|
| **baidu-search-1.1.0** | baidu-search | search.py | Baidu AI Search (BDSE). | “用百度搜索 [query]” or “Search Baidu for [topic].” (Requires BAIDU_API_KEY.) |
| **image-generation-1.0.0** | image-generation | generate_image.py | Image generation/editing with Gemini 3 Pro Image. | “Generate an image of [description]” or “Edit this image: [path] to add [change].” (API key may be required.) |
| **desktop-ui** | desktop-ui | run.py | macOS desktop automation (peekaboo): list windows, click, type, screenshot. | “List my open apps” or “Take a screenshot of the desktop.” (macOS + peekaboo only.) |
| **ip-cameras** | ip-cameras | run.py | RTSP/ONVIF camera snap/clip via camsnap. | “Snapshot from my kitchen camera” or “Record 5 seconds from camera X.” (Requires camsnap + ffmpeg + config.) |

---

## Quick testing checklist

1. **Config:** `use_skills: true`, `skills_dir: skills`. Optional: `skills_use_vector_search: true`, `skills_refresh_on_startup: true`.
2. **Restart Core** so skills are loaded (and synced to vector store if vector search is on).
3. **Chat:** Use WebChat, inbound, or your main chat UI. Send a message that clearly matches one skill (e.g. “Write a LinkedIn post about …”, “What’s the weather in Tokyo?”).
4. **Logs:** Check for `[skills] selected: …` to see which skill(s) were injected.
5. **Instruction-only:** The model should follow the skill’s guidelines in its reply (e.g. LinkedIn tone, weather format).
6. **Script-based:** The model should call `run_skill(skill_name="folder-name", script="script_name", args=[...])` when appropriate; ensure the script is in **tools.run_skill_allowlist** if you use an allowlist.

---

## Dependencies (for script / CLI skills)

- **summarize:** `summarize` CLI + provider API key (e.g. GEMINI_API_KEY).
- **weather:** No key; uses `curl` (wttr.in / Open-Meteo).
- **file-search:** `fd`, `rg` (ripgrep).
- **notion:** Notion integration token + shared pages.
- **trello:** TRELLO_API_KEY, TRELLO_TOKEN.
- **outlook:** MATON_API_KEY (or OAuth as per skill).
- **apple-notes:** `memo` (macOS).
- **gog:** `gog` CLI + OAuth.
- **openai-whisper:** `whisper` CLI.
- **baidu-search:** BAIDU_API_KEY + `run_skill(..., script="search.py", args=[...])`.
- **image-generation:** API key if required; `run_skill(..., script="generate_image.py", args=[...])`.
- **desktop-ui:** peekaboo (macOS).
- **ip-cameras:** camsnap, ffmpeg, camera config.

---

## Example chat prompts by category

**Writing / content**  
- “Write a LinkedIn post about remote work.”  
- “Draft a short LinkedIn story post about a lesson I learned last week.”

**Weather**  
- “What’s the weather in Berlin?”  
- “Weather in Tokyo tomorrow?”

**Summarize**  
- “Summarize this URL: https://…”  
- “Summarize the PDF at /path/to/file.pdf.” (if summarize CLI supports it.)

**Search**  
- “Search Baidu for 人工智能最新进展.”  
- “Find files named *.md in my project.”  
- “Search my Notion for meeting notes.”

**Productivity**  
- “List my Trello boards.”  
- “Add a card to my Trello list In Progress.”  
- “Check my Outlook inbox.”  
- “Add a note: call mom.” (Apple Notes / memo.)

**Media / automation**  
- “Transcribe the audio at /path/to/recording.mp3.”  
- “Generate an image of a sunset over mountains.”  
- “Take a snapshot from my IP camera named kitchen.”

**Social / X**  
- “Post a tweet: Hello world.”  
- “What should I post on X about AI today?” (social-media-agent.)

Use these as a reference to test each skill via chat; adjust prompts to your config (e.g. API keys, camera names, paths).
