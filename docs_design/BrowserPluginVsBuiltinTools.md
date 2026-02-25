# HomeClaw Browser: Plugin vs Built-in Tools — Comparison

This document compares the **system plugin** `system_plugins/homeclaw-browser` (Node.js) with the **built-in browser tools** (Python in Core, `tools/builtin.py`) so you can choose which is more stable and feature-complete for your setup.

---

## 1. Architecture

| Aspect | **Plugin (homeclaw-browser)** | **Built-in tools** |
|--------|-------------------------------|---------------------|
| **Process** | Separate Node.js process (e.g. port 3020). Core calls it via HTTP POST. | Same process as Core (Python). Playwright runs inside Core. |
| **Isolation** | **Yes.** Plugin crash/hang does not crash Core. Core can timeout (default 420s) and return an error. | **No.** Playwright/Chromium runs in Core. A hung or crashing browser can block or crash Core. |
| **Session** | Per `user_id` / `session_id` in the Node server; browser context lives in the plugin process. | Per request context (`context.browser_session`); one browser/page per tool chain in Core. |
| **Control UI / WebChat** | **Yes.** Same server serves Control UI, WebChat, canvas, nodes. One place to manage browser and nodes. | **No.** No UI; tools only. |

**Verdict (stability):** The **plugin is more stable** because of process isolation. A long-running or failing browser task in the built-in tools can block Core or require killing the whole process.

---

## 2. Capabilities (Features)

### 2.1 Basic browser (navigate, snapshot, click, type)

| Capability | **Plugin** | **Built-in** |
|------------|------------|--------------|
| **browser_navigate** | ✅ URL + max_chars, session_id. 30s goto timeout. Extracts URL from sentence. | ✅ url, max_chars. 20s goto timeout. |
| **browser_snapshot** | ✅ Elements with ref + selector; contenteditable. | ✅ Same idea; optional screenshot to temp file. |
| **browser_click** | ✅ selector or ref. | ✅ selector only. |
| **browser_type** | ✅ selector or ref + text. | ✅ selector + text. |
| **browser_fill** | ✅ Clear + fill (same as type). | ❌ Not exposed (only browser_type). |
| **browser_scroll** | ✅ direction, optional selector. | ❌ Not available. |
| **browser_close_session** | ✅ Explicit close to free resources. | ⚠️ `close_browser_session()` exists but is not a registered tool; session lives for request. |

### 2.2 Browser settings (emulation / environment)

| Capability | **Plugin** | **Built-in** |
|------------|------------|--------------|
| **browser_set_color_scheme** | ✅ dark / light / no-preference | ❌ |
| **browser_set_geolocation** | ✅ lat/lon/accuracy, clear | ❌ |
| **browser_set_timezone** | ✅ IANA timezone | ❌ |
| **browser_set_locale** | ✅ Accept-Language | ❌ |
| **browser_set_device** | ✅ iPhone 14, iPad, Pixel, Desktop viewport | ❌ |
| **browser_set_offline** | ✅ Emulate offline | ❌ |
| **browser_set_extra_headers** | ✅ Custom headers | ❌ |
| **browser_set_credentials** | ✅ HTTP Basic auth | ❌ |

### 2.3 Canvas and nodes (devices / Companion)

| Capability | **Plugin** | **Built-in** |
|------------|------------|--------------|
| **canvas_update** | ✅ Push UI to /canvas viewer | ❌ |
| **node_list** | ✅ List connected nodes (devices) | ❌ |
| **node_command** | ✅ Send command to node | ❌ |
| **node_notify** | ✅ System notification on node | ❌ |
| **node_camera_snap** | ✅ Photo on node (front/back/both) | ❌ |
| **node_camera_clip** | ✅ Video clip on node (duration, audio) | ❌ |
| **node_screen_record** | ✅ Screen recording on node | ❌ |
| **node_location_get** | ✅ Device location from node | ❌ |

### 2.4 Other

| Capability | **Plugin** | **Built-in** |
|------------|------------|--------------|
| **web_search_browser** | ❌ (not in plugin) | ✅ Google/Bing/Baidu via browser (no API key; fragile) |

