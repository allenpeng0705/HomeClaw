# Tools Design: Four Core Categories and Robustness

Tools are the **base of skills**: capability and stability matter most. This doc maps the current tool set to four essential categories, identifies gaps and failure modes (permissions, failing easily), and outlines how to achieve **full, easy, stable, and robust** support for each.

---

## 0. Design principles: Utilize, not control

**Target:** Use the computer’s **storage**, **network**, and **applications** — not to “control” the machine. If an application (or tool) is not there, it can be **installed and used** (Python, Node.js, or others). The runtime should support **installing tools**, **mapping requests to tools**, and **using them** in a stable way.

- **Multi-choice for capabilities:** Don’t depend on a single heavy dependency (e.g. Chromium). Prefer **simple tools first** (e.g. `fetch_url` for web content); use heavier tools (e.g. Playwright) only when needed (click/type on the page). When a tool isn’t installed (e.g. Playwright), **don’t register it** so the model uses the simpler option (`fetch_url`) and never hits “no Chromium”.
- **Different file types:** Support PDF, PPT, Word, MD, HTML, XML, JSON, and more via **one powerful tool**: [Unstructured](https://unstructured.io/) (`pip install 'unstructured[all-docs]'`). If not installed, fall back to `pypdf` for PDF and plain text for others; return a clear message for Office formats. For long files, **truncate with a hint** (increase `max_chars` or ask for section-by-section summary).
- **No hang:** When any tool has problems, **catch exceptions** and **timeout** so a single tool **never hangs the whole system**. Every tool call is wrapped in a per-tool timeout; on timeout or exception, return a clear error string and continue.

---

## 1. The Four Categories

| # | Category | Purpose | Examples |
|---|----------|---------|----------|
| **1** | **Files / folders** | Read, modify, create, list, find | Read config, edit notes, create folder, list dir, find "*.py" |
| **2** | **Web access** | Visit sites, search internet, retrieve data for reference | Fetch page, search web, get text from URL |
| **3** | **Web API / service** | Call external APIs or services to do something | Create a post, book a hotel, rent a car, send to webhook |
| **4** | **Launch application** | Run an app (CLI or UI), installed or installable, to finish a task | Run script, open app, exec command |

---

## 2. Current Mapping and Gaps

### Category 1: Files / folders

| Need | Current tool(s) | Status |
|------|-----------------|--------|
| Read file | `file_read` | ✅ Under `tools.file_read_base` |
| Modify file | `file_edit`, `apply_patch` | ✅ Same base |
| Create file | `file_write` (creates parent dirs) | ✅ |
| Create folder | Implicit via `file_write` (parent dirs); no dedicated `folder_create` | ⚠️ Optional: add for clarity |
| List folder | `folder_list` | ✅ |
| Find file/folder | `file_find` (glob pattern) | ✅ |
| Read documents (PDF, PPT, Word, MD, HTML, XML, JSON, …) | `document_read` (Unstructured when installed; pypdf fallback for PDF) | ✅ One powerful tool |

**Failure modes:** Path outside `file_read_base` → "path must be under the configured base directory". Wrong base path in config → "not a file or not found". Permissions = config-driven (`file_read_base`); no per-user tool permissions.

---

### Category 2: Web access (multi-choice)

| Need | Current tool(s) | Status |
|------|-----------------|--------|
| Visit site / get content | **`fetch_url`** (HTTP GET, HTML stripped; **no Chromium**), **`web_extract`** (free; main-content extraction from URLs; trafilatura/BeautifulSoup), **`web_crawl`** (free; crawl from URL with depth/limit), **`browser_navigate`** (Playwright, optional) | ✅ Prefer fetch_url or web_extract; web_crawl for exploring sites; browser when click/type needed |
| Search internet | `web_search` (providers: **Tavily** free tier, **Brave** web/news/video/image, **SerpAPI** Google/Bing/Baidu; fallback DuckDuckGo) | ✅ Set `tools.web.search.provider` and API key per provider |
| Retrieve data for reference | `fetch_url`, `browser_*` (snapshot, click, type) | ✅ |

**Multi-choice behavior:**  
- **fetch_url** is always registered; no Chromium or Playwright required. Use it for reading web pages.  
- **browser_*** tools are registered **only if** `tools.browser_enabled` is true **and** Playwright is installed. If Playwright isn’t installed (or browser_enabled is false), browser tools are **not** registered — the model only sees `fetch_url` and `web_search`, so it never tries `browser_navigate` and never hits “no Chromium”. Set `tools.browser_enabled: false` in config to disable browser tools entirely.

**Failure modes:**  
- **web_search**: Fails if provider’s API key not set (Brave: `BRAVE_API_KEY` or `tools.web.search.api_key`; Tavily: `TAVILY_API_KEY` or `tools.web.search.tavily.api_key`) → returns error JSON.  
- **fetch_url**: Fails on non-200, timeouts, or missing `httpx`.  
- **browser_***: Only present when Playwright is available; otherwise not registered.

**Web search "unconfigured" / "API key not set":** If the model says web search is "unconfigured" or "unavailable", the tool returned "API key not set". **Fix:** Set **TAVILY_API_KEY** in the environment where Core runs (e.g. `export TAVILY_API_KEY=tvly-xxx`), or put the key in **config/core.yml** under `tools.web.search.tavily.api_key`. Tavily free tier: **1000 searches/month** at [tavily.com](https://tavily.com). Restart Core after changing config. If the model also adds "ethical considerations" or refuses the topic, that is the model's own safety layer — the tool error and the model refusal are separate.

**Web search fallback (no API key / expired / rate limit):** When Tavily or Brave API key is not set, expired, or exceeds plan, Core can use **DuckDuckGo** as a fallback (no API key). Set `tools.web.search.fallback_no_key: true` (default) and optionally `fallback_max_results: 5` (3–10). Install: `pip install duckduckgo-search`. Fallback returns top 3–5 results in the same JSON shape as Tavily/Brave. To disable fallback, set `fallback_no_key: false`.

**Tavily Search options:** Under `tools.web.search.tavily` you can set **search_depth** (`basic` \| `fast` \| `advanced` \| `ultra-fast`; default `basic`), **topic** (`general` \| `news` \| `finance`; default `general`), and **time_range** (`day` \| `week` \| `month` \| `year`; empty = no filter). These apply only to `web_search` when provider is Tavily.

**Tavily Extract / Crawl / Research:** Same Tavily API key (TAVILY_API_KEY or `tools.web.search.tavily.api_key`) is used for **tavily_extract** (extract content from one or more URLs), **tavily_crawl** (crawl a site from a base URL), and **tavily_research** (async research task: create then poll until done; returns report content and sources). Use `tavily_extract` when the user wants to read or summarize specific pages by URL; `tavily_crawl` to explore or map a site; `tavily_research` for deep research reports.

**Brave Search (web, news, video, image):** When `provider` is **brave**, set BRAVE_API_KEY or `tools.web.search.brave.api_key`. Pass **search_type** in the tool call or config: `web` (default), `news`, `video`, or `image`. [Brave Search API](https://api-dashboard.search.brave.com/documentation/services/web-search) offers freshness filtering, extra snippets, and local/rich enrichments on paid plans.

**SerpAPI (Google, Bing, Baidu):** When `provider` is **serpapi**, set SERPAPI_API_KEY or `tools.web.search.serpapi.api_key`. Pass **engine** in the tool call or config: `google` (default), `bing`, or `baidu`. [SerpAPI](https://serpapi.com/) has a free tier (~250 searches/month); paid for higher volume.

**Free search (no API key):** Set **provider** to **duckduckgo** for search with no API key. Install: `pip install duckduckgo-search`. Use when you want to avoid any paid or key-based provider.

**Google and Bing with free tiers (API key required):**  
- **Google Custom Search (google_cse):** Set `provider: google_cse`, **GOOGLE_CSE_API_KEY** and **GOOGLE_CSE_CX** (Search Engine ID from [Programmable Search Engine](https://programmablesearchengine.google.com/)). **100 free queries per day**; then $5 per 1,000.  
- **Bing Web Search (bing):** Set `provider: bing`, **BING_SEARCH_SUBSCRIPTION_KEY** (Azure). **1,000 free transactions per month**. Note: Bing Search APIs are [retiring Aug 2025](https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/create-bing-search-service-resource).

**Browser-based search (no API key):** When Playwright is installed and browser tools are enabled, **web_search_browser** searches **Google**, **Bing**, or **Baidu** by opening the search page in a headless browser and parsing results. No API key. Fragile: CAPTCHA or HTML changes may break it; prefer **duckduckgo** or **google_cse**/bing when possible.

**Free extract and crawl (no API key):** **web_extract** and **web_crawl** use only Python and HTTP: no paid service required. **web_extract** fetches one or more URLs and extracts main content using **trafilatura** (best) or **BeautifulSoup** when installed; otherwise falls back to basic HTML stripping. **web_crawl** starts from a URL, follows links (optionally same-domain only), and extracts content up to `max_pages` and `max_depth`. Optional: `pip install trafilatura` or `pip install beautifulsoup4` for better extraction.

---

### Category 3: Web API / service

| Need | Current tool(s) | Status |
|------|-----------------|--------|
| Call an API to do something | `webhook_trigger` (POST only, optional JSON body) | ⚠️ **Limited**: POST only; no GET/PUT/PATCH/DELETE, no custom headers or auth |

**Gap:** No generic **http_request** (method, url, headers, body). Booking hotel, rent car, create post often need GET (read) + POST/PUT (write), and headers (e.g. `Authorization: Bearer ...`). Skills can work around with `webhook_trigger` for POST-only flows, but not for full REST.

**Failure modes:** Wrong URL, network error, 4xx/5xx → exception or opaque error. No retries or structured error codes.

---

### Category 4: Launch application

| Need | Current tool(s) | Status |
|------|-----------------|--------|
| Run CLI command | `exec` (allowlisted commands only) | ✅ |
| Run in background | `exec(background=true)`, `process_list`, `process_poll`, `process_kill` | ✅ |
| Run script from skill | `run_skill` (skill_name, script, args) | ✅ Sandboxed under skill, optional allowlist |
| Launch GUI app | — | ⚠️ Only via `exec` if e.g. `open` (macOS) or `xdg-open` is in allowlist |

**Failure modes:**  
- **exec**: Fails easily if command not in `tools.exec_allowlist` → "command 'X' is not in the allowlist". User must add each command (e.g. `open`, `python`, `node`) to config.  
- **run_skill**: Script not in `run_skill_allowlist` (if set) or path outside skill → error.  
- No dedicated "launch app by name" (e.g. "open Slack"); achievable only by allowlisting `open` and passing args.

---

## 3. How to Achieve Full, Easy, Stable, and Robust Support

### 3.1 Permissions and configuration

- **Single place for tool config:** All under `config/core.yml` → `tools:` (already: `exec_allowlist`, `file_read_base`, `run_skill_allowlist`, `web.search.api_key`, `browser_headless`).  
- **Document required config** so tools don’t "fail easily" due to missing keys:
  - **Web search:** Set provider (`tools.web.search.provider`: `brave` or `tavily`) and the corresponding API key (Brave: `BRAVE_API_KEY` or `tools.web.search.api_key`; Tavily: `TAVILY_API_KEY` or `tools.web.search.tavily.api_key`; [Tavily](https://www.tavily.com/) has a free tier).
  - **File tools:** Set `tools.file_read_base` to a path the process can read/write (e.g. `.` or `/Users/you/Documents`).
  - **Exec:** Add needed commands to `tools.exec_allowlist` (e.g. `open`, `python`, `node`).
  - **Run skill:** If using allowlist, add script names to `tools.run_skill_allowlist`.
- **Startup check (optional):** Validate that `file_read_base` exists and is readable; warn if web_search is used but API key is missing; warn if browser tools are registered but Playwright isn’t installed.

### 3.2 Clear, consistent error responses

- Each tool returns a **string**. Use a consistent pattern for errors, e.g. `"Error: <short reason>"` or JSON `{"error": "...", ...}` so the LLM can retry or explain.
- **Registry:** `ToolRegistry.execute_async` already catches exceptions and returns `"Error running tool {name}: {e!s}"`. Keep it; ensure individual executors return clear messages (e.g. "path must be under the configured base directory", "Web search not configured. Set BRAVE_API_KEY or config tools.web.search.api_key").

### 3.3 Category-specific improvements

**1) Files / folders**

- Add **file_find** (or **folder_find**): search under `file_read_base` by name pattern (glob or substring), return list of relative paths. This closes the "find file/folder" gap.
- Optionally add **folder_create** for explicit directory creation (currently covered by `file_write` creating parents).
- Keep path restriction under `file_read_base`; document it in TOOLS.md and skill docs.

**2) Web access**

- **fetch_url**: Keep; document that it’s for static HTML (no JS). For JS-rendered content, document use of `browser_navigate` + `browser_snapshot`.
- **web_search**: Provider choice **Brave** or **Tavily** (configurable). [Tavily](https://www.tavily.com/) is the web-access layer used by LangChain and others; free and paid plans. Document required API key per provider.
- **Browser**: Document Playwright install (`pip install playwright`, `python -m playwright install chromium`) and `browser_headless` for servers.

**3) Web API / service**

- Add a generic **http_request** tool: method (GET, POST, PUT, PATCH, DELETE), url, optional headers (e.g. `Authorization`), optional body. Timeout and optional max response size. This supports booking, posting, etc., without a new tool per API.
- Keep **webhook_trigger** for simple POST-only use cases; document that **http_request** is for full REST.

**4) Launch application**

- Keep **exec** + allowlist for safety. Document how to allowlist `open` (macOS), `xdg-open` (Linux), or other launchers for "open app by name."
- Optionally add **open_application** (e.g. app name or path) that wraps platform-specific launch and is allowlisted as one command (e.g. `open` on macOS). Lower priority if allowlist is well documented.

### 3.4 Stability and robustness (no hang)

- **Per-tool timeout:** Core wraps each `registry.execute_async(...)` in `asyncio.wait_for(..., timeout=tool_timeout_seconds)`. Config: `tools.tool_timeout_seconds` (default 120; 0 = no timeout). On timeout, the tool returns a clear error string ("tool X timed out after Ys; the system did not hang") and the loop continues. **A single tool can never hang the whole system.**
- **Exception handling:** Registry and Core catch exceptions; every tool returns a string (never raises to the caller). Individual executors catch and return "Error: ..." for validation and runtime errors.
- **Timeouts inside tools:** exec, run_skill, fetch (httpx), webhook, http_request use their own timeouts; the per-tool timeout in Core is a final safeguard.
- **Retries:** Optional retry for network tools can be added later; start with clear errors.
- **Validation:** Validate required args at the start of each executor and return a clear "Error: ..." instead of raising.
- **Logging:** Keep `logger.exception` in registry on tool failure.

---

## 4. Summary: What Exists vs What to Add

| Category | Exists | Add / improve |
|----------|--------|----------------|
| **1. Files/folders** | file_read, file_write, file_edit, apply_patch, folder_list, **file_find**, **document_read** (Unstructured for PDF/PPT/Word/MD/HTML/XML/JSON/…; pypdf fallback for PDF) | Optional folder_create. |
| **2. Web access** | fetch_url (always), **web_search** (Brave or **Tavily** configurable), browser_* (only if Playwright + browser_enabled) | Multi-choice: prefer fetch_url; Tavily for AI-oriented search. |
| **3. Web API** | http_request (GET/POST/PUT/PATCH/DELETE, headers), webhook_trigger (POST) | — |
| **4. Launch app** | exec, process_*, run_skill | Document allowlist (e.g. `open`); optional open_application later. |

**No-hang guarantee:** Per-tool timeout (`tools.tool_timeout_seconds`, default 120s) in Core; exceptions caught and returned as error strings. Tools are **easy to use** and **fail clearly**; a single tool never hangs the system.

---

## 5. Cross-platform support (Mac, Linux, Windows)

The system is designed to run **cross-platform (Mac, Linux, Windows)**. Code uses `Path()` and platform-aware defaults so one config works on all systems where possible.

**Platform-aware defaults**

- **exec allowlist:** When `tools.exec_allowlist` is empty or omitted, the code uses a **platform default**: on **Windows** → `date`, `whoami`, `echo`, `cd`, `dir`, `type`, `where`, `powershell`; on **Mac/Linux** → `date`, `whoami`, `echo`, `pwd`, `ls`, `cat`, `which`. Set `exec_allowlist` explicitly in config to override.
- **file_read_base:** Default is **`.`** (current working directory) so file tools work the same on all OSes. Set to an absolute path (e.g. `/Users/you/Docs` or `C:\Users\you\Docs`) if you need a fixed tree.
- **run_skill:** `.py`/`.pyw` scripts run with Python on all platforms. **`.sh`/`.bash` on Windows** are run via **bash** (e.g. Git Bash) or **WSL** if available; otherwise the tool returns a clear error. Use `.py` or `.bat` for Windows-only skills if you prefer.

**What works on all platforms**

- **Core, channels, memory, tools:** Paths use `pathlib.Path`; file/folder tools work with OS-native paths.
- **llama.cpp:** Use the matching folder (`mac/`, `linux_cpu/`, `linux_cuda/`, `win_cpu/`, `win_cuda/`) and binary; Core auto-detects (see `llama.cpp-master/README.md`).
- **Playwright / browser:** `python -m playwright install chromium`; headless/headed both work.
- **Web search, fetch_url, web_extract, web_crawl:** No OS-specific code.
- **Channels:** Matrix, WhatsApp, Webhook, Telegram, etc. run on Mac, Linux, and Windows (WeChat channel is Windows-only for the desktop client).

**Windows-specific**

- **Build:** README requires **Visual C++ Build Tools** on Windows for some Python packages.
- **run_skill .sh:** On Windows, `.sh` scripts run via Git Bash or WSL when available; otherwise use `.py` or `.bat`.

**Summary:** One config (e.g. empty `exec_allowlist`, `file_read_base: "."`) works on Mac, Linux, and Windows. Override in config when you need a fixed allowlist or base path.

---

## 6. Use tool result as final response (skip second LLM)

Core can use a tool’s result as the **final user response** and skip a second LLM call when the result is self-contained. Config: **`config/skills_and_plugins.yml`** under **`tools.use_result_as_response`**.

- **needs_llm_tools:** Tools that return raw content (e.g. document_read, web_search, fetch_url, image). We always run a second LLM to synthesize a reply.
- **self_contained_tools:** Tools whose result can be shown as-is when short (e.g. run_skill, time, profile_get, cron_list). We use the result as the final response when length ≤ max_self_contained_length (default 2000). save_result_page / get_file_view_link are special: we use the result when it contains a file view link (`/files/out?token=`).
- **skills_results_need_llm:** By default all skills (run_skill) use their result as the final response. List skill names (e.g. `maton-api-gateway-1.0.0`) here to **force** a second LLM call for those skills (e.g. to confirm in natural language or explain API responses).
- **Plugins (e.g. homeclaw-browser, ppt-generation):** Invoked via **route_to_plugin**. The plugin’s result is **always** used as the final response; there is no second LLM in Core for plugins. **homeclaw-browser** is a system plugin (camera, browser); same rule applies. When the plugin result contains a file view link, we skip the plugin’s own post_process LLM so the URL is not corrupted.

### 6.1 Response with link (no second/third LLM) — review

We **use the tool result as the final response** when it contains a file view link (`/files/out` and `token=`), and **do not** call the LLM again. This avoids the model truncating or corrupting the URL.

**Flow**

1. **Tool path (save_result_page / get_file_view_link):** After the tool loop, if `last_file_link_result` is set (tool was save_result_page or get_file_view_link and result contains `/files/out` and `token=`), we set `response = last_file_link_result` and **break** — no second LLM.
2. **Plugin path (e.g. ppt-generation):** route_to_plugin runs; when the plugin returns a link (e.g. JSON with output_rel_path), we build the link, set result_text, and **skip post_process LLM** when the result already contains a file view link, then send that text to the user.

**Why it's reasonable**

- Links are built in one place (`build_file_view_link` in result_viewer.py) and always use the form `…/files/out?token=…&path=…`. Requiring both `/files/out` and `token=` in the result matches that format and avoids false positives (e.g. "Report saved to your output folder" has no link).
- The **full** tool result is used as the response (including lines like "SUCCESS. CRITICAL: Use ONLY the URL…"), so the user gets the instruction and the exact URL; we do not strip or rephrase.

**Edge cases (robust)**

| Case | Behavior |
|------|----------|
| save_result_page format=html returns link | Result contains `/files/out` and `token=` → we use it as final response. ✓ |
| save_result_page format=markdown with link | Same; user gets markdown preview + link. ✓ |
| save_result_page returns no link (auth not set) | Result is e.g. "Report saved… Set auth_api_key…" — no `token=` → we do **not** set last_file_link_result; we fall through to self-contained check. save_result_page is only "use as final" when link present, so we do a second LLM. ✓ |
| get_file_view_link returns error | No `/files/out` or `token=` → no last_file_link_result → second LLM can explain. ✓ |
| Multiple tools in one round; last is save_result_page | last_file_link_result is set; we use it (checked first after loop). ✓ |
| Multiple tools; save_result_page then echo | last_file_link_result set by save_result_page, not cleared by echo → we still use the link. ✓ |
| Plugin (ppt) returns JSON with output_rel_path | We build link, set result_text, skip post_process, send exact text. ✓ |

**Detection:** We require both substrings (`"/files/out" in result and "token=" in result`) so that only real file-view URLs trigger the "use as final response" and "skip post_process" behavior. All links produced by `build_file_view_link` include both.
