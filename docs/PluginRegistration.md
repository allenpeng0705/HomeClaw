# Plugin Registration: Unified Definition and RAG-Based Discovery

This document defines the **unified plugin registration** for HomeClaw: the same definition for built-in and external plugins, persistence in database and vector database (like skills), and RAG-based discovery so the system prompt does not include all plugins (avoiding context length limits).

---

## 1. Goals

1. **Same registration definition** for built-in and external plugins. Built-in plugins do not call the registration API but must provide the same information (via manifest/config). External plugins send this information when they call the registration API.
2. **Plugin tells Core** (a) what **capabilities** it exposes (functions for built-in, REST APIs for external), (b) what **parameters** each capability needs (name, type, required/optional), (c) what **output** it returns, (d) whether Core should **post-process** the output with the LLM (and optional prompt for that) or send to the channel directly.
3. **Persistence** like skills: all plugin registration data is stored in **database** and **vector database**. Embedding is used to find the most relevant plugins; only those are injected into the system prompt (or offered via tools). This avoids exceeding context length.
4. **Flow**: RAG finds relevant plugins → LLM tool selects plugin (and capability/params) → Core calls plugin with registration info → get response → either Core processes with LLM and sends to channel, or send to channel directly.

---

## 2. Tools vs plugins (reminder)

- **Tools** are built-in and general-purpose (read file, web search). They are the base for **skills**.
- **Plugins** are feature-oriented: each plugin does **one specific thing** (e.g. weather, news, mail). They do not share a unified definition with tools.

---

## 3. Unified registration schema (built-in and external)

The registration payload is **100% the same** for both. Only the **source** and **how Core invokes** differ:

- **Built-in**: capabilities = **functions** (e.g. `fetch_weather`, `fetch_latest_news`). Core invokes the Python method.
- **External**: capabilities = **REST APIs** (method + path). Core invokes HTTP.

### 3.1 Plugin level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| **id** | string | yes | Unique plugin id (e.g. `weather`, `news`, `mail`). Used in routing and `route_to_plugin(plugin_id)`. |
| **name** | string | yes | Human-readable name. |
| **description** | string | yes | Short description for LLM routing and for embedding. |
| **description_long** | string | no | Longer text for embedding (RAG). If present, used with description for vector search. |
| **capabilities** | array | yes | List of capabilities (functions or REST APIs). See §3.2. |
| **source** | string | — | Set by Core: `built-in` or `external`. Not sent by plugin. |
| **health_check_url** | string | external only | Required for external plugins. Not used for built-in. |
| **type** | string | external only | `http`, `subprocess`, `mcp`. Not used for built-in. |
| **config** | object | external only | Type-specific config (base_url, path, etc.). Not used for built-in. |

### 3.2 Capability (function or REST API)

Each capability describes one callable: a **function** (built-in) or a **REST API** (external).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| **id** | string | yes | Capability id (e.g. `fetch_weather`, `fetch_latest_news`). |
| **name** | string | yes | Human-readable name. |
| **description** | string | yes | What this capability does; used for routing and tool choice. |
| **parameters** | array | yes | List of parameters. See §3.3. |
| **output_description** | string | no | What the capability returns. Can be plain text or a **JSON** schema/example (e.g. `{"text": "string", "temperature": number}`) to describe structured output. |
| **post_process** | boolean | no | If `true`, Core uses the LLM to process the output before sending to the channel. If `false`, output is sent to the channel directly. Default: `false`. |
| **post_process_prompt** | string | no | When `post_process` is true: description or system-prompt snippet for the LLM to process the output (e.g. "Summarize and refine for the user"). Injected into a system prompt when Core runs the LLM on the plugin output. |
| **method** | string | external only | HTTP method (e.g. `GET`, `POST`) for REST API. |
| **path** | string | external only | Path relative to plugin `base_url` (or full path). |

### 3.3 Parameter

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| **name** | string | yes | Parameter name. |
| **type** | string | yes | `string`, `number`, `boolean`, `object`, `array`. |
| **required** | boolean | no | Default `true`. |
| **default** | any | no | Default value if optional and omitted. |
| **description** | string | no | For LLM/tool schema. |

---

## 4. Persistence: database and vector database (same as skills)

- **Vector database**: Store one vector per plugin. Embedding input = `description` + optional `description_long`. Payload = plugin id, name, short description. Collection name configurable (e.g. `homeclaw_plugins`). Used for **RAG**: given user query, search by similarity and return top-k plugin ids.
- **Database / registry**: Store full registration (id, name, description, description_long, capabilities, source, and for external: health_check_url, type, config). Built-in: source of truth is the **plugins** folder (manifest/config). External: source of truth is the registration API + persisted file (e.g. `config/external_plugins.json`). Optionally, Core can maintain a single **plugin registry** (e.g. SQLite table or JSON file) that merges built-in (from folder) and external (from API) so that full descriptor is always available by id without re-scanning. For parity with skills, the minimum is: vector store for RAG; full descriptor from PluginManager (built-in from folder, external from JSON). An explicit registry DB table can be added later.

**Sync**: On startup (and optionally on a timer), Core (1) loads all plugins (built-in from plugins folder, external from API storage), (2) builds the list of registration descriptors, (3) syncs to the vector store (embed description + description_long, upsert by plugin id). Removed plugins are removed from the vector store.

---

## 5. Flow: RAG → LLM tool → call plugin → post-process or direct

