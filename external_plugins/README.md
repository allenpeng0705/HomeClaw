# External Plugins (simulate full workflow)

These examples show **external plugins** that register with Core via `POST /api/plugins/register` and run as separate HTTP servers. They demonstrate **multiple capabilities**, **multiple parameters**, and **post_process: true** (Core runs LLM on the plugin output before sending to the user).

**Summary:** Small examples in this folder — **Python** (Time, Companion), **Node.js** (Quote), **Go** (Time), **Java** (Quote). Full-featured examples: **system_plugins/homeclaw-browser** (Node.js — WebChat, browser automation, canvas, nodes) and a **companion plugin** (Python — same contract; see repo for location).

---

## One-step run (after Core is running)

Start all plugin servers and register them with Core in one command. Run from **project root** after Core is up:

```bash
# Linux / macOS / Git Bash
./external_plugins/run.sh
```

```powershell
# Windows PowerShell
.\external_plugins\run.ps1
```

- **All plugins:** Starts time (3102), companion (3103), quote-node (3111), time-go (3112), quote-java (3113) in the background and registers each with Core.
- **Specific plugins:** `./external_plugins/run.sh time companion quote-node` or `.\external_plugins\run.ps1 -Plugins time,companion,quote-node`
- **CORE_URL:** Set if Core is not at `http://127.0.0.1:9000` (e.g. `CORE_URL=http://127.0.0.1:9000 ./external_plugins/run.sh`).
- Logs and PIDs: `external_plugins/.run_logs/`. If a plugin is already running (same PID), the script only re-registers it.

**Run one plugin (one command):** Each plugin has its own start+register script. One command starts the server and registers it:

```bash
# Linux / macOS / Git Bash (from project root)
./external_plugins/time/run.sh
./external_plugins/companion/run.sh
./external_plugins/quote-node/run.sh
./external_plugins/time-go/run.sh
./external_plugins/quote-java/run.sh
```

```powershell
# Windows PowerShell (from project root)
.\external_plugins\time\run.ps1
.\external_plugins\companion\run.ps1
.\external_plugins\quote-node\run.ps1
```

(time-go and quote-java use `run.sh`; on Windows use Git Bash for those or use the top-level `.\external_plugins\run.ps1 -Plugins time-go,quote-java`.)

Then you can ask: "What time is it in Tokyo?", "Give me a quote", or use the companion (enable in `config/core.yml` as below).

---

## 1. Time Plugin (Python)

- **Server**: Returns current time or list of timezones; dispatches by `capability_id`.
- **Port**: 3102
- **Capabilities**:
  - **get_time** — Current time; parameters `timezone` (optional), `format` (12h/24h). **post_process: true**: Core formats as a friendly sentence.
  - **list_timezones** — List common IANA timezones. **post_process: false**.

### Run

**One command (start + register):** From project root after Core is running: `./external_plugins/time/run.sh` or `.\external_plugins\time\run.ps1`

Or manually: start server (`python -m external_plugins.time.server`), then in another terminal register (`python -m external_plugins.time.register`).

Then: "What time is it in Tokyo?" → Core routes to time, gets raw time string, **post_process** runs (Core LLM turns it into a friendly sentence), then sends. "List timezones" → capability list_timezones.

## 2. Companion Plugin

- **Server**: Separate conversation thread (companion persona) per user. Chat stored **only in companion store**, not in main user DB. Uses Core's LLM via `POST /api/plugins/llm/generate`. See [docs_design/CompanionFeatureDesign.md](../docs_design/CompanionFeatureDesign.md).
- **Port**: 3103 (set `COMPANION_PORT` to change)
- **Capability**: **chat** — one turn with the companion; user message in `user_input`, returns companion reply.

### Run

**One command (start + register):** From project root after Core is running: `./external_plugins/companion/run.sh` or `.\external_plugins\companion\run.ps1`

Or manually: start server (`python -m external_plugins.companion.server`), then register (`python -m external_plugins.companion.register`).

Enable in `config/core.yml`:

