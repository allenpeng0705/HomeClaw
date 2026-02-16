# HomeClaw Plugin Standard

This document defines a **language-agnostic plugin standard** for HomeClaw: registration, discovery, run contract, and optional **MCP (Model Context Protocol)** integration so plugins can extend HomeClaw in any language and use MCP to "do anything possible."

---

## 1. Goals

1. **Registration** – Plugins declare themselves via a **manifest**; Core discovers and registers them.
2. **Find plugin** – Core (and the LLM via routing) can find plugins by **id** or by **description** (e.g. vector search or list).
3. **Work and return result** – A clear **run contract**: Core sends a request (user input, context); the plugin runs and returns a result (or sends the response to the channel).
4. **One standard, any language** – Plugins can be implemented in **Python, Node.js, Java, or any language** by following the same manifest and run contract.
5. **MCP** – Plugins may **expose** an MCP server (Core calls the plugin’s tools) or **use** MCP clients internally to extend capability.

**Tools vs plugins.** In HomeClaw, **tools** are built-in and general-purpose (e.g. read file, web search). They are the **base layer** that **skills** use. **Plugins** are **feature-oriented**: each plugin does **one specific thing** (e.g. send email, get weather, post to Slack). Tools and plugins are different layers; they do not share a unified definition.

**Unified plugin registration.** The **same** registration definition is used for built-in and external plugins: the plugin tells Core (1) what **capabilities** it exposes (functions for built-in, REST APIs for external), (2) what **parameters** each capability needs (name, type, required/optional), (3) what **output** it returns, (4) whether Core should **post-process** the output with the LLM (and optional prompt) or send to the channel directly. All plugin info is persisted in **database and vector database** (like skills); **RAG** finds the most relevant plugins by embedding, so only those are injected into the system prompt (avoiding context length limits). See **docs/PluginRegistration.md** for the full schema (capabilities, parameters, post_process, persistence, RAG flow).

---

## 2. Built-in vs external plugins

HomeClaw defines **two categories** of plugins:

| Category | Who registers | Where | Language | How Core discovers |
|----------|----------------|-------|----------|----------------------|
| **Built-in** | PluginManager (scan) | **plugins** folder | Python only | Scan folders; load Python class; hot-reload |
| **External** | Plugin (calls Core API) | Anywhere (remote process) | Any (Node.js, Java, Go, Rust, C, C++, etc.) | **Core provides a registration API**; plugin POSTs its descriptor |

- **Built-in plugins** live in the **plugins** folder. Core scans that folder, loads Python `BasePlugin` subclasses, and registers them. Each built-in plugin must have a **plugin id** (in `plugin.yaml` or `config.yml`). Only Python plugins are supported; they run in-process with Core and can be hot-reloaded. **No** registration API is used for built-in plugins.
- **External plugins** run as separate processes (or remote services). They **call Core** to register: `POST /api/plugins/register` with a descriptor. They must provide a **health check URL** so Core can verify they are running. They can be written in any language. Core does **not** scan folders for external plugins; registration is entirely via the API.

---

## 3. Core registration API (external plugins only)

Core exposes a **registration API** that external plugins call to register themselves. Built-in plugins do **not** use this API.

### 3.1 Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/plugins/register` | Register an external plugin (body = descriptor). Returns `{ "plugin_id", "registered": true }` or error. |
| `POST` | `/api/plugins/unregister` | Unregister by `plugin_id` (body: `{ "plugin_id": "..." }`). Optional. |
| `GET` | `/api/plugins/health/{plugin_id}` | Core calls the plugin health URL and returns `{ "ok": true/false }` (proxy of plugin health). |

### 3.2 Registration request body

The plugin sends a JSON body that matches **ExternalPluginRegisterRequest** (see base/base.py). Required and optional fields:

- **plugin_id** (string, required) – Unique id (e.g. `weather`, `slack-bot`). Used in `route_to_plugin(plugin_id)`.
- **name** (string, required) – Human-readable name.
- **description** (string, required) – Short description for LLM routing (and prompt). Should clearly state when to select this plugin.
- **description_long** (string, optional) – Longer text for **embedding-based discovery** (like skills). If present, Core can sync it to a plugin vector store and use it for similarity search when selecting plugins.
- **health_check_url** (string, required) – HTTP URL Core will call (GET) to verify the plugin is alive. Should return 2xx when healthy.
- **type** (string, required) – One of `http`, `subprocess`, `mcp`. For `http`, the plugin runs its own server; Core POSTs PluginRequest to it.
- **config** (object, required) – Type-specific config (e.g. for `http`: `base_url`, `path`, `timeout_sec`).
- **tools** (array, optional) – If omitted, the plugin is a single entry point: Core sends PluginRequest and gets PluginResult. Optional metadata for future use (plugins are feature-oriented and do one specific thing; they are not the same as Core tools).

