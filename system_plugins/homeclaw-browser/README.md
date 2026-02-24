# HomeClaw Browser Plugin

Node.js **system plugin** (in **system_plugins/homeclaw-browser**) that provides **browser automation** (Playwright), **canvas**, **nodes**, and **Control UI** (WebChat, dashboard). The Control UI (WebChat + WebSocket proxy to Core) is merged into this plugin; one server serves WebChat at `/`, canvas at `/canvas`, nodes at `/nodes`, and proxies chat to Core at `/ws`.

**Design:** [docs_design/BrowserCanvasNodesPluginDesign.md](../../docs_design/BrowserCanvasNodesPluginDesign.md)

---

## Control UI (WebChat)

Control UI lives in the **control-ui/** folder (like **browser/**, **canvas/**, **nodes/**).

- **GET /** — WebChat page (`control-ui/index.html`); connect to same-origin **/ws** (plugin proxies to Core’s `/ws`). Set **CORE_URL** and **CORE_API_KEY** (if Core has auth) when starting the server.
- **WS /ws** — Proxy: browser ↔ Core `/ws` (handled by **control-ui/ws-proxy.js**). Same behavior as the former homeclaw-control-ui plugin.
- **Launcher:** Plugin registers **ui.webchat**, **ui.control**, **ui.dashboard**; Core **GET /ui** shows WebChat and Control UI links.