1. **User message** arrives; Core builds context (e.g. for `answer_from_memory`).
2. **RAG**: Core embeds the user query (and optionally conversation context), searches the **plugins vector store**, and retrieves the top-k most relevant plugin ids (same pattern as skills).
3. **Inject into prompt or tools**: Only the retrieved plugins are added to the system prompt (or offered as a tool like `route_to_plugin(plugin_id, capability_id?, parameters?)`). This keeps the prompt small and avoids context length issues.
4. **LLM selects plugin**: The LLM uses the injected list (or the tool) to choose a plugin and, if needed, a capability and parameters.
5. **Core calls plugin**: Using the registration info (from PluginManager or registry), Core invokes the plugin: for built-in, call the Python function; for external, call the REST API (or subprocess/MCP). Parameters are passed as defined in the capability.
6. **Plugin returns result to Core**: Plugins **do not** call Core’s LLM or `send_response_to_*` themselves. They **return** the result (raw text or structured output) to Core. Core then decides what to do with it.
7. **Handle response**: If the capability has `post_process: true`, Core runs the LLM with the plugin output and optional `post_process_prompt` (e.g. as system instruction), then sends the LLM result to the channel. If `post_process: false`, Core sends the plugin output to the channel directly.

---

## 6. Built-in: manifest / config format

Built-in plugins live in the **plugins** folder. Each plugin has:

- **plugin.yaml** (or **plugin.json**): preferred. Contains id, name, description, description_long (optional), **capabilities** (list of capability objects as in §3.2). For inline (Python) plugins, each capability `id` must match a method name (e.g. `fetch_weather`) that Core can call.
- **config.yml**: legacy. Can still define id, description, **parameters** (plugin-level). For the new design, parameters and capabilities should move into **plugin.yaml** under each capability. config.yml can keep scheduling (tasks), API keys, and other runtime config.

Example **plugin.yaml** (built-in, Weather):

```yaml
id: weather
name: Weather Plugin
description: Current weather and forecast for a location. Use when the user asks about weather, temperature, or forecast.
description_long: "Provides current weather, humidity, conditions, wind, AQI. Supports city and district. Use for questions like: what's the weather, will it rain, do I need an umbrella."

capabilities:
  - id: fetch_weather
    name: Get current weather
    description: Returns current weather for a city (and optional district). Includes temperature, humidity, conditions, wind, AQI.
    parameters:
      - name: city
        type: string
        required: true
        description: City name, e.g. Beijing.
      - name: district
        type: string
        required: false
        description: District within the city, e.g. Daxing.
    output_description: '{"text": "plain text weather summary", "temperature": number, "humidity": number, "conditions": string, "aqi": number}'
    post_process: true
    post_process_prompt: "Reorganize the weather information for the user and suggest practical tips (e.g. umbrella, washing car, clothing)."
```

Example **plugin.yaml** (built-in, News):

```yaml
id: news
name: News Plugin
description: Latest news headlines and summaries. Use when the user wants news, headlines, or top stories.
description_long: "Fetches top headlines from configurable sources/categories. Can summarize and refine articles for the user."

capabilities:
  - id: fetch_latest_news
    name: Fetch latest news
    description: Fetches latest news articles; parameters can filter by country, category, sources.
    parameters:
      - name: country
        type: string
        required: false
        description: Country code, e.g. us.
      - name: category
        type: string
        required: false
        description: Category, e.g. business.
      - name: sources
        type: string
        required: false
        description: Source id, e.g. techcrunch.
    output_description: "List of articles (title, content)."
    post_process: true
    post_process_prompt: "Select top 3 latest articles; summarize and refine for the user."
```

**config.yml** for the same plugin can keep: tasks (scheduling), base_url, apiKey, etc. The **parameters** in config.yml that are runtime defaults can stay; the **capabilities** in plugin.yaml define the contract (parameters, post_process, post_process_prompt). Core uses plugin.yaml for registration and config.yml for runtime config (API keys, schedule).

---

## 7. External: registration API payload

External plugins call `POST /api/plugins/register` with a JSON body that matches the same schema. They must include **health_check_url**, **type**, **config**. **capabilities** use **method** and **path** for each REST API. Example:

```json
{
  "plugin_id": "slack-bot",
  "name": "Slack Plugin",
  "description": "Post messages to Slack and read channel history.",
  "description_long": "Integrates with Slack: post messages, list channels, read history. Use when the user wants to send or read Slack messages.",
  "health_check_url": "http://127.0.0.1:3100/health",
  "type": "http",
  "config": { "base_url": "http://127.0.0.1:3100", "path": "/run", "timeout_sec": 30 },
  "capabilities": [
    {
      "id": "post_message",
      "name": "Post message",
      "description": "Post a message to a Slack channel.",
      "parameters": [
        { "name": "channel", "type": "string", "required": true, "description": "Channel id or name" },
        { "name": "text", "type": "string", "required": true, "description": "Message text" }
      ],
      "output_description": "Success or error message.",
      "post_process": false,
      "method": "POST",
      "path": "/post"
    }
  ]
}
```

---

## 8. Summary

| Aspect | Content |
|--------|--------|
| **Definition** | Same for built-in and external: id, name, description, description_long, **capabilities** (each with parameters, output_description, post_process, post_process_prompt). |
| **Capabilities** | Built-in = functions (method names); External = REST APIs (method + path). |
| **Parameters** | Per capability: name, type, required, default, description. |
| **Output handling** | **post_process: true** → Core runs LLM on output (optional post_process_prompt) and sends result to channel. **post_process: false** → send to channel directly. |
| **Persistence** | Vector database for RAG (embed description + description_long). Full descriptor from plugins folder (built-in) and external_plugins.json or registry. |
| **Flow** | RAG finds relevant plugins → inject only those into prompt/tools → LLM selects plugin (and capability/params) → Core calls plugin → post-process or direct to channel. |

This design keeps registration identical for built-in and external plugins, uses the same RAG pattern as skills to avoid context overflow, and makes output handling explicit (Core LLM vs direct to channel) with an optional prompt for refinement.