### 3.3 Health check

- On registration, Core may optionally call `health_check_url` once to verify the plugin is reachable.
- Core can periodically (or on-demand via `GET /api/plugins/health/{plugin_id}`) call the plugin `health_check_url`. If the GET fails or returns non-2xx, the plugin can be marked unhealthy and excluded from routing. At minimum, the URL is stored and used for on-demand health checks.

---

## 4. Plugin manifest (built-in and folder-based external)

Every **built-in** plugin (and any plugin discovered by folder scan) is described by a **manifest**. Folder-based external plugins (http/subprocess/mcp) also use a manifest in the folder; **API-registered** external plugins do not use a manifest (they send the descriptor in the registration body).

**Location:** `plugins/<plugin_id>/plugin.yaml` (or `plugin.json`). Alternative: single `plugins/registry.yaml` listing plugins by path or URL.

**Recommended: per-plugin manifest** in the plugin folder.

### 4.1 Manifest schema (plugin.yaml)

```yaml
# Required (including for built-in / inline plugins)
id: string              # Unique plugin id (e.g. "weather", "mail"). Used in route_to_plugin(plugin_id). Built-in plugins must set this in plugin.yaml or config.yml.
name: string            # Human-readable name (e.g. "Weather Plugin")
description: string     # Short description for LLM routing (e.g. "Current weather for a configured city")

# Plugin type: how Core runs the plugin
type: inline | subprocess | http | mcp

# Type-specific config (see §3)
config: {}
  # inline: (optional) config_file path relative to plugin dir; default config.yml
  # subprocess: command, args, env, timeout_sec
  # http: base_url, path (e.g. /run), timeout_sec
  # mcp: transport (stdio | sse), command (for stdio), or base_url (for SSE)

# Optional: capabilities (same schema for built-in and external). See docs/PluginRegistration.md.
# capabilities:
#   - id: fetch_weather
#     name: Get current weather
#     description: ...
#     parameters: [{ name, type, required, description }]
#     output_description: ...
#     post_process: true   # Core runs LLM on output before sending to channel
#     post_process_prompt: "Reorganize for the user and suggest tips."
# Optional
version: string          # e.g. "1.0.0"
keywords: [string]       # Optional tags for discovery
description_long: string # Longer text for embedding (RAG); same as skills.
```

**Example (Python inline – current style):**

```yaml
id: mail
name: Mail Plugin
description: Send email. Select when the user wants to send an email.
type: inline
config:
  config_file: config.yml
```

**Example (Node.js HTTP plugin):**

```yaml
id: slack-bot
name: Slack Plugin
description: Post messages to Slack and read channel history.
type: http
config:
  base_url: http://127.0.0.1:3100
  path: /run
  timeout_sec: 30
```

**Example (Any language – subprocess):**

```yaml
id: weather
name: Weather
description: Current weather for a configured city.
type: subprocess
config:
  command: node
  args: ["plugin.js"]
  timeout_sec: 15
  # Request passed via stdin (JSON); result read from stdout (JSON)
```

**Example (MCP server plugin):**

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

---

## 5. Run contract by type

Core sends a **PluginRequest** and receives a **PluginResult** (or the plugin sends the response to the channel itself). The exact wire format depends on the type.

### 5.1 Common request/response shape

