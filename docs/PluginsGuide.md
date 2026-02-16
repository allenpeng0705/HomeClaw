# HomeClaw Plugins: A Complete Guide

This guide explains **what plugins are**, **how to write them** (built-in and external), and **how to use them**. Whether you want to add a quick Python feature or ship a Node.js service that talks to HomeClaw, this is the place to start.

**Run and test:** For step-by-step instructions on **running and testing** both built-in and external plugins (Core, WebChat, registration, example prompts), see [RunAndTestPlugins.md](RunAndTestPlugins.md).

### Getting Started in 5 Minutes

- **Built-in (Python):** Create `plugins/MyPlugin/` with `plugin.yaml`, `config.yml`, and `plugin.py` (subclass `BasePlugin`, implement `run()` or capability methods). Restart Core; your plugin is live.
- **External (HTTP):** Run a server that accepts POST with `PluginRequest` and returns `PluginResult`. Put a `plugin.yaml` with `type: http` in a folder under `plugins/`, or register via `POST /api/plugins/register`.
- **Parameters:** Use `profile_key` and `config_key` in capability parameters so Core can fill values from the user profile and config. Use `confirm_if_uncertain` when you need the user to confirm before proceeding.

---

## Table of Contents

1. [What Are Plugins?](#1-what-are-plugins)
2. [Built-in Plugins (Python)](#2-built-in-plugins-python)
3. [External Plugins (Any Language)](#3-external-plugins-any-language)
4. [Parameter Collection and Configuration](#4-parameter-collection-and-configuration)
5. [How Plugins Are Used](#5-how-plugins-are-used)
6. [Quick Reference](#6-quick-reference)

---

## 1. What Are Plugins?

### Plugins vs Tools vs Skills

| Layer | Purpose | Example |
|-------|---------|---------|
| **Tools** | General-purpose, atomic operations (file read, web search, reminders) | `file_read`, `memory_search`, `remind_me` |
| **Skills** | Application workflows; LLM uses tools to accomplish tasks | "Social media agent" that posts via browser + cron |
| **Plugins** | **Single-feature modules** that do one thing well | Weather, News, Mail, "Buy something" |

Plugins are **feature-oriented**. Each plugin focuses on one capability: fetch weather, send email, post to Slack, place an order. The LLM routes user requests to the right plugin when the intent matches.

### Two Kinds of Plugins

| Type | Language | Where It Runs | When to Choose |
|------|----------|---------------|----------------|
| **Built-in** | Python only | In-process with Core | Fast integration, no extra process, uses Python libs |
| **External** | Any (Node.js, Go, Java, etc.) | Separate process or remote service | Existing service, different language, independent deployment |

---

## 2. Built-in Plugins (Python)

Built-in plugins live in the `plugins/` folder. Core discovers them by scanning subfolders and loading Python classes that extend `BasePlugin`.

### 2.1 Minimum Structure

```
plugins/
  MyPlugin/
    plugin.yaml      # Manifest: id, description, capabilities
    config.yml       # Runtime config (API keys, defaults)
    plugin.py        # Python class with run() and/or capability methods
```

### 2.2 The Manifest: plugin.yaml

The manifest tells Core *what* your plugin does and *how* to call it.

```yaml
id: my_plugin              # Unique id; used in route_to_plugin(plugin_id)
name: My Plugin            # Human-readable name
description: Short description for LLM routing. Be specific: "Current weather for a location. Use when the user asks about weather, temperature, or forecast."

type: inline               # Must be "inline" for Python built-in plugins

config:
  config_file: config.yml  # Optional; plugin loads this for runtime config

capabilities:
  - id: do_something       # Must match a method name in your plugin class
    name: Do Something
    description: What this capability does; used by the LLM to choose parameters.
    parameters:
      - name: param1
        type: string
        required: true
        description: What this parameter is for.
    output_description: "What the capability returns (plain text or JSON schema)"
    post_process: true     # If true, Core runs LLM on output before sending to user
    post_process_prompt: "Summarize and refine for the user."
```

**Important:** Each capability `id` must correspond to an `async` method on your plugin class. If the LLM calls `route_to_plugin(plugin_id="my_plugin", capability_id="do_something")`, Core will call `await plugin.do_something()`.

### 2.3 The Python Class: plugin.py

```python
from base.BasePlugin import BasePlugin
from core.coreInterface import CoreInterface

class MyPlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        # Load config (or let initialize do it)
        import os
        config_path = os.path.join(os.path.dirname(__file__), "config.yml")
        self.config = Util().load_yml_config(config_path) if os.path.exists(config_path) else {}

    def initialize(self):
        if self.initialized:
            return
        super().initialize()
        self.initialized = True

    async def do_something(self):
        """Called when LLM routes to capability do_something."""
        param1 = self.config.get("param1") or ""
        # Do your work here
        return "Result text to send to the user"

    async def run(self):
        """Default entry when no capability_id is specified. Often delegates to first capability."""
        return await self.do_something()
```

- **`coreInst`** — Access to Core: `coreInst.send_response_to_request_channel()`, `coreInst.get_latest_chats()`, etc.
- **`self.config`** — Your runtime config (API keys, defaults). Merged with capability parameters at invoke time.
- **`self.promptRequest`** — The current request (set by Core before `run()` or capability call).
- **`self.user_input`** — The user's message text.

### 2.4 Runtime Config: config.yml

```yaml
# Plugin metadata (optional if in plugin.yaml)
id: my_plugin
description: Same description as in plugin.yaml.

# Your plugin's config
api_key: "your-api-key"
default_city: "Beijing"

# Optional: default values for capability parameters (see §4)
default_parameters:
  city: "Beijing"
use_default_directly_for: [city]
```

### 2.5 Example: Weather Plugin

See `plugins/Weather/` for a full example:

- **plugin.yaml** — Capabilities `fetch_weather` with params `city`, `district`
- **config.yml** — `city`, `district`, `api_key` (and optional `default_parameters`)
- **plugin.py** — `WeatherPlugin(SchedulerPlugin)` with `fetch_weather()` and `run()`

---

## 3. External Plugins (Any Language)

External plugins run as **separate processes** or **HTTP services**. They register with Core via the registration API and receive `PluginRequest`; they return `PluginResult`.

### 3.1 Two Ways to Run External Plugins

| Type | How Core Invokes | Use Case |
|------|------------------|----------|
| **http** | POST request to your server | You run a web server (Express, Fastify, etc.) |
| **subprocess** | Spawn process; JSON via stdin/stdout | CLI tool, script, any language |

### 3.2 Option A: HTTP Plugin

Your plugin runs an HTTP server. Core POSTs a `PluginRequest` and expects a `PluginResult` in the response body.

**1. Implement the HTTP endpoint**

```javascript
// Node.js example
const express = require('express');
const app = express();

app.use(express.json());

app.post('/run', (req, res) => {
  const { plugin_id, user_input, user_id, metadata } = req.body;
  const params = metadata?.capability_parameters || {};
  
  // Do your work
  const result = doSomething(params);
  
  res.json({
    request_id: req.body.request_id,
    plugin_id,
    success: true,
    text: result,
  });
});

app.get('/health', (req, res) => res.status(200).send('OK'));

app.listen(3100);
```

**2. Register with Core**

Either put a manifest in a folder under `plugins/`:

```
plugins/
  my-http-plugin/
    plugin.yaml
```

```yaml
id: my-http-plugin
name: My HTTP Plugin
description: Does something useful. Use when the user wants X.
type: http
config:
  base_url: http://127.0.0.1:3100
  path: /run
  timeout_sec: 30
```

Or register via the Core API:

```bash
curl -X POST http://localhost:8000/api/plugins/register \
  -H "Content-Type: application/json" \
  -d '{
    "plugin_id": "my-http-plugin",
    "name": "My HTTP Plugin",
    "description": "Does something useful. Use when the user wants X.",
    "health_check_url": "http://127.0.0.1:3100/health",
    "type": "http",
    "config": {
      "base_url": "http://127.0.0.1:3100",
      "path": "/run",
      "timeout_sec": 30
    }
  }'
```

### 3.3 Option B: Subprocess Plugin

Your plugin is a program that reads JSON from stdin and writes JSON to stdout.

**1. Implement the script**

```javascript
// plugin.js (Node.js)
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });

rl.on('line', (line) => {
  const req = JSON.parse(line);
  const params = req.metadata?.capability_parameters || {};
  const result = doSomething(params);
  console.log(JSON.stringify({
    request_id: req.request_id,
    plugin_id: req.plugin_id,
    success: true,
    text: result,
  }));
});
```

**2. Manifest**

```yaml
id: my-subprocess-plugin
name: My Subprocess Plugin
description: Does something. Use when the user wants X.
type: subprocess
config:
  command: node
  args: ["plugin.js"]
  timeout_sec: 15
```

Core spawns `node plugin.js`, writes one line of JSON (PluginRequest) to stdin, and reads one line of JSON (PluginResult) from stdout.

### 3.4 Request and Result Format

**PluginRequest** (what Core sends):

```json
{
  "request_id": "uuid",
  "plugin_id": "my-plugin",
  "user_input": "User's message",
  "user_id": "user-id",
  "user_name": "User Name",
  "channel_name": "channel",
  "metadata": {
    "capability_id": "do_something",
    "capability_parameters": { "param1": "value1" }
  }
}
```

**PluginResult** (what your plugin returns):

```json
{
  "request_id": "uuid",
  "plugin_id": "my-plugin",
  "success": true,
  "text": "The reply to send to the user",
  "error": null
}
```

On failure: `"success": false, "error": "Error message"`.

---

## 4. Parameter Collection and Configuration

Plugins often need parameters (address, phone, city, etc.) that may be **missing** or **uncertain**. HomeClaw supports:

- **Filling from user profile** (e.g. address, name)
- **Filling from config** (default city, API keys)
- **Asking the user** when missing
- **Confirming with the user** when values come from profile/config and correctness is uncertain

### 4.1 Parameter Sources (Resolution Order)

Before invoking your plugin, Core resolves each parameter in this order:

1. **User message** — Value explicitly provided by the LLM from the current turn (highest confidence)
2. **Profile** — User profile (if param has `profile_key`)
3. **Config** — `default_parameters` or top-level config (if param has `config_key`)

### 4.2 Declaring Parameter Behavior

In your capability parameters:

```yaml
parameters:
  - name: city
    type: string
    required: true
    config_key: city              # Fill from config["city"] or default_parameters["city"] when missing
    description: City name.
  - name: address
    type: string
    required: true
    profile_key: address          # Fill from user profile when missing
    config_key: default_address   # Fallback from config
    confirm_if_uncertain: true    # If value from profile/config, confirm with user before using
    description: Delivery address.
```

| Attribute | Purpose |
|-----------|---------|
| `profile_key` | Map to user profile key (e.g. `address`, `name`, `phone`) |
| `config_key` | Map to `config` or `default_parameters` |
| `confirm_if_uncertain` | When value comes from profile/config, ask user to confirm before invoking |

### 4.3 Using Defaults Directly (No Confirmation)

When you trust preset values, add to **config.yml**:

```yaml
# Use these params from config without asking the user
use_default_directly_for: [city, district, address]
```

Or to trust all defaults:

```yaml
use_defaults_directly: true
```

### 4.4 Flow: Missing or Uncertain Params

- **Missing required param** → Core does **not** invoke the plugin. It returns a message to the LLM: "Ask the user for: address, phone." The LLM asks the user; on the next turn, the user provides values and the LLM calls the plugin again.
- **Uncertain param** (from profile/config, `confirm_if_uncertain: true`) → Same: Core returns "Confirm with the user: address=123 Main St (from profile)." The LLM asks "Is 123 Main St correct?" and proceeds after confirmation.
- **`use_default_directly_for`** → Params in that list are used from config without confirmation.

See **docs/PluginParameterCollection.md** for full design details.

---

## 5. How Plugins Are Used

### 5.1 From the User's Perspective

The user talks to HomeClaw through a channel (Telegram, webchat, etc.). When they say something like "What's the weather in Beijing?" or "Send an email to John", the main LLM:

1. Sees the routing block in the system prompt: "Available plugins: **weather**: Current weather... **mail**: Send email..."
2. Chooses the appropriate plugin and calls the `route_to_plugin` tool.
3. Core invokes the plugin and sends the result back to the user.

The user does not need to know about plugins; they just ask naturally.

### 5.2 From the LLM's Perspective

The LLM has access to a `route_to_plugin` tool:

```
route_to_plugin(plugin_id, capability_id?, parameters?)
```

- **plugin_id** — Required. Must match an available plugin (e.g. `weather`, `news`).
- **capability_id** — Optional. Which capability to call (e.g. `fetch_weather`). If omitted, plugin's default `run()` is used.
- **parameters** — Optional. Key-value params (e.g. `{"city": "Beijing"}`). Core merges these with profile and config.

### 5.3 Scheduling (Built-in Plugins)

Built-in plugins can extend `SchedulerPlugin` to run tasks on a schedule (e.g. daily weather at 8am). Define tasks in **config.yml**:

```yaml
tasks:
  fetch_weather:
    type: fixed
    frequency: daily
    time: "08:00:00"
```

See `plugins/Weather/` and `plugins/News/` for examples.

---

## 6. Quick Reference

### File Layout

```
plugins/
  MyPlugin/
    plugin.yaml    # Manifest: id, name, description, type, capabilities
    config.yml     # Runtime config, default_parameters, use_default_directly_for
    plugin.py      # BasePlugin subclass (built-in only)
```

### Manifest Fields (plugin.yaml)

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Unique plugin id |
| `name` | yes | Human-readable name |
| `description` | yes | Short description for LLM routing |
| `type` | yes | `inline` (built-in) or `http`, `subprocess`, `mcp` (external) |
| `config` | no | Type-specific config |
| `capabilities` | recommended | List of capabilities with parameters |

### Capability Parameter Fields

| Field | Description |
|-------|-------------|
| `name` | Parameter name |
| `type` | `string`, `number`, `boolean`, `object`, `array` |
| `required` | Default `true` |
| `profile_key` | User profile key to fill from |
| `config_key` | Config key to fill from |
| `confirm_if_uncertain` | Confirm with user when value from profile/config |
| `description` | For LLM |

### Config Fields (config.yml)

| Field | Description |
|-------|-------------|
| `default_parameters` | Key-value defaults for params |
| `use_defaults_directly` | Use all defaults without confirmation |
| `use_default_directly_for` | List of params to use from config without confirmation |

### Plugin Author Checklist

**Before shipping a built-in plugin:**

- [ ] `plugin.yaml` has unique `id`, clear `description` (for LLM routing)
- [ ] Each capability `id` matches a method name in your plugin class
- [ ] `config.yml` contains API keys, defaults; add `default_parameters` if you want Core to fill params from config
- [ ] Plugin class extends `BasePlugin` (or `SchedulerPlugin`), implements `initialize()` and `run()` and/or capability methods

**Before shipping an external plugin:**

- [ ] HTTP: `/run` (or configured path) accepts JSON body = `PluginRequest`, returns JSON body = `PluginResult`
- [ ] Subprocess: reads one JSON line from stdin, writes one JSON line to stdout
- [ ] Health endpoint (`/health`) returns 2xx when the plugin is ready
- [ ] Registration includes `health_check_url`, `type`, `config` (base_url/path or command/args)

**For plugins that need user-provided params:**

- [ ] Add `profile_key` or `config_key` to parameters so Core can auto-fill
- [ ] Add `confirm_if_uncertain: true` for sensitive params (address, payment)
- [ ] Add `use_default_directly_for` in config when you trust preset values

---

### Related Documentation

- **PluginStandard.md** — Full standard (manifest, run contract, MCP)
- **PluginRegistration.md** — Unified registration schema, RAG discovery
- **PluginParameterCollection.md** — Parameter resolution, confirmation flow
