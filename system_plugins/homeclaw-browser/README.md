# HomeClaw Browser Plugin

Node.js **system plugin** (in **system_plugins/homeclaw-browser**) that provides **browser automation** (Playwright), **canvas**, **nodes**, and **Control UI** (WebChat, dashboard). The Control UI (WebChat + WebSocket proxy to Core) is merged into this plugin; one server serves WebChat at `/`, canvas at `/canvas`, nodes at `/nodes`, and proxies chat to Core at `/ws`.

**Design:** [docs_design/BrowserCanvasNodesPluginDesign.md](../../docs_design/BrowserCanvasNodesPluginDesign.md)

---

## Control UI (WebChat)

Control UI lives in the **control-ui/** folder (like **browser/**, **canvas/**, **nodes/**).

- **GET /** — WebChat page (`control-ui/index.html`); connect to same-origin **/ws** (plugin proxies to Core’s `/ws`). Set **CORE_URL** and **CORE_API_KEY** (if Core has auth) when starting the server.
- **WS /ws** — Proxy: browser ↔ Core `/ws` (handled by **control-ui/ws-proxy.js**). Same behavior as the former homeclaw-control-ui plugin.
- **Launcher:** Plugin registers **ui.webchat**, **ui.control**, **ui.dashboard**; Core **GET /ui** shows WebChat and Control UI links.

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

```bash
# From project root or plugin directory
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

**Test the command path (echo only)**

1. Open **http://127.0.0.1:3020/nodes**, set Node ID (e.g. `test-node-1`), click **Connect as node**.
2. From another terminal, call the plugin:
   ```bash
   # Camera snap (params: node_id, optional facing, maxWidth)
   curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"node_camera_snap","capability_parameters":{"node_id":"test-node-1"}}'
   # Camera clip with microphone (params: node_id, optional duration, includeAudio)
   curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"2","plugin_id":"homeclaw-browser","capability_id":"node_camera_clip","capability_parameters":{"node_id":"test-node-1","duration":"3s","includeAudio":true}}'
   ```
3. With the **default test node** (Nodes page), the node only **echoes** the command: you get a result like `Echo: camera_snap` or `Echo: camera_clip ...` — no real camera/mic is used. This confirms the path (Core → plugin → node → result) works.

**Test real camera and microphone (browser test node)**

If the Nodes page has been updated to support real camera/mic (see below), use **HTTPS or localhost** and grant camera/mic when the browser prompts:

1. Open **http://127.0.0.1:3020/nodes** (or https if required by the browser for getUserMedia).
2. Click **Connect as node**; when prompted, allow camera and microphone.
3. From chat, ask e.g. *“Take a photo on test-node-1”* or *“Record a short video with sound on test-node-1.”* Or use the `curl` calls above. The node will use the device camera (and mic for `camera_clip` when `includeAudio: true`) and return a snapshot or clip (e.g. as a data URL or MEDIA path in the result).

**From chat**

- *“Take a photo on test-node-1”* → `node_camera_snap` (or `node_command` with `camera_snap`).
- *“Record a 3 second video with microphone on test-node-1”* → `node_camera_clip` with `duration: "3s"`, `includeAudio: true`.

**Note:** Real camera/mic require a node that implements `getUserMedia` (and, for video, `MediaRecorder`). The built-in test node can be extended to do this in the browser; otherwise use a phone or desktop app that implements the node protocol and device APIs.

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
| **camera_snap** | facing (front/back/both), maxWidth | Returns image; node may return MEDIA path. |
| **camera_clip** | facing, duration, includeAudio | Short video from camera. |
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