```yaml
companion:
  enabled: true
  plugin_id: companion
  session_id_value: companion
```

Then: **Companion app**, **WebChat**, or **homeclaw-browser** control UI send `conversation_type: companion` or `session_id: companion` (or `channel_name: companion`); Core routes those requests to the companion plugin only.

## 3. Quote Plugin (Node.js)

- **Server**: Same quote contract as (1), implemented in **Node.js** (no framework).
- **Port**: 3111
- **Capabilities**: get_quote (post_process: true), get_quote_by_topic.

### Run

**One command (start + register):** From project root after Core is running: `./external_plugins/quote-node/run.sh` or `.\external_plugins\quote-node\run.ps1`

Or manually: `cd external_plugins/quote-node`, `npm install`, `node server.js`, then in another terminal `node register.js`.

## 4. Time Plugin (Go)

- **Server**: Same time contract as (2), implemented in **Go** (stdlib only).
- **Port**: 3112
- **Capabilities**: get_time (post_process: true), list_timezones.

### Run

**One command (start + register):** From project root after Core is running: `./external_plugins/time-go/run.sh`

Or manually: `cd external_plugins/time-go`, `go run .`, then in another terminal `./register.sh`.

## 5. Quote Plugin (Java)

- **Server**: Same quote contract as (1), implemented in **Java** (JDK 11+, `com.sun.net.httpserver` + Gson).
- **Port**: 3113
- **Capabilities**: get_quote (post_process: true), get_quote_by_topic.

### Run

**One command (start + register):** From project root after Core is running: `./external_plugins/quote-java/run.sh`

Or manually: `cd external_plugins/quote-java`, `mvn compile exec:java -Dexec.mainClass="QuotePlugin"`, then in another terminal `./register.sh`.

## 6. HomeClaw Browser (system plugin — Node.js; Control UI + browser + canvas + nodes)

**Location:** **system_plugins/homeclaw-browser** (project root). A **Node.js**-based **system plugin** and a full-featured external plugin example. It provides WebChat (Control UI), browser automation (Playwright), canvas, and nodes in one server. Same contract: GET /health, POST /run; register with Core.

See **[system_plugins/README.md](../system_plugins/README.md)** and **[system_plugins/homeclaw-browser/README.md](../system_plugins/homeclaw-browser/README.md)** for run instructions, env vars (CORE_URL, CORE_API_KEY, PORT 3020), and how to test. Launcher: **http://127.0.0.1:9000/ui**; WebChat: **http://127.0.0.1:3020/**.

## 7. Companion plugin (Python)

A **Python**-based companion/utility plugin can serve as another external plugin example. Same contract: HTTP server with GET /health and POST /run; register with Core via POST /api/plugins/register. See the repo or **external_plugins/** for the latest location and run steps.

## Config

- **CORE_URL**: Default `http://127.0.0.1:9000`. Core runs on port 9000 by default (config/core.yml). Set `CORE_URL` if your Core is elsewhere.
- Python Time: `http://127.0.0.1:3102`
- Companion: `http://127.0.0.1:3103`
- Node.js Quote: `http://127.0.0.1:3111`
- Go Time: `http://127.0.0.1:3112`
- Java Quote: `http://127.0.0.1:3113`
- HomeClaw Browser (system plugin): `http://127.0.0.1:3020` — see **system_plugins/homeclaw-browser**

Run Python commands from the **project root** (e.g. `python -m external_plugins.time.server`). For Node/Go/Java, run from each sample directory as shown above.

## Contract

- Each server exposes:
  - `GET /health` — Core uses this for health checks. Return 2xx.
  - `POST /run` — Body = PluginRequest (JSON) with `capability_id` and `capability_parameters`; response = PluginResult (JSON) with `text`.
- Registration includes **capabilities** with **parameters** and **post_process** / **post_process_prompt**. When **post_process: true**, Core runs the LLM on the plugin's `text` using **post_process_prompt** before sending to the user. See docs/PluginRegistration.md.