**PluginRequest** (JSON):

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
  "chat_context": "string (optional, recent messages)",
  "metadata": {}
}
```

**PluginResult** (JSON, when plugin returns to Core):

```json
{
  "request_id": "string",
  "plugin_id": "string",
  "success": true | false,
  "text": "string (reply to user)",
  "error": "string (if success false)",
  "metadata": {}
}
```

Plugins can either **return** this result to Core (subprocess stdout, HTTP response body) or **push** the reply themselves (inline/HTTP plugin can call Core’s send_response API if it has Core’s URL and request_id).

### 5.2 Type: inline (Python in-process)

- **Discovery:** Core scans the **plugins** folder for subfolders that contain `plugin.yaml` with `type: inline` **or** (for backward compatibility) a `config.yml` + Python file defining a `BasePlugin` subclass. If manifest exists, load class from `plugin_module` (optional in manifest) or by convention `plugins.<folder>.plugin`.
- **Registration:** Load Python class, call `initialize()`, register by **plugin id** and description. Built-in plugins must have an **id** in `plugin.yaml` or `config.yml` (e.g. `id: mail`).
- **Run:** Core sets `plugin.promptRequest`, `plugin.user_input`, then `await plugin.run()`. Plugin uses `coreInst.send_response_to_request_channel()` or similar to send the reply. **No** separate request/result JSON; in-process only.

**Backward compatibility:** If a folder has `config.yml` and a `.py` file with `BasePlugin` but **no** `plugin.yaml`, treat as **inline** with id/description from config.yml. Config should include `id` so the plugin has a stable plugin id.

### 5.3 Type: subprocess

- **Discovery:** Manifest `type: subprocess` with `config.command` and optional `config.args`.
- **Registration:** Store manifest (id, name, description, type, config). No process started yet.
- **Run:**  
  1. Core builds **PluginRequest** JSON.  
  2. Core spawns subprocess: `command` + `args` (e.g. `node plugin.js`).  
  3. Core writes PluginRequest JSON to process **stdin** (single line or newline-delimited JSON).  
  4. Process runs, then writes **PluginResult** JSON to **stdout** (single line).  
  5. Core reads stdout, parses PluginResult, then sends `result.text` to the channel (or handles `result.error`).  
  6. Timeout: `config.timeout_sec` or default (e.g. 30s); on timeout, kill process and return error to user.

**Contract for plugin process:** Read one JSON object from stdin (PluginRequest). Write one JSON object to stdout (PluginResult). Exit code 0 on success. Any language can implement this (Node.js, Java, Python, Go, etc.).

### 5.4 Type: http

- **Discovery:** Manifest `type: http` with `config.base_url` and optional `config.path` (default `/run`).
- **Registration:** Store manifest. No server started by Core; the plugin runs as a **separate HTTP server** (any language).
- **Run:**  
  1. Core builds PluginRequest JSON.  
  2. Core `POST` to `{base_url}{path}` (e.g. `http://127.0.0.1:3100/run`) with body PluginRequest, `Content-Type: application/json`.  
  3. Plugin server handles request, does work, returns response body = **PluginResult** JSON.  
  4. Core parses response, sends `result.text` to the channel.  
  5. Timeout: `config.timeout_sec` or default.

**Contract for plugin server:** Endpoint `POST /run` (or configured path) accepts JSON body = PluginRequest, returns JSON body = PluginResult. Status 200 for success; 4xx/5xx with body `{ "success": false, "error": "..." }` for failure.

### 5.5 Type: mcp

- **Discovery:** Manifest `type: mcp` with `config.transport` (stdio | sse) and either `command`+`args` (stdio) or `base_url` (SSE).
- **Registration:** Store manifest. Core may optionally **connect** to the MCP server at startup (or on first use) to list tools.
- **Run:**  
  - **Option A (recommended):** Plugin is an MCP server that exposes a **single tool** (e.g. `handle_request`) taking the user input (and optional context). Core, as MCP client, calls that tool with the request payload and uses the tool result as the plugin result text.  
  - **Option B:** Plugin exposes **multiple MCP tools** (e.g. `get_weather`, `get_forecast`). Core can list tools and either call one designated “main” tool with the full request, or the LLM could choose which MCP tool to call (then the plugin is more like a “tool pack”). For simplicity, Option A (one main tool per plugin) is the standard; Option B can be a future extension.

**MCP stdio:** Core spawns subprocess `command` + `args`; communicates via stdin/stdout using MCP JSON-RPC. Core calls `tools/call` for the plugin’s handle tool with request payload.  
**MCP SSE:** Core connects to `base_url` (e.g. `http://127.0.0.1:3100/sse`); same MCP JSON-RPC over SSE. No process lifecycle managed by Core.

**Result:** The MCP tool’s return value (text or structured content) is treated as the plugin result and sent to the user.

---

## 6. Registration and discovery flow