**Images / vision in WebChat**  
When you attach **images**, the client first uploads them via **POST /api/upload** (plugin proxies to Core). Core saves files under **database/uploads/** and returns their paths. The chat message then sends **payload.images = [path, ...]** so the model receives the image from disk (no huge data URLs over WebSocket). Video/audio/other still go as data URLs in `payload.videos`, `payload.audios`, `payload.files`. For the assistant to describe images, Core must use a **vision-capable main LLM** (e.g. `main_llm: local_models/main_vl_model` with `mmproj` / `supported_media: [image]` in **config/core.yml**). See **docs_design/Multimodal.md** and the "Vision request" / "main_llm_supported_media" logs if the model says it cannot see images.

**Assistant vs Friend and location (Companion parity)**  
The Control UI dropdown offers **Assistant** (main chat) or **Friend** (Friends plugin). When Friend is selected, the client sends `session_id`, `conversation_type`, and `channel_name` = **friend** (Core config `companion.session_id_value`, default `friend`). When the browser supports the Geolocation API, the page requests position before each send; if the user grants permission, `payload.location` is set to `"lat,lng"` so Core can store latest location per user (see SystemContextDateTimeAndLocation.md). If denied or unavailable, the message is sent without location.

---

## How to use

**use_skills** and **skills_dir** in **config/core.yml** must be set so these skills load (e.g. `use_skills: true`, `skills_dir: config/skills`).

- **desktop-ui (macOS):** Install peekaboo: `brew install steipete/tap/peekaboo`. Then the agent can call e.g. `run_skill(skill_name="desktop-ui", script="run.py", args=["see", "--annotate", "--path", "/tmp/see.png"])`.
- **ip-cameras:** Install camsnap and ffmpeg (e.g. `brew install steipete/tap/camsnap ffmpeg`), configure cameras in **~/.config/camsnap/config.yaml**. Then the agent can call e.g. `run_skill(skill_name="ip-cameras", script="run.py", args=["snap", "kitchen", "--out", "/tmp/shot.jpg"])`.
- **On Windows with desktop-ui,** the agent will get “Desktop UI automation is only available on macOS.” and can report that to the user without any crash.

---

## Phase 1: Browser

- **Capabilities:** `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill`, `browser_scroll`, `browser_close_session`; **browser settings:** `browser_set_color_scheme`, `browser_set_geolocation`, `browser_set_timezone`, `browser_set_locale`, `browser_set_device`, `browser_set_offline`, `browser_set_extra_headers`, `browser_set_credentials`.
- **Session:** One Playwright browser context per `user_id` or `session_id` so multi-turn flows (“go to example.com”, “click Login”) use the same page.
- **Port:** 3020 (default).
- **Cross-platform:** All browser and settings capabilities use Playwright and work on Windows, Linux, and macOS.

### Prerequisites

- **Node.js** 18+
- **Playwright browsers:** After `npm install`, run **`npx playwright install chromium`** once (required for headless/headed browser).

### Use this plugin instead of Core’s browser tools

1. In **config/core.yml**, set:
   ```yaml
   tools:
     browser_enabled: false
   ```
2. Start Core and this plugin; register the plugin. The LLM will then use **route_to_plugin** with `plugin_id: homeclaw-browser` and the right capability (e.g. `browser_navigate`, `browser_snapshot`) for all browser actions.

### Run

**When Core auto-starts the plugin** (`system_plugins_auto_start: true` in **config/core.yml**): you **do not** need to run `cd system_plugins/homeclaw-browser && npm start` (or `node server.js`) or `node register.js` manually. Core starts the plugin and runs `node register.js` for you. Just do the one-time setup below once, then start Core (e.g. `python -m main start`).

**When you run the plugin yourself** (e.g. development or testing with curl without Core):

```bash
# One-time setup (from project root or plugin directory)
cd system_plugins/homeclaw-browser
npm install
npx playwright install chromium   # first time only
node server.js
```

In another terminal (Core must be running):

```bash
node register.js
```

**See the browser window:** By default the browser runs **headless** (no visible window). To see the Chromium window when the agent opens a page:

- **If you start the plugin yourself:** run `BROWSER_HEADLESS=false node server.js`.
- **If Core auto-starts the plugin** (e.g. `system_plugins_auto_start: true`): set it in **config/core.yml** under `system_plugins_env` with the **plugin id** (folder name) so each plugin gets only its own env:
  ```yaml
  system_plugins_env:
    homeclaw-browser:
      BROWSER_HEADLESS: "false"
  ```
  Core passes these env vars only to the `homeclaw-browser` process when it starts it.

Env:

- **PORT** — Plugin HTTP port (default 3020).
- **CORE_URL** — Core base URL (default http://127.0.0.1:9000).
- **PLUGIN_BASE** — Plugin base URL (default http://127.0.0.1:3020).
- **BROWSER_HEADLESS** — Set to `false` to show the browser window (default headless).

### Process review: why video recording can be slow and why you might see 503

**End-to-end flow** for a request like *“Record a 3 second video with microphone on test-node-1”*:

1. **User → Core** — Message goes to Core (e.g. via WebChat).
2. **Core → LLM** — Core runs the main LLM to decide which tool to call (can take several seconds).
3. **LLM → route_to_plugin** — Model calls `route_to_plugin(plugin_id=homeclaw-browser, capability_id=node_camera_clip, parameters={...})`.
4. **Core → Plugin** — Core sends **HTTP POST** to the plugin’s **/run** endpoint and **waits** for the response (timeout 420s by default; must be longer than the plugin→node timeout so Core doesn’t ReadTimeout first).
5. **Plugin → Node** — Plugin sends a command over WebSocket to the connected node (the **Nodes** page tab) and **waits** for the node to finish (timeout e.g. 5 min in `nodes/command.js`).
6. **Node (browser)** — The tab gets the command, calls `getUserMedia` (camera/mic), starts `MediaRecorder`, records for the requested duration, stops, encodes to a blob, converts to a data URL, and sends the result back over the WebSocket.
7. **Plugin → Core** — Plugin returns a **200** JSON response (or **500** on exception). Only then does Core get the result and send it to the user.

**Why it feels slow**

- **LLM** step can take 5–30+ seconds.
- **Node recording** step takes at least the recording duration (e.g. 3s) plus device access, encoding, and sending the (large) data URL; on a slow device or with high resolution this can be 30s–2 min.
- The plugin **does not** respond to Core until the node has finished and the plugin has the result. So the whole chain is one long request.

