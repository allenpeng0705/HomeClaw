# How to write a plugin

This document describes how to develop **built-in Python plugins** and **external plugins** in other languages (Go, Java, Node.js, etc.), and how plugins can use **MCP (Model Context Protocol)**.

For the full plugin standard (manifest schema, run contract, registration API), see **docs_design/PluginStandard.md** and **docs_design/PluginRegistration.md**. For a complete user guide and parameter collection, see **docs_design/PluginsGuide.md**.

---

## 1. Overview

### 1.1 Plugins vs tools

| Layer | Purpose | Example |
|-------|---------|---------|
| **Tools** | General-purpose, atomic operations (file read, web search, cron) | `file_read`, `web_search`, `cron_schedule` |
| **Plugins** | **Single-feature** modules that do one thing (weather, email, Slack) | Weather, Mail, Quote |

Plugins are **feature-oriented**. The LLM routes user requests to a plugin when the intent matches (e.g. “what’s the weather?” → Weather plugin). Plugins can be **built-in** (Python, in-process) or **external** (any language, separate process or HTTP service).

### 1.2 Two ways to implement a plugin

| Type | Language | Where it runs | When to use |
|------|----------|---------------|-------------|
| **Built-in** | Python only | In-process with Core | Fast integration, no extra process, use Python libs (e.g. Weather, News, Mail). |
| **External** | Any (Node.js, Go, Java, Rust, etc.) | Separate process or HTTP service | Existing service, different language, or independent deployment. |

Both use the same **run contract**: Core sends a **PluginRequest** (user input, context, optional capability_id and parameters) and gets a **PluginResult** (success, text, error). Built-in plugins are invoked by `await plugin.run()` (or a capability method); external plugins are invoked by **HTTP POST** (type: http) or **subprocess stdin/stdout** (type: subprocess).

---

## 2. Built-in Python plugin

A **built-in** plugin lives in the **plugins** folder, is written in **Python**, and runs **in-process** with the Core.

### 2.1 Folder structure

```
plugins/
  MyPlugin/
    plugin.yaml    # Manifest: id, name, description, type: inline, capabilities
    config.yml     # Runtime config (API keys, defaults)
    plugin.py      # Python class extending BasePlugin
```

### 2.2 Manifest: plugin.yaml

```yaml
id: my_plugin                    # Unique id; used in route_to_plugin(plugin_id)
name: My Plugin                  # Human-readable name
description: Short description for LLM routing. Be specific so the LLM knows when to select this plugin (e.g. "Current weather for a location. Use when the user asks about weather, temperature, or forecast.")

type: inline                     # Must be "inline" for built-in Python plugins

config:
  config_file: config.yml        # Optional; plugin loads this for runtime config

capabilities:                    # Optional; if present, Core can call by capability_id
  - id: do_something             # Must match an async method name on your plugin class
    name: Do Something
    description: What this capability does.
    parameters:
      - name: param1
        type: string
        required: true
        description: What this parameter is for.
    output_description: "What the capability returns"
    post_process: true           # If true, Core runs LLM on output before sending to user
    post_process_prompt: "Summarize for the user."
```

- **id** (required): Stable plugin id; the LLM uses it in `route_to_plugin(plugin_id)`.
- **description**: Used for routing and (optionally) vector search; be clear and specific.
- **type: inline**: Tells Core to load the Python class from this folder.
- **capabilities**: Optional list of capabilities; each **id** should match an **async** method on your plugin class (e.g. `do_something` → `async def do_something(self): ...`). If you omit capabilities, Core calls **run()** only.

### 2.3 Config: config.yml

Runtime configuration (API keys, default city, etc.). Your plugin loads it in `__init__` or `initialize()`.

```yaml
# Example (Weather)
city: Beijing
api_key: "your-api-key"
```

Use **config_key** in capability parameters to fill values from this config when the user does not provide them (see docs_design/PluginParameterCollection.md).

### 2.4 Python class: plugin.py

Your plugin must extend **BasePlugin** (or **SchedulerPlugin** if you only need a simple async `run()`).