**Verdict (features):** The **plugin has many more functions**: scroll, fill, all set_* options, canvas, and the full node stack (list, command, notify, camera snap/clip, screen record, location). The built-in tools only cover basic navigate/snapshot/click/type and a separate web_search_browser helper.

---

## 3. Stability and robustness

| Aspect | **Plugin** | **Built-in** |
|--------|------------|--------------|
| **Timeout** | Core → plugin: configurable (default **420s** in plugin config). Plugin internal goto: **30s**. Long operations (e.g. node video) can complete without Core giving up too early. | Core applies **tool_timeout_sec** (default 120s) to the whole tool call. Page goto: **20s** hardcoded. No separate long timeout for media. |
| **Crash impact** | Plugin crash: Core gets HTTP error; Core and other tools keep running. | Playwright/Chromium crash or hang: can block or crash the Core process. |
| **Resource cleanup** | Explicit **browser_close_session**; one context per user/session in Node. | Session tied to request; no explicit “close” tool; relies on GC/process. |
| **URL vs node_id** | Plugin distinguishes URL vs node id; returns clear error if user says “open test-node-1” (suggests node_camera_*). | Built-in tools only do browser; no node concept. No confusion. |
| **Dependencies** | Node + Playwright in plugin env. Core does not need Playwright. | Core needs **playwright** and **chromium** in the same Python env. Wrong Python/venv can cause “executable not found”. |

**Verdict (stability):** The **plugin is more stable**: process isolation, higher default timeout for long tasks, explicit session lifecycle, and no risk of taking down Core if the browser or a node hangs. The built-in tools are simpler but share Core’s process and can block or crash it.

---

## 4. Configuration and deployment

| Aspect | **Plugin** | **Built-in** |
|--------|------------|--------------|
| **Enable/disable** | Start plugin (e.g. `system_plugins_auto_start: true` or manual `node server.js`). Core uses it when plugin is registered. | **tools.browser_enabled** in config (default true). If false, browser_* tools are not registered; only fetch_url remains. |
| **Headless** | Plugin env e.g. `BROWSER_HEADLESS: false` (Control UI can show browser). | **tools.browser_headless** in Core config. |
| **Install** | Node: `npm install` in plugin dir; `playwright install` in Node env. Core does not need Playwright. | Python: `pip install playwright`, then `python -m playwright install chromium` **with the same Python that runs Core**. |
| **Multi-user** | Session key by user_id/session_id; each user can have a separate browser context. | Single in-memory session per request; no durable multi-user browser state. |

---

## 5. Summary table

| Criterion | **Plugin (homeclaw-browser)** | **Built-in tools** |
|-----------|-------------------------------|---------------------|
| **Stability** | ✅ Better (isolated process, timeouts, no Core crash) | ⚠️ Worse (same process, can block/crash Core) |
| **Functions** | ✅ More (scroll, fill, set_*, canvas, nodes, camera, screen, location) | ⚠️ Fewer (navigate, snapshot, click, type, web_search_browser) |
| **Control UI / WebChat** | ✅ Yes | ❌ No |
| **Nodes / devices** | ✅ Full support | ❌ None |
| **Canvas** | ✅ Yes | ❌ No |
| **Setup** | Separate Node process; no Playwright in Core | Playwright + Chromium in Core’s Python env |

---

## 6. Recommendation

- **For production and when you care about stability and features (nodes, canvas, Control UI):** use the **plugin** (`system_plugins/homeclaw-browser`) and set **tools.browser_enabled: false** in Core so the model uses `route_to_plugin` for browser and node actions only. This matches “we are majorly using the system_plugins/homeclaw-browser” and is the more stable, feature-rich option.
- **For minimal setup (no Node, no nodes/canvas):** you can use the **built-in tools** (tools.browser_enabled: true, Playwright installed in Core’s Python). Prefer **fetch_url** for read-only page content to avoid starting Chromium when not needed.

**Conclusion:** The **plugin is more stable and has more functions**. The built-in browser tools are a fallback when you do not run the plugin; they are not a replacement for the plugin’s full feature set and isolation.