**Why you might see “plugin returned 503”**

- This plugin’s code **only** returns **200**, **500**, or **404**. It **never** returns **503**.
- **503** almost always comes from **something in front** of the plugin (or Core):
  - A **reverse proxy** (e.g. nginx, Caddy) with a short `proxy_read_timeout` (e.g. 60s). If the plugin takes longer than that to respond, the proxy closes the connection and may return **503 Service Unavailable** to Core.
  - The proxy might also return a custom HTML or text body (e.g. “can we review the process? why it is so slow?”) if that’s how it’s configured for 5xx pages.
- So: **slow request** (recording + encoding) + **short proxy timeout** → proxy gives up → **503** to Core.

**What to do**

- **No proxy for local use:** Call the plugin directly (Core → `http://127.0.0.1:3020/run`). Then 503 from a proxy won’t happen.
- **If you use a reverse proxy:** Increase its read timeout to at least the plugin timeout (default **420 seconds**), so long-running video requests don’t get cut off.
- **Keep the Nodes tab connected** and grant camera/mic so the node can record and return in time; shorten the clip if needed so the total time stays under timeouts.

**Why the node (browser) is slow:** The main delay is **after** the 3s recording: the browser encodes the clip to WebM (often 10–60+ seconds), then converts to base64 and sends a multi‑MB string over the WebSocket. The Nodes page requests **640×480** video to reduce encoding and transfer time. See **docs_design/VideoRecordingSlownessInvestigation.md** for a full breakdown.

---

## Testing (browser, canvas, nodes)

Use these steps to verify browser, canvas, and nodes. Ensure Core is running, the plugin server is running (`node server.js`), and the plugin is registered (`node register.js`). Default plugin URL: **http://127.0.0.1:3020**.

### 1. Test browser

- In **config/core.yml** set `tools.browser_enabled: false`, then start Core and the plugin and run `node register.js`.
- Use **WebChat** at **http://127.0.0.1:3020/** (or Core’s launcher **http://127.0.0.1:9000/ui**) or `python -m main start` so the LLM can call tools.
- Example prompts:
  - *“Open https://example.com in the browser.”* → should call `browser_navigate`.
  - *“Get a snapshot of the page.”* or *“What buttons and links are on the page?”* → `browser_snapshot`.
  - *“Click the first link.”* or *“Click ref 0.”* → `browser_click`.
  - *“Type ‘hello’ into the search box.”* (after navigating to a search page) → `browser_type` or `browser_fill`.
- To see the Chromium window: start the plugin with **BROWSER_HEADLESS=false** (`BROWSER_HEADLESS=false node server.js`).

### 2. Test canvas

**What to do**

1. **Prerequisites:** Core running, plugin server running (`node server.js`), plugin registered (`node register.js`). Default plugin URL: **http://127.0.0.1:3020**.
2. Open **http://127.0.0.1:3020/canvas** in your browser.
3. Leave **Session** as `default` (or type another name, e.g. `my-session`).
4. Click **Connect**.
5. In another terminal, call the plugin to push content to the canvas:
   ```bash
   curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"canvas_update","capability_parameters":{"document":{"title":"Hello","blocks":[{"type":"text","content":"Hello"},{"type":"button","label":"OK"}]}}}'
   ```
   If you use a session other than `default`, add `"session_id": "your_session"` inside `capability_parameters` and use that same session name in the canvas page:
   ```bash
   curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"canvas_update","capability_parameters":{"session_id":"my-session","document":{"title":"Hello","blocks":[{"type":"text","content":"Hello"},{"type":"button","label":"OK"}]}}}'
   ```

**What you should see (in detail)**

- **Before Connect:** Status line: *"Disconnected. Enter session and click Connect."* The content area shows: *"No canvas content yet. The agent can push UI via canvas_update."*
- **After Connect:** Status changes to *"Connected to session: default"* (or the session name you entered). Content area stays empty until an update is pushed.
- **After the curl call:** The page updates in real time (no refresh). You should see:
  - **Title:** "Hello" at the top (bold).
  - **Blocks:** A text line "Hello", then a dark **OK** button. Clicking the button updates the status to *"Clicked: "* (and the button id if set).