```python
from base.BasePlugin import BasePlugin
from core.coreInterface import CoreInterface

class MyPlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        # Load config from plugins/MyPlugin/config.yml
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.yml")
        if os.path.exists(config_path):
            self.config = Util().load_yml_config(config_path)
        else:
            self.config = {}

    async def run(self):
        """Called when the user message is routed to this plugin (no capability_id)."""
        # Use self.user_input, self.promptRequest
        result = await self.do_work()
        # Send reply: Core will deliver to the channel
        await self.coreInst.send_response_for_plugin(result, self.promptRequest)
        # Or: return a string and let Core send it (and optionally post_process)
        return result

    async def do_something(self):
        """Called when route_to_plugin(plugin_id, capability_id="do_something")."""
        params = (self.promptRequest.request_metadata or {}).get("capability_parameters") or {}
        param1 = params.get("param1", "")
        # ... do work ...
        return "Result text"
```

- **coreInst**: Core interface; use `send_response_for_plugin(response, self.promptRequest)` or `send_response_to_request_channel(response, self.promptRequest)` to send the reply to the user.
- **user_input**: Raw user message text when the plugin was invoked.
- **promptRequest**: Full request (user_id, channel_name, etc.); use for context or to send the reply to the right channel.
- **run()**: Invoked when the LLM routes to this plugin without a specific capability (or as the default entry). You can **return** a string (Core sends it; if capability has `post_process: true`, Core runs the LLM on it first) or **send** via `coreInst.send_response_for_plugin(...)` and return without a value.
- **Capability methods**: If you declare capabilities, implement an **async** method per capability **id**. Core will call it when `route_to_plugin(plugin_id, capability_id="do_something")` is used.

### 2.5 Discovery and loading

