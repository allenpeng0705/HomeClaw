# External Plugins (simulate full workflow)

These examples show **external plugins** that register with Core via `POST /api/plugins/register` and run as separate HTTP servers. They demonstrate **multiple capabilities**, **multiple parameters**, and **post_process: true** (Core runs LLM on the plugin output before sending to the user).

**Summary:** Small examples in this folder — **Python** (Quote, Time), **Node.js** (Quote), **Go** (Time), **Java** (Quote). Full-featured examples: **system_plugins/homeclaw-browser** (Node.js — WebChat, browser automation, canvas, nodes) and a **companion plugin** (Python — same contract; see repo for location).

## 1. Quote Plugin

- **Server**: Returns random quotes; dispatches by `capability_id`.
- **Port**: 3101
- **Capabilities**:
  - **get_quote** — Random quote; optional `style` (short/long). **post_process: true**: Core adds a brief reflection.
  - **get_quote_by_topic** — Quote by topic; parameters `topic` (required), `style` (optional). **post_process: false**.

### Run

```bash
# Terminal 1: start Core (from project root)
python -m core.core

# Terminal 2: start the quote plugin server
python -m examples.external_plugins.quote.server

# Terminal 3: register the plugin with Core
python -m examples.external_plugins.quote.register
```

Then: "Give me an inspirational quote" → Core routes to quote, gets raw quote, **post_process** runs (Core LLM adds a short reflection), then sends to user. "Quote about success" → use capability get_quote_by_topic with topic=success.

## 2. Time Plugin

- **Server**: Returns current time or list of timezones; dispatches by `capability_id`.
- **Port**: 3102
- **Capabilities**:
  - **get_time** — Current time; parameters `timezone` (optional), `format` (12h/24h). **post_process: true**: Core formats as a friendly sentence.
  - **list_timezones** — List common IANA timezones. **post_process: false**.

### Run

```bash
# Terminal 1: Core (if not already running)
python -m core.core

# Terminal 2: start the time plugin server
python -m examples.external_plugins.time.server

# Terminal 3: register the plugin with Core
python -m examples.external_plugins.time.register
```

Then: "What time is it in Tokyo?" → Core routes to time, gets raw time string, **post_process** runs (Core LLM turns it into a friendly sentence), then sends. "List timezones" → capability list_timezones.

## 3. Quote Plugin (Node.js)

- **Server**: Same quote contract as (1), implemented in **Node.js** (no framework).
- **Port**: 3111
- **Capabilities**: get_quote (post_process: true), get_quote_by_topic.

### Run

```bash
cd examples/external_plugins/quote-node
npm install
node server.js
# In another terminal (from project root or quote-node): node register.js
```

## 4. Time Plugin (Go)

- **Server**: Same time contract as (2), implemented in **Go** (stdlib only).
- **Port**: 3112
- **Capabilities**: get_time (post_process: true), list_timezones.

### Run

```bash
cd examples/external_plugins/time-go
go run main.go
# In another terminal: ./register.sh  (or bash register.sh)
```

## 5. Quote Plugin (Java)

- **Server**: Same quote contract as (1), implemented in **Java** (JDK 11+, `com.sun.net.httpserver` + Gson).
- **Port**: 3113
- **Capabilities**: get_quote (post_process: true), get_quote_by_topic.

### Run

```bash
cd examples/external_plugins/quote-java
mvn compile exec:java -Dexec.mainClass="QuotePlugin"
# In another terminal: ./register.sh
```

## 6. HomeClaw Browser (system plugin — Node.js; Control UI + browser + canvas + nodes)

**Location:** **system_plugins/homeclaw-browser** (project root). A **Node.js**-based **system plugin** and a full-featured external plugin example. It provides WebChat (Control UI), browser automation (Playwright), canvas, and nodes in one server. Same contract: GET /health, POST /run; register with Core.

See **[system_plugins/README.md](../../system_plugins/README.md)** and **[system_plugins/homeclaw-browser/README.md](../../system_plugins/homeclaw-browser/README.md)** for run instructions, env vars (CORE_URL, CORE_API_KEY, PORT 3020), and how to test. Launcher: **http://127.0.0.1:9000/ui**; WebChat: **http://127.0.0.1:3020/**.

## 7. Companion plugin (Python)

A **Python**-based companion/utility plugin can serve as another external plugin example. Same contract: HTTP server with GET /health and POST /run; register with Core via POST /api/plugins/register. See the repo or **examples/external_plugins/** for the latest location and run steps.

## Config

- **CORE_URL**: Default `http://127.0.0.1:9000`. Core runs on port 9000 by default (config/core.yml). Set `CORE_URL` if your Core is elsewhere.
- Python Quote: `http://127.0.0.1:3101`
- Python Time: `http://127.0.0.1:3102`
- Node.js Quote: `http://127.0.0.1:3111`
- Go Time: `http://127.0.0.1:3112`
- Java Quote: `http://127.0.0.1:3113`
- HomeClaw Browser (system plugin): `http://127.0.0.1:3020` — see **system_plugins/homeclaw-browser**

Run Python commands from the **project root** (e.g. `python -m examples.external_plugins.quote.server`). For Node/Go/Java, run from each sample directory as shown above.

## Contract

- Each server exposes:
  - `GET /health` — Core uses this for health checks. Return 2xx.
  - `POST /run` — Body = PluginRequest (JSON) with `capability_id` and `capability_parameters`; response = PluginResult (JSON) with `text`.
- Registration includes **capabilities** with **parameters** and **post_process** / **post_process_prompt**. When **post_process: true**, Core runs the LLM on the plugin's `text` using **post_process_prompt** before sending to the user. See docs/PluginRegistration.md.
