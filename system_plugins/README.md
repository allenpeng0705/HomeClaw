# System Plugins

Plugins that ship with HomeClaw and provide core UI and automation features. They live at the **project root** under **system_plugins/** (not under examples).

## homeclaw-browser

Single Node.js plugin that provides:

- **Control UI / WebChat** — GET `/`, WebSocket `/ws` (proxy to Core). Chat with the agent from the browser.
- **Browser automation** — Capabilities: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill`, `browser_scroll`, `browser_close_session` (Playwright in Node). Set `tools.browser_enabled: false` in Core to use this plugin for browser actions.
- **Canvas** — GET `/canvas`, capability `canvas_update`; agent pushes UI to the canvas viewer.
- **Nodes** — GET `/nodes`, capabilities `node_list`, `node_command`; devices connect via `/nodes-ws`.

**Run:** `cd system_plugins/homeclaw-browser && npm install && npx playwright install chromium && node server.js`  
**Register:** `node register.js` (Core must be running)  
**Launcher:** Open **http://127.0.0.1:9000/ui** to see WebChat, Canvas, Nodes links.  
**WebChat:** **http://127.0.0.1:3020/** (default port 3020)

See **[homeclaw-browser/README.md](homeclaw-browser/README.md)** for design, env vars (CORE_URL, CORE_API_KEY, PORT, BROWSER_HEADLESS), and how to test.

Design: [docs_design/BrowserCanvasNodesPluginDesign.md](../docs_design/BrowserCanvasNodesPluginDesign.md), [docs_design/PluginUIsAndHomeClawControlUI.md](../docs_design/PluginUIsAndHomeClawControlUI.md).