- Core scans **plugins/** on startup (and optionally on hot-reload).
- For each subfolder, Core looks for **plugin.yaml** (or plugin.json). If present and **type: inline**, it loads the Python class from **plugin.py** (convention: module `plugins.<folder>.plugin`, class inferred or from manifest).
- If there is no plugin.yaml but there is **config.yml** and a **.py** file with a **BasePlugin** subclass, Core treats it as **inline** (legacy) and derives id/description from config.yml. Prefer adding **plugin.yaml** with an **id** for stable routing.

### 2.6 Example: Weather plugin

See **plugins/Weather/**: `plugin.yaml` (id: weather, type: inline, capabilities fetch_weather), `config.yml` (city, api_key), `plugin.py` (WeatherPlugin extends SchedulerPlugin, implements `async def run()` and `async def fetch_weather()`). Core routes “what’s the weather?” to the Weather plugin and may call `fetch_weather` with parameters (city, district) and **post_process** the result with the LLM.

---

## 3. External plugin (other languages: Go, Java, Node.js)

External plugins run in a **separate process** or as an **HTTP service**. They can be written in **any language**. Core communicates with them via a **PluginRequest** / **PluginResult** contract.

### 3.1 Two ways to register an external plugin

| Method | How | When to use |
|--------|-----|-------------|
| **Folder + manifest** | Put a folder under **plugins/** with **plugin.yaml** and **type: http** (or **type: subprocess**). Core discovers it on scan. | Plugin code lives in the repo or a known path; you want Core to discover it automatically. |
| **Registration API** | Your plugin (or a script) calls **POST /api/plugins/register** with a descriptor (id, name, description, health_check_url, type, config). | Plugin runs elsewhere (different host, different repo); you register at runtime. |

Both require a **health_check_url** for external plugins registered via API (so Core can verify the plugin is alive). Folder-based external plugins define **config** in the manifest (e.g. base_url, path, timeout_sec for http).

### 3.2 Type: http (HTTP server)

Your plugin runs an **HTTP server**. Core **POST**s a **PluginRequest** (JSON) to your endpoint and expects a **PluginResult** (JSON) in the response body.

**Contract**

- **Endpoint**: Any path you choose; typical is **POST /run** (or configure **config.path** in the manifest).
- **Request body**: **PluginRequest** (JSON):
  - `request_id`, `plugin_id`, `user_input`, `user_id`, `user_name`, `channel_name`, `channel_type`, `app_id`
  - `metadata`, `chat_context` (optional)
  - **capability_id** (optional): which capability to run (e.g. `get_quote`, `get_time`)
  - **capability_parameters** (optional): object with parameter names and values
- **Response body**: **PluginResult** (JSON):
  - `request_id`, `plugin_id`, `success` (true/false), `text` (reply to user), `error` (if success false), `metadata`

**Health check**: Expose **GET /health** (or another URL you declare as **health_check_url**). Return 2xx when the plugin is ready. Core may call this on registration and periodically.

**Manifest (folder-based)** example:

```yaml
id: quote
name: Quote Plugin
description: Returns random inspirational quotes. Use when the user asks for a quote.
type: http
config:
  base_url: http://127.0.0.1:3101
  path: /run
  timeout_sec: 30
```

**Registration (API)** example: POST to `http://<core_host>:9000/api/plugins/register` with a body that includes **plugin_id**, **name**, **description**, **health_check_url** (e.g. `http://127.0.0.1:3101/health`), **type: "http"**, **config** (base_url, path, timeout_sec). See **base/base.py** (ExternalPluginRegisterRequest) and **docs_design/PluginStandard.md** §3.

**Implementing the server (any language)**

1. Start an HTTP server listening on a port (e.g. 3101).
2. **GET /health**: Return 200 OK (or 200 + JSON `{"status":"ok"}`).
3. **POST /run** (or your path): Read JSON body → parse as PluginRequest. Use **capability_id** and **capability_parameters** to dispatch to your logic. Compute the reply text, then respond with 200 and JSON body = PluginResult (`success: true`, `text: "..."`).

**Examples in this repo**

- **Python**: `examples/external_plugins/quote/server.py`, `examples/external_plugins/time/server.py` (FastAPI; POST /run, GET /health).
- **Node.js**: `examples/external_plugins/quote-node/server.js` (plain Node.js http; POST /run, GET /health).
- **Go**: `examples/external_plugins/time-go/main.go` (stdlib HTTP; POST /run, GET /health).
- **Java**: `examples/external_plugins/quote-java/` (com.sun.net.httpserver; POST /run, GET /health).

See **examples/external_plugins/README.md** for run and register instructions.

### 3.3 Type: subprocess

Your plugin is a **standalone program**. Core **spawns** it (e.g. `node plugin.js`, `go run main.go`), writes **one PluginRequest** (JSON) to the process **stdin**, and reads **one PluginResult** (JSON) from **stdout**.

**Contract**

- **Stdin**: One JSON object = **PluginRequest** (same fields as HTTP).
- **Stdout**: One JSON object = **PluginResult** (same as HTTP response body).
- **Exit code**: 0 on success. Core may treat non‑zero as failure and use stderr for logging.

**Manifest (folder-based)** example:

```yaml
id: weather
name: Weather
description: Current weather for a configured city.
type: subprocess
config:
  command: node
  args: ["plugin.js"]
  timeout_sec: 15
```

Core runs `node plugin.js`, sends PluginRequest JSON to stdin, and parses PluginResult JSON from stdout. **Any language** that can read JSON from stdin and write JSON to stdout works (Node.js, Python, Go, Java, Rust, etc.).

### 3.4 Request/response schema (PluginRequest / PluginResult)

**PluginRequest** (JSON, same for http and subprocess):

```json
{
  "request_id": "string",
  "plugin_id": "string",
  "user_input": "string",
  "user_id": "string",
  "user_name": "string",
  "channel_name": "string",
  "channel_type": "string",
  "app_id": "string",
  "chat_context": "string or null",
  "metadata": {},
  "capability_id": "string or null",
  "capability_parameters": {}
}
```

**PluginResult** (JSON):

```json
{
  "request_id": "string",
  "plugin_id": "string",
  "success": true,
  "text": "Reply to the user",
  "error": null,
  "metadata": {}
}
```

On failure, set **success: false** and **error: "message"**. Core will surface the error to the user (or log it).

---

## 4. MCP (Model Context Protocol)

**MCP** is a standard for exposing **tools** and **resources** to LLM applications. HomeClaw supports two ways for plugins to work with MCP:

1. **Plugin as MCP server** (type: mcp) — Core runs an MCP **client** and calls the plugin’s MCP **tools** (e.g. a single “handle_request” tool). The plugin is an MCP server written in any language.
2. **Plugin uses MCP** — Any plugin (built-in or external) can **use MCP clients** inside its own code to call **other** MCP servers (e.g. company APIs, databases, external tools). This is an implementation detail of the plugin; Core does not need to know about those MCP servers.

### 4.1 Plugin as MCP server (type: mcp)

**Status**: **Planned**; not yet implemented in Core. Use **type: http** or **type: subprocess** for now. The design below is the intended contract when MCP support is added.

**Idea**: Your plugin runs an **MCP server** (stdio or SSE). Core runs an MCP **client**, connects to your server, and calls a **designated tool** (e.g. `handle_request`) with the current user input (and optional context). The tool’s return value (text or structured) is the plugin result that Core sends to the user.

**Manifest (future)** example:

```yaml
id: filesystem-mcp
name: Filesystem MCP
description: Browse and edit files via MCP tools.
type: mcp
config:
  transport: stdio
  command: npx
  args: ["-y", "@modelcontextprotocol/server-filesystem", "/allowed/path"]
  timeout_sec: 60
```

- **transport: stdio**: Core spawns `command` + `args` and communicates via stdin/stdout using MCP JSON-RPC.
- **transport: sse**: Core connects to a **base_url** (e.g. `http://127.0.0.1:3100/sse`) and uses MCP over SSE.

**Run flow (when implemented)**: Core connects to the MCP server, lists tools, and calls the designated tool (e.g. `handle_request`) with a payload such as `{ "user_input": "...", "context": "..." }`. The tool’s return value is used as the plugin result text. This allows **any MCP server** that implements the expected tool to act as a HomeClaw plugin in any language.

**Current code**: In **base/PluginManager.py**, when **type** is **mcp**, `run_external_plugin` returns: *"Error: MCP plugins not yet implemented. Use type http or subprocess for now."* So today you must implement an external plugin as **http** or **subprocess**; MCP as a plugin type will be added in a future release.

### 4.2 Plugin uses MCP (internal use)

**Any** plugin (built-in Python or external in Go/Java/Node.js) can **use MCP clients** inside its own implementation to talk to **other** MCP servers. For example:

- A **built-in** Python plugin could use an MCP client library (e.g. `mcp` package) to call a company-internal MCP server that exposes “query inventory” or “create ticket.”
- An **external** Node.js plugin could run an MCP client and call a database MCP server before returning a PluginResult to Core.

Core does **not** need to know about these MCP servers. The plugin:

1. Receives the usual **PluginRequest** (from Core via `run()` or HTTP/subprocess).
2. Inside its logic, uses an MCP client to call one or more MCP servers (tools/resources).
3. Combines the results and returns a **PluginResult** (or sends the response to the channel).

This gives you “do anything possible” inside the plugin while keeping the Core ↔ plugin contract simple (PluginRequest / PluginResult). For more on MCP, see [Model Context Protocol](https://modelcontextprotocol.io/) and **docs_design/PluginStandard.md** §7.

---

## 5. Summary

| What you want | How |
|---------------|-----|
| **Built-in Python plugin** | Create **plugins/MyPlugin/** with **plugin.yaml** (id, description, type: inline, capabilities), **config.yml**, and **plugin.py** (subclass BasePlugin, implement `run()` and/or capability methods). Core discovers it on scan. |
| **External plugin in Go / Java / Node.js** | Run an **HTTP server** that accepts **POST /run** (PluginRequest JSON) and returns **PluginResult** JSON, and **GET /health** (2xx). Register via **folder** (plugin.yaml with type: http + config.base_url) or **POST /api/plugins/register**. Alternatively, use **type: subprocess** and read PluginRequest from stdin, write PluginResult to stdout. |
| **Plugin as MCP server** | **Not yet implemented.** When added, use **type: mcp** in the manifest; your process runs an MCP server; Core will connect as MCP client and call your designated tool. Today use **http** or **subprocess**. |
| **Plugin uses MCP** | In your plugin code (any type), use an MCP **client** to call other MCP servers (APIs, DBs, tools). No change to the Core ↔ plugin contract. |

---

## 6. References

- **Plugin standard (manifest, run contract, registration API)**: **docs_design/PluginStandard.md**
- **Registration schema and capabilities**: **docs_design/PluginRegistration.md**
- **Plugins user guide and parameter collection**: **docs_design/PluginsGuide.md**
- **Run and test plugins**: **docs_design/RunAndTestPlugins.md**
- **External plugin examples**: **examples/external_plugins/** (Python, Node.js, Go, Java) and **examples/external_plugins/README.md**
- **Built-in example**: **plugins/Weather/** (plugin.yaml, config.yml, plugin.py)
- **Base classes**: **base/BasePlugin.py**, **base/PluginManager.py**, **base/base.py** (PluginRequest, PluginResult)