1. **Scan** – On startup (and optionally on a timer), Core scans `plugins_dir` (e.g. `plugins/`). For each subfolder:
   - If **plugin.yaml** (or plugin.json) exists: parse manifest → **id**, **name**, **description**, **type**, **config**.
   - Else if **config.yml** + a `.py` file with `BasePlugin`: treat as **inline** (legacy), derive id/description from config.yml.
2. **Register** – For each discovered plugin: store in PluginManager by **id** (and optionally by description for search). For **inline**, also load the Python class and call `initialize()`.
3. **Find** – `get_plugin_by_id(plugin_id)` returns the plugin (inline = Python instance; http/subprocess/mcp = manifest + config). For routing, Core (and the LLM) need the list of **id** + **description**; optional vector search for large plugin sets.
4. **Run** – When the LLM calls `route_to_plugin(plugin_id)`:
   - **inline:** `await plugin.run()` as today.
   - **subprocess:** Build PluginRequest → spawn process → write stdin → read stdout → parse PluginResult → send to channel.
   - **http:** Build PluginRequest → POST to plugin URL → parse response → send to channel.
   - **mcp:** Connect (if not already), call the plugin’s handle tool with request → use tool result → send to channel.

---

## 7. MCP: extend HomeClaw and “do anything possible”

**Why MCP:** Model Context Protocol is a standard for exposing **tools** and **resources** to LLM applications. A plugin that is an **MCP server** can expose tools (e.g. read files, call APIs, run code). Core can then call those tools on behalf of the user, so the plugin **extends** HomeClaw’s capability without implementing everything in Core.

**Two roles:**

1. **Plugin as MCP server** – The plugin process (Node.js, Python, etc.) runs an MCP server. Core runs an MCP client and calls the plugin’s tools. The plugin’s “run” = Core invoking one or more of its MCP tools with the current request. This is the **type: mcp** plugin.
2. **Plugin uses MCP** – The plugin (any type) can **internally** use MCP clients to talk to other MCP servers (e.g. company APIs, databases, external tools). That’s an implementation detail of the plugin; the standard doesn’t require Core to know about those MCP servers. The plugin just needs to be able to run (subprocess/http) and return a result.

**Standard contract for type: mcp**

- Plugin manifest has `type: mcp` and transport config (stdio or SSE).
- Core starts or connects to the MCP server.
- Core calls a **designated tool** (e.g. `handle_request`) with a single argument (e.g. the serialized PluginRequest or `{ "user_input": "...", "context": "..." }`).
- The tool’s return value (string or structured) is the plugin result sent to the user.

This way, **any MCP server** that implements `handle_request` (or a configured tool name) can be a HomeClaw plugin: written in any language, using any stack, and exposing arbitrary tools/resources via MCP to “do anything possible.”

---

## 8. Summary

| Aspect | Content |
|--------|--------|
| **Manifest** | `plugin.yaml` (or plugin.json) per plugin: id, name, description, type (inline \| subprocess \| http \| mcp), config. |
| **Built-in vs external** | Built-in = Python only, in **plugins** folder; each has a **plugin id** (manifest or config.yml). External = any language, register via Core API; health_check_url required. |
| **Discovery** | Built-in: scan **plugins** folder; parse manifest or config.yml + Python. External: registration API only. |
| **Registration** | Built-in: store by id; load Python class. External: plugin POSTs descriptor; Core stores and checks health. |
| **Find** | By id; optional list/search by description. |
| **Run** | Inline = in-process `plugin.run()`; subprocess = stdin/stdout JSON; http = POST request/response; mcp = MCP client calls plugin tool. |
| **Language** | Built-in = Python only; external = any language. |
| **MCP** | Plugin can be an MCP server (type: mcp) or use MCP internally; Core can call plugin’s MCP tools to extend capability. |

Implementing this standard in Core: (1) **Built-in**: manifest parsing and type-aware registration; keep inline (Python) behavior and hot-reload. (2) **External**: Core exposes `POST /api/plugins/register`, `POST /api/plugins/unregister`, `GET /api/plugins/health/{plugin_id}`; PluginManager stores API-registered plugins (persisted to `config/external_plugins.json`) and does not clear them on folder scan. (3) **Health check**: each external plugin provides `health_check_url`; Core can call it (GET) to verify the plugin is running. (4) Runners for subprocess and http (and optionally mcp client) so plugins can be implemented in any language and use MCP.
