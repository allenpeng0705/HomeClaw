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

**See the browser window:** By default the browser runs **headless** (no visible window). To see the Chromium window when the agent opens a page, restart the plugin with:

```bash
BROWSER_HEADLESS=false node server.js
```

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

- Open **http://127.0.0.1:3020/canvas** in your browser, enter a session (e.g. `default`), click **Connect**. That page is the canvas viewer; updates pushed by the plugin appear there in real time.
- The canvas updates when the plugin’s **`canvas_update`** capability is called. If the agent doesn’t call the plugin when you ask to “update the canvas”, re-register the plugin (`node register.js`) and try again.
- To see an update without the LLM, call the plugin directly:
  ```bash
  curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"canvas_update","capability_parameters":{"document":{"title":"Hello","blocks":[{"type":"text","content":"Hello"},{"type":"button","label":"OK"}]}}}'
  ```
  With the canvas page open at http://127.0.0.1:3020/canvas and connected with session **default**, you should see the title “Hello” and an “OK” button. For another session, add `"session_id": "your_session"` in `capability_parameters` and use that session in the canvas page.

### 3. Test nodes

- Open **http://127.0.0.1:3020/nodes**. Click **Connect as node** (default node id `test-node-1`). The list should show the connected node.
- From chat, ask *“List connected nodes.”* or *“What nodes are connected?”* → agent should call `node_list` and reply with the node id and capabilities.
- Ask *“Send the screen command to test-node-1.”* (or *“Run command screen on node test-node-1.”*) → agent should call `node_command`; the test node echoes the command and the agent returns the result.
- Or call the plugin directly (with the Nodes page connected as `test-node-1`):
  ```bash
  curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"1","plugin_id":"homeclaw-browser","capability_id":"node_list"}'
  curl -X POST http://127.0.0.1:3020/run -H "Content-Type: application/json" -d '{"request_id":"2","plugin_id":"homeclaw-browser","capability_id":"node_command","capability_parameters":{"node_id":"test-node-1","command":"screen"}}'
  ```

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