- **If nothing appears:** Ensure the session in the canvas page matches the one used in the request (default vs `session_id` in the JSON). If you used `session_id: "my-session"`, type `my-session` in the Session field and click Connect before running curl.

The canvas updates whenever the plugin’s **`canvas_update`** capability is called (by the LLM via `route_to_plugin` or by a direct POST to `/run`). If the agent doesn’t call the plugin when you ask to “update the canvas”, re-register the plugin (`node register.js`) and try again. 

### 3. Test nodes

- Open **http://127.0.0.1:3020/nodes**. Click **Connect as node** (default node id `test-node-1`). The list should show the connected node.
- From chat, ask *“List connected nodes.”* or *“What nodes are connected?”* → agent should call `node_list` and reply with the node id and capabilities.
- Ask *“Send the screen command to test-node-1.”* (or *“Run command screen on node test-node-1.”*) → agent should call `node_command`; the test node echoes the command and the agent returns the result.
- Or call the plugin directly (with the Nodes page connected as `test-node-1`):
  ```bash
  curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"node_list"}'
  curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"2","plugin_id":"homeclaw-browser","capability_id":"node_command","capability_parameters":{"node_id":"test-node-1","command":"screen"}}'
  ```

### 4. Test camera and microphone

Camera and mic are controlled via **node** commands. The **node** (e.g. the Nodes page tab, or a phone/desktop app) must support `camera_snap` and/or `camera_clip`; the plugin only forwards the command and returns the node’s result.

**Test with curl**

1. **You must connect the node first.** Open **http://127.0.0.1:3020/nodes** in a browser, set Node ID to `test-node-1`, click **Connect as node**. Wait until the page shows "Connected as test-node-1". Without this step, the plugin has no node to send the command to.
2. From another terminal, call the plugin:
   ```bash
   # Camera snap (params: node_id, optional facing, maxWidth)
   curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"node_camera_snap","capability_parameters":{"node_id":"test-node-1"}}'

   # Camera clip with microphone (params: node_id, optional duration, includeAudio)
   curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"2","plugin_id":"homeclaw-browser","capability_id":"node_camera_clip","capability_parameters":{"node_id":"test-node-1","duration":"3s","includeAudio":true}}'
   ```
3. The test node uses the **device camera** (and **microphone** for `camera_clip` when `includeAudio: true`) and returns a snapshot or clip in the result (e.g. `media` data URL). Other commands (e.g. `screen`, `notify`) are echoed.

**Test real camera and microphone (browser test node)**

If the Nodes page has been updated to support real camera/mic (see below), use **HTTPS or localhost** and grant camera/mic when the browser prompts:

1. Open **http://127.0.0.1:3020/nodes** (or https if required by the browser for getUserMedia).
2. Click **Connect as node**; when prompted, allow camera and microphone.
3. From chat, ask e.g. *“Take a photo on test-node-1”* or *“Record a short video with sound on test-node-1.”* Or use the `curl` calls above. The node will use the device camera (and mic for `camera_clip` when `includeAudio: true`) and return a snapshot or clip (e.g. as a data URL or MEDIA path in the result).

**From chat**

- *“Take a photo on test-node-1”* → `node_camera_snap` (or `node_command` with `camera_snap`).
- *“Record a 3 second video with microphone on test-node-1”* → `node_camera_clip` with `duration: "3s"`, `includeAudio: true`.

