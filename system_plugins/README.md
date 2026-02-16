# System Plugins

Plugins that ship with HomeClaw and provide core UI and automation features. They live at the **project root** under **system_plugins/** (not under examples).

## Run all with Core (one command)

Set **`system_plugins_auto_start: true`** in **config/core.yml**. When you start Core (e.g. `python -m main start`), it will:

1. Start Core as usual.
2. A background task **polls Core** (GET `/ui`) until it responds (or 60s timeout). Only then does it start plugins, so registration runs when Core is ready.
3. Start each plugin in **system_plugins/** that has `register.js` and a server (`server.js` or `package.json` start script).
4. After a short delay, run `node register.js` for each so they register with Core.

You only need to run Core; all system plugins start and register automatically. Stopping Core also terminates the plugin processes.

Optional: **`system_plugins: [homeclaw-browser]`** in core.yml limits auto-start to that list; leave empty to start all discovered plugins.

**First-time setup** for a plugin (e.g. homeclaw-browser): run `npm install` and `npx playwright install chromium` once in that plugin folder. After that, Core can start it without extra steps.

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