**Note:** The **Nodes page** (http://127.0.0.1:3020/nodes) test node supports **real** camera and microphone in the browser: when you connect as a node and the page receives `camera_snap` or `camera_clip`, it uses `getUserMedia` (and `MediaRecorder` for clips). Grant camera/mic when the browser prompts; the snapshot or clip is returned in the result (e.g. `media` data URL). Other commands (e.g. `screen`, `notify`) are still echoed. For production, use a phone or desktop app that implements the node protocol and device APIs.

**Where are the photo and video placed?** When the user asks to take a photo (or record a clip) and the agent uses **node_camera_snap** or **node_camera_clip** from chat: (1) **Core sends the photo/video to the user via the channel** (e.g. WeChat/Matrix image message, or text + attachment where supported). (2) **Core also saves the file** under the workspace media folder: **`<workspace_dir>/media/images/`** for snapshots (e.g. `20250216_143022_abc12.jpg`) and **`<workspace_dir>/media/videos/`** or **`media/audio/`** for clips/audio. So the user sees the photo in the chat and a copy is kept on disk. When you call the plugin with **curl**, the response JSON still includes the data URL in `metadata.media`; Core does not run for curl, so you only get the JSON (decode and save locally if needed).

**Why does the camera/mic permission prompt only show once?** Browsers remember your choice per site (origin). After you Allow or Block for http://127.0.0.1:3020, that setting is stored and the prompt is not shown again. To see the prompt again: in Chrome, click the lock or info icon next to the URL → **Site settings** → **Camera** / **Microphone** → set to **Ask** or **Reset**; or use a private/incognito window (no stored permissions).

**Nothing happens when I curl node_camera_snap?**

- **Connect the node first.** The plugin only forwards commands to nodes that are connected via WebSocket. Open **http://127.0.0.1:3020/nodes**, set Node ID to `test-node-1`, click **Connect as node**, and wait until you see "Connected as test-node-1". If you skip this, the plugin returns `success: false` and `text: "Node 'test-node-1' not connected"`.
- **See the actual response:** run `curl -v ...` so you see the HTTP response body. If the node is not connected you'll get JSON like `{"success":false,"text":"Node 'test-node-1' not connected",...}`.
- **Check the plugin is running:** `curl http://127.0.0.1:3020/health` should return `{"status":"ok"}`. If connection refused and you use **auto-start**, ensure Core is running (Core starts the plugin). If you run the plugin yourself, start it with `npm start` or `node server.js` in the homeclaw-browser directory.

**"Error: plugin returned 503"**

- This plugin’s code only returns 200, 500, or 404. **503** usually comes from elsewhere: (1) a **reverse proxy or gateway** in front of the plugin (e.g. nginx, Caddy) when it considers the backend unavailable, (2) the **plugin process** overloaded or restarting so connections are refused, or (3) the request hitting a **different service** that returns 503. Check: `curl -v http://127.0.0.1:3020/health` and `curl -v -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{}'` — if you get 503 only sometimes, the plugin may be under load or restarting; restart the plugin and Core and try again.
- **503 after ~2 minutes (e.g. 120s):** Often a **proxy/gateway read timeout**. The plugin may still be waiting for the node (camera_snap, etc.). Increase the proxy’s read timeout (e.g. to 420s or 300s) or call the plugin directly (no proxy). The plugin sets a 6‑minute socket timeout for `/run` so Node won’t close the request; if you still see 503 at ~2 min, the close is coming from in front of the plugin.

**"Error calling plugin homeclaw-browser: ReadTimeout" or "Command timeout" when recording video or taking a photo**

- **Two timeouts:** (1) **Core → plugin** HTTP timeout (default **420s** in `config.timeout_sec` / register.js — must be *longer* than the plugin→node timeout or Core will ReadTimeout before the plugin responds). (2) **Plugin → node** command timeout (5 min in `nodes/command.js` CMD_TIMEOUT_MS). If you see **ReadTimeout**, Core gave up waiting — re-register with `node register.js` (sends 420s) or set `timeout_sec: 420` in config. If you see **Command timeout**, the plugin gave up waiting for the node — increase `CMD_TIMEOUT_MS` in `nodes/command.js` if needed and restart the plugin.
- **Camera works but you still get "Command timeout":** The node may have recorded but the browser’s encoding step (`MediaRecorder` onstop) can hang or take very long. The Nodes page now has a **90s encoding timeout**: if encoding doesn’t finish in 90s, the node sends an error (`encoding_timeout`) so the plugin gets a response instead of waiting 5 min. Keep the **Nodes** tab in the foreground, grant camera/mic, and try a shorter clip (e.g. 3s); if you see `encoding_timeout`, try closing other tabs or lowering resolution.
- **Request took many minutes then failed:** Core waits up to 420s for the plugin. If the node never sends a result (tab closed, recording stuck), the plugin returns at 5 min with "Command timeout" and Core must still be waiting — so Core’s timeout (420s) is set higher than the plugin’s node timeout (5 min). Keep the **Nodes** tab open and connected, grant camera/mic, and try again.

**Model replies "No" or doesn't call the plugin**

- If the main LLM does not support tool/function calling, it may reply with text (e.g. "No") instead of calling `route_to_plugin`. Core has a **fallback**: when the model returns no tool call and the user message clearly matches a node action (e.g. "Take a photo on test-node-1", "record video on test-node-1", "list nodes"), Core will still call the plugin. Use a model that supports tools for best behavior, or rely on this fallback for simple phrases.

**Request seems blocked for minutes, then plugin returns 200 OK but client times out**

- If logs show "LLM call started" long before "LLM call returned in Xs" and then "[plugin] routed" and "HTTP/1.1 200 OK", the delay is in the **main LLM** (e.g. large local model on CPU) deciding to call the plugin, not in the plugin itself. The client (e.g. WebChat) may time out before Core sends the response. Mitigations: use a faster or smaller model, increase the client’s request timeout, or use streaming so the client sees progress.

---

### Capabilities (Phase 1)

| Capability | Purpose |
|------------|--------|
| **browser_navigate** | Open URL; params: `url`, optional `max_chars`, `session_id`. |
| **browser_snapshot** | List interactive elements with refs/selectors; params: optional `session_id`. |
| **browser_click** | Click element; params: `selector` or `ref` (from snapshot), optional `session_id`. |
| **browser_type** / **browser_fill** | Type into input; params: `selector` or `ref`, `text`, optional `session_id`. |
| **browser_scroll** | Scroll page; params: optional `direction` (up/down), `selector`, `session_id`. |
| **browser_close_session** | Close browser context for user/session; params: optional `session_id`. |
| **browser_set_color_scheme** | Set prefers-color-scheme: `color_scheme` = dark \| light \| no-preference \| none. |
| **browser_set_geolocation** | Set or clear geolocation: `latitude`, `longitude`, optional `accuracy`, or `clear: true`. |
| **browser_set_timezone** | Set timezone: `timezone` (e.g. America/New_York). |
| **browser_set_locale** | Set Accept-Language: `locale` (e.g. en-US). |
| **browser_set_device** | Set viewport for device emulation: `device` (e.g. iPhone 14, Desktop 1920x1080). |
| **browser_set_offline** | Emulate offline: `offline` (true/false). |
| **browser_set_extra_headers** | Set extra HTTP headers: `headers` (object). |
| **browser_set_credentials** | Set or clear HTTP Basic auth: `username`, `password`, or `clear: true`. |

---

## Phase 2: Canvas (implemented)

- **GET /canvas** — Canvas viewer page; enter a session key and Connect to receive live updates.
- **WebSocket /canvas-ws?session=...** — Subscribe to canvas updates for that session.
- **Capability canvas_update** — Params: `document` (or `title` + `blocks`), optional `session_id`. The agent can push `{ title: string, blocks: [ { type: "text", content: string } | { type: "button", label: string, id?: string } ] }`; the canvas page updates in real time.
- **Launcher:** Plugin registers **ui.custom** with Canvas URL; **GET /ui** on Core shows a link to Canvas.

## Phase 3: Nodes (implemented)

- **GET /nodes** — Nodes page: list connected nodes (from GET /api/nodes) and “Connect as test node” to register a browser tab as a node.
- **WebSocket /nodes-ws** — First message must be `{ type: "register", node_id: string, capabilities: string[] }`. Then the plugin can send `{ type: "command", id, command, params }`; the node responds with `{ type: "command_result", id, payload: { success, text, error? } }`.
- **Capabilities:** **node_list** (no params). **node_command** (params: `node_id`, `command`, optional `params`). **Convenience:** **node_notify**, **node_camera_snap**, **node_camera_clip**, **node_screen_record**, **node_location_get** — same protocol as node_command; the plugin maps them to the command name and forwards params. Nodes that don’t support a command return `success: false`, `error: "command_not_supported"`; the plugin and Core do not crash.
- **Launcher:** Plugin registers **ui.custom** with Nodes URL; **GET /ui** on Core shows a link to Nodes.

### Node command contract

Nodes may implement these commands (sent via **node_command** or the convenience capabilities). The **node** (e.g. phone or desktop app) may support only some commands or only on some OSes; the plugin just forwards. If the node returns an error (e.g. `command_not_supported`, `platform_not_supported`), the plugin returns that in the result; it never crashes.

| Command | Typical params | Notes |
|---------|----------------|--------|
| **notify** | title, body | System notification (e.g. system.notify on macOS). |
| **camera_snap** | facing (front/back/both), maxWidth | Returns image; node may return MEDIA path. Core saves to workspace/media/images and tells the user the path. |
| **camera_clip** | duration, includeAudio (optional facing) | Short video from camera. Returns video (data URL). Core saves to workspace/media/videos and tells the user the path (e.g. "Video saved to: …/config/workspace/media/videos/YYYYMMDD_HHMMSS_id.webm"). |
| **screen_record** | fps, duration | Screen recording on the node. |
| **location_get** | maxAgeMs | Device location (lat/lon/accuracy). |

---

## Cross-platform and stability

- **Browser and settings:** All capabilities use Playwright and work on **Windows, Linux, and macOS**. Errors (e.g. context closed) are caught and returned as `success: false`, `error: "<message>"`; the plugin never throws to Core.
- **Nodes:** The plugin forwards commands; support depends on the **node** (e.g. camera_snap may be implemented only on certain devices). Unsupported or failed commands return a clear error; the plugin does not crash.
- **Core:** Treats plugin errors (non-2xx or `success: false` in body) without crashing and passes them to the agent/user.

---

## Files

| File | Purpose |
|------|--------|
| **server.js** | HTTP server: GET /health, POST /run, GET / (WebChat), GET /canvas, GET /nodes, GET /api/nodes, WS /ws (proxy to Core), WS /canvas-ws, WS /nodes-ws. |
| **run-handler.js** | Dispatches by capability_id: browser_*, browser_set_*, canvas_update, node_*, node_command. |
| **browser/session.js** | Per-user/session Playwright context. |
| **browser/actions.js** | navigate, snapshot, click, type, fill, scroll, closeSession. |
| **browser/settings.js** | setColorScheme, setGeolocation, setTimezone, setLocale, setDevice, setOffline, setExtraHeaders, setCredentials. |
| **canvas/store.js** | In-memory canvas document per session. |
| **canvas/push.js** | Push canvas updates to WS clients by session. |
| **nodes/registry.js** | Connected nodes (WS + node_id, capabilities). |
| **nodes/command.js** | Send command to node, wait for command_result. |
| **control-ui/index.html** | WebChat (Control UI) page. |
| **control-ui/ws-proxy.js** | WebSocket proxy: browser client ↔ Core /ws. |
| **public/canvas.html** | Canvas viewer page. |
| **public/nodes.html** | Nodes page (list + connect as test node). |
| **tui.js** | Stub for future TUI (run: node tui.js). |
| **register.js** | POST /api/plugins/register with capabilities and ui (webchat, control, dashboard, tui, custom). |
