# HomeClaw Using Cursor and TRAE from Channels / Companion

This document designs how **HomeClaw** can **use** **Cursor** (IDE) and **TRAE** ([trae.ai](https://www.trae.ai/) — “your 10x AI Engineer who can independently build software solutions”) when the user talks from **channels** (Telegram, WebChat, etc.) or the **Companion app**. The user says something like “run this in Cursor” or “ask TRAE to build X” and HomeClaw invokes the right backend.

---

## 1. Goals

- **Cursor**: From any channel or Companion, the user can ask HomeClaw to run a command in Cursor, open a file, apply an edit, or trigger an action in the IDE. HomeClaw sends the request to a **Cursor Bridge** that runs on the user’s dev machine and interacts with Cursor.
- **TRAE**: From any channel or Companion, the user can ask HomeClaw to hand off a coding or build task to **TRAE** (trae.ai). TRAE is an AI engineering product that can “independently build software solutions”; HomeClaw either calls TRAE’s API (if available) or talks to a **TRAE Bridge** that runs alongside TRAE and forwards requests.
- **Unified entry**: Same flow as today: user message → Core → LLM → tool/plugin/skill. We add **plugins** (or skills) for Cursor and TRAE so the LLM can route to them when intent matches.

---

## 2. High-Level Architecture

```
[User: Telegram / WebChat / Companion / …]
         │
         ▼
   [HomeClaw Core]
   - LLM chooses tool/plugin/skill
         │
         ├──────────────────────────┬─────────────────────────────┐
         ▼                          ▼                             ▼
   [Cursor Plugin]            [TRAE Plugin]               [Other plugins…]
   type: http                 type: http (or inline if API)
   Core POSTs to ──►          Core POSTs to ──►
   Cursor Bridge              TRAE Bridge (or TRAE API)
         │                          │
         ▼                          ▼
   [Cursor Bridge]            [TRAE Bridge / TRAE]
   (runs on dev machine)      (runs with TRAE; or TRAE cloud/local API)
   - Receives PluginRequest   - Receives PluginRequest
   - Talks to Cursor          - Forwards to TRAE (API / SOLO / app)
   - Returns PluginResult     - Returns PluginResult
```

- **Channels / Companion**: No change. They already send messages to Core via POST `/inbound` or WebSocket `/ws`. Core already has `route_to_plugin` and `run_skill`. We only add the Cursor and TRAE integrations and config.

---

## 3. Cursor Integration

### 3.1 Why a bridge?

Cursor does not expose a public “remote control” API. So HomeClaw cannot call Cursor directly. We need a small **bridge** that:

- Runs on the **same machine (or network)** as Cursor.
- Exposes an **HTTP endpoint** that HomeClaw Core can call (PluginRequest → PluginResult).
- Performs actions that **affect Cursor** (run command, open file, apply edit, etc.) using whatever mechanism is available (extension API, CLI, file-based handoff, or future Cursor APIs).

HomeClaw treats this bridge as an **external plugin (type: http)**:
- Core POSTs a **PluginRequest** to the bridge’s URL.
- Bridge returns a **PluginResult** (success, text, optional error).

### 3.2 Cursor Bridge contract

The bridge implements the same contract as any HomeClaw **external HTTP plugin**:

- **Endpoint**: e.g. `POST /run` (or path configured in plugin `config.path`).
- **Request body**: **PluginRequest** (JSON):
  - `request_id`, `plugin_id`, `user_input`, `user_id`, `user_name`, `channel_name`, …
  - `capability_id`: e.g. `run_command`, `open_file`, `apply_edit`, `ask_cursor` (optional; if omitted, bridge can infer from `user_input`).
  - `capability_parameters`: e.g. `{ "command": "npm test", "cwd": "/path/to/project" }` or `{ "path": "/path/to/file" }`.
- **Response body**: **PluginResult** (JSON):
  - `request_id`, `plugin_id`, `success`, `text` (reply to show user), `error` (if success false), optional `metadata`.

Optional: **GET /health** returning 2xx when the bridge (and ideally Cursor) is reachable. Core or the user can use this to verify connectivity.

### 3.3 How the bridge can talk to Cursor

Today Cursor does not offer a documented remote-control API. The bridge can use one or more of:

1. **Cursor extension / IDE API**  
   A Cursor extension (or VS Code extension running in Cursor) that:
   - Listens on a local port or uses a file/socket, and
   - Receives “run command”, “open file”, “apply edit” from the bridge and calls Cursor/VS Code APIs (e.g. `executeCommand`, `openTextDocument`, `workspace.applyEdit`).

2. **CLI / terminal**  
   If Cursor or the OS provides a way to run a command in the IDE’s integrated terminal (e.g. a CLI or script that the bridge spawns), the bridge can use that. This is environment-dependent.

3. **File-based handoff**  
   Bridge writes a “request” file (e.g. JSON) into a folder that a Cursor extension watches; the extension performs the action and writes a “response” file. Bridge polls or watches for the response and then returns it as PluginResult. Simple and works without any Cursor HTTP API.

4. **Future Cursor API**  
   If Cursor later exposes an HTTP or MCP server for IDE actions, the bridge can call that instead of (or in addition to) the above.

The design does not depend on which of these the bridge uses internally; it only requires the bridge to honour the PluginRequest/PluginResult HTTP contract.

### 3.4 HomeClaw side: Cursor as external plugin

- **Registration**: Cursor is registered as an **external plugin** with **type: http**.
  - **Folder-based**: e.g. `plugins/CursorBridge/` with `plugin.yaml`:
    - `id: cursor-bridge` (or `cursor`)
    - `name`, `description` for LLM routing (e.g. “Run commands or open files in Cursor IDE. Use when the user wants to run something in Cursor, open a file in Cursor, or control the IDE from a message.”)
    - `type: http`
    - `config.base_url`: e.g. `http://192.168.1.100:3102` or `https://cursor-bridge.my-tailscale.ts.net` (user-configurable; can be overridden by env or `skills_and_plugins`).
    - `config.path`: `/run` (default)
    - `config.timeout_sec`: e.g. 60
  - **API registration**: Alternatively, the user (or a script) registers the bridge with **POST /api/plugins/register** with the same descriptor and `health_check_url` so Core can check liveness.
- **Reachability**: Core must be able to reach the bridge. Options:
  - Same LAN: `base_url` = machine’s LAN IP + port.
  - Tailscale (or similar): `base_url` = Tailscale hostname (e.g. `http://dev-machine:3102`).
  - Ngrok / Cloudflare Tunnel: public URL (consider auth and security).
- **Capabilities** (optional but recommended for better LLM routing):
  - `run_command`: Run a shell command in Cursor’s context (params: `command`, optional `cwd`).
  - `open_file`: Open a file in Cursor (params: `path` or `uri`).
  - `apply_edit`: Apply a text edit (params: e.g. `path`, `old_text`, `new_text` or range + text).
  - `ask_cursor`: Send a natural-language request; bridge/Cursor interprets it (e.g. “run tests”, “open README”).

If capabilities are defined, the LLM can call `route_to_plugin(plugin_id="cursor-bridge", capability_id="run_command", parameters={...})`. If not, the bridge receives `user_input` (and optional `capability_parameters`) and infers the action.

### 3.5 Security

- **Auth**: The bridge should require authentication (e.g. API key or Bearer token). Core sends it in a header (e.g. `X-API-Key` or `Authorization: Bearer <token>`). Plugin config can hold `api_key` or `auth_header` (or reference an env var) so Core’s HTTP client sends it. Same pattern as other external plugins.
- **Scope**: The bridge runs on the user’s dev machine and only controls that machine’s Cursor. No cross-user Cursor control unless the user explicitly runs multiple bridges with different tokens.
- **Network**: Prefer private network (LAN or Tailscale). If the bridge is exposed to the internet, auth and HTTPS are required.

### 3.6 Summary: Cursor

| Item | Choice |
|------|--------|
| HomeClaw side | External plugin, type: http, id e.g. `cursor-bridge` |
| Contract | PluginRequest (POST) → PluginResult; optional GET /health |
| Where bridge runs | User’s dev machine (same as Cursor) |
| How bridge talks to Cursor | Extension / CLI / file handoff / future API (bridge’s concern) |
| Config | `config.base_url`, `config.path`, `config.timeout_sec`, optional auth |
| Channels/Companion | No change; LLM routes to plugin from any channel |

---

## 4. TRAE Integration (trae.ai)

**TRAE** ([trae.ai](https://www.trae.ai/)) is an AI engineering product: “Ship Faster with TRAE — Understand. Execute. Deliver. TRAE is your 10x AI Engineer who can independently build software solutions for you.” It is downloadable (e.g. “Download TRAE”, “Explore SOLO”) and is a separate product from Cursor.

### 4.1 Integration options

- **If TRAE exposes an API** (cloud or local): HomeClaw can call it directly (same pattern as any external HTTP plugin: Core POSTs a request, gets back a result). No bridge needed; we register TRAE as an external plugin with `type: http` and `config.base_url` pointing at TRAE’s API.
- **If TRAE is desktop-only or has no public API**: We use a **TRAE Bridge** (like the Cursor Bridge): a small HTTP server that runs on the machine where TRAE runs, receives **PluginRequest** from HomeClaw, forwards the task to TRAE (e.g. via TRAE’s local UI/CLI, or a file/socket TRAE watches), and returns **PluginResult**. HomeClaw then registers the bridge as an external plugin (type: http) with `base_url` pointing at the bridge.

This design supports both: **direct TRAE API** (when available) or **TRAE Bridge** (when TRAE is app/desktop-only).

### 4.2 TRAE Bridge / API contract (same as Cursor)

So that HomeClaw can treat TRAE like any other external plugin:

- **Endpoint**: e.g. `POST /run` (or path in plugin `config.path`).
- **Request body**: **PluginRequest** (JSON): `request_id`, `plugin_id`, `user_input`, `user_id`, `channel_name`, …; optional `capability_id` and `capability_parameters`.
- **Response body**: **PluginResult** (JSON): `request_id`, `plugin_id`, `success`, `text`, optional `error`, optional `metadata`.
- **GET /health**: Optional; return 2xx when TRAE (or the bridge) is ready.

If TRAE’s own API uses a different schema, the bridge (or a thin adapter in HomeClaw) translates between PluginRequest/PluginResult and TRAE’s format.

### 4.3 HomeClaw side: TRAE as external plugin

- **Registration**: TRAE is an **external plugin** with **type: http**.
  - **Folder-based**: e.g. `plugins/TraeBridge/` or `plugins/TRAE/` with `plugin.yaml`:
    - `id: trae` or `trae-bridge`
    - `name`: e.g. “TRAE” or “TRAE Bridge”
    - `description`: e.g. “Send coding or build tasks to TRAE (trae.ai), your 10x AI Engineer. Use when the user wants TRAE to build something, implement a feature, or run a task in TRAE.”
    - `type: http`
    - `config.base_url`: TRAE API URL or TRAE Bridge URL (e.g. `http://127.0.0.1:3103` or user’s Tailscale host).
    - `config.path`: `/run` (or TRAE API path)
    - `config.timeout_sec`: e.g. 120 (TRAE tasks may take longer)
  - **API registration**: User can register the TRAE endpoint via **POST /api/plugins/register** with `health_check_url` and config.
- **Capabilities** (optional): e.g. `ask_trae` (natural-language task), `build` (project/task description), `run_task` (structured task). If TRAE’s API or bridge supports more (e.g. “get status”, “list projects”), add capabilities accordingly.
- **Reachability**: Same as Cursor — Core must reach the TRAE API or bridge (LAN, Tailscale, or tunnel). Auth (API key / Bearer) in config if the endpoint is protected.

### 4.4 Config and security

- **Config**: `config.base_url`, `config.path`, `config.timeout_sec`, optional `api_key` or auth header.
- **Network**: Prefer private (LAN / Tailscale). If exposed, use HTTPS and auth.
- **Auth**: Store credentials in config or env; send in request header; do not log secrets.

### 4.5 Summary: TRAE

| Item | Choice |
|------|--------|
| HomeClaw side | External plugin, type: http, id e.g. `trae` or `trae-bridge` |
| Backend | TRAE API (if available) or TRAE Bridge (HTTP server next to TRAE app) |
| Contract | PluginRequest (POST) → PluginResult; optional GET /health |
| Config | `config.base_url`, `config.path`, `config.timeout_sec`, optional auth |
| Channels/Companion | No change; LLM routes to plugin from any channel |
| Reference | [TRAE — Collaborate with Intelligence](https://www.trae.ai/) |

---

## 5. How channels and Companion trigger it

- **Channels** (Telegram, WebChat, Discord, etc.) and **Companion** already send the user message to Core via POST `/inbound` or WebSocket `/ws`.  
- Core runs the usual flow: LLM with tools and plugins; intent router can restrict tools/plugins by category if desired.  
- When the user says things like “run npm test in Cursor” or “ask TRAE to build a small CLI tool”, the LLM chooses:
  - **Cursor**: `route_to_plugin(plugin_id="cursor-bridge", capability_id="run_command", parameters={ "command": "npm test" })` (or similar).  
  - **TRAE**: `route_to_plugin(plugin_id="trae", capability_id="ask_trae", parameters={ "task": "..." })` or forwards `user_input` to the TRAE plugin.  
- Core invokes the plugin (Cursor → HTTP to Cursor Bridge; TRAE → HTTP to TRAE API or TRAE Bridge). The plugin result is then sent back to the user on the same channel or Companion session.

No changes are required to the channel or Companion clients; only Core config (and optionally intent router categories) need to include the new plugins and their descriptions so the LLM can route to them.

---

## 6. Configuration sketch

### 6.1 Cursor Bridge (external plugin)

**Option 1 – Folder under `plugins/`**

```yaml
# plugins/CursorBridge/plugin.yaml
id: cursor-bridge
name: Cursor Bridge
description: |
  Run commands or open files in Cursor IDE. Use when the user wants to run something in Cursor,
  open a file in Cursor, or control the IDE from a message (e.g. "run npm test in Cursor",
  "open README in Cursor").
type: http
config:
  base_url: "http://127.0.0.1:3102"   # override in skills_and_plugins or env
  path: /run
  timeout_sec: 60
  # api_key: "${CURSOR_BRIDGE_API_KEY}"  # optional; Core sends in header
capabilities:
  - id: run_command
    name: Run command in Cursor
    description: Run a shell command in Cursor's context (e.g. terminal).
    parameters:
      - name: command
        type: string
        required: true
      - name: cwd
        type: string
        required: false
  - id: open_file
    name: Open file in Cursor
    description: Open a file in the Cursor editor.
    parameters:
      - name: path
        type: string
        required: true
```

`base_url` can be overridden per environment (e.g. in `skills_and_plugins.yml` or via env) so the same Core can talk to a bridge on a Tailscale hostname.

**Option 2 – API registration**

User runs the Cursor bridge and then registers it with Core:

```bash
curl -X POST "http://core:9000/api/plugins/register" \
  -H "Content-Type: application/json" \
  -d '{
    "plugin_id": "cursor-bridge",
    "name": "Cursor Bridge",
    "description": "Run commands or open files in Cursor IDE...",
    "type": "http",
    "health_check_url": "http://dev-machine:3102/health",
    "config": { "base_url": "http://dev-machine:3102", "path": "/run", "timeout_sec": 60 }
  }'
```

### 6.2 TRAE (external plugin – API or Bridge)

```yaml
# plugins/TraeBridge/plugin.yaml  (or plugins/TRAE/plugin.yaml)
id: trae
name: TRAE
description: |
  Send coding or build tasks to TRAE (trae.ai), your 10x AI Engineer. Use when the user
  wants TRAE to build something, implement a feature, or run a task (e.g. "ask TRAE to build X",
  "have TRAE implement a login page").
type: http
config:
  base_url: "http://127.0.0.1:3103"   # TRAE API or TRAE Bridge URL; override per env
  path: /run
  timeout_sec: 120
  # api_key: "${TRAE_API_KEY}"       # optional
capabilities:
  - id: ask_trae
    name: Ask TRAE
    description: Send a natural-language task to TRAE (e.g. build, implement, refactor).
    parameters:
      - name: task
        type: string
        required: true
        description: The task or request for TRAE (e.g. "Build a small REST API for todos").
```

If TRAE exposes a direct API with a different path or schema, set `config.base_url` to that API root and adjust `path` (or add a thin adapter in the bridge).

---

## 7. Implementation steps (summary)

1. **Cursor Bridge (outside HomeClaw repo)**  
   - Implement a small HTTP server (e.g. Python/FastAPI or Node) that:  
     - Accepts POST with PluginRequest, returns PluginResult.  
     - Optionally implements capabilities (run_command, open_file, …) by talking to Cursor via extension/CLI/file.  
   - Document how to run it and how to point HomeClaw at it (base_url, auth).

2. **Cursor plugin in HomeClaw**  
   - Add `plugins/CursorBridge/` with `plugin.yaml` (type: http, config.base_url, capabilities).  
   - Ensure Core can override `base_url` from config or env so the same code works for LAN/Tailscale/ngrok.  
   - Optionally: support API registration so users can register their bridge at runtime.

3. **TRAE plugin in HomeClaw**  
   - Add `plugins/TraeBridge/` (or `TRAE/`) with plugin.yaml (type: http, config.base_url, capabilities e.g. ask_trae).  
   - If TRAE has a public API: point `base_url` at it and match path/body to TRAE’s schema (or add a small adapter). If TRAE is desktop-only: implement a **TRAE Bridge** (same contract as Cursor Bridge) that runs next to TRAE and forwards PluginRequest to TRAE (e.g. via local API, CLI, or file handoff).  
   - Add descriptions so the LLM routes “ask TRAE to …”, “have TRAE build …”, etc., to this plugin.

4. **Intent router (optional)**  
   - Add categories or mappings so “IDE / Cursor” and “TRAE / AI engineer” requests get the right plugin set (e.g. include cursor-bridge and trae in the right categories).

5. **Docs**  
   - Document “Using Cursor from HomeClaw” (how to run the bridge, config, capabilities).  
   - Document “Using TRAE from HomeClaw” (config, TRAE API vs bridge, capabilities). Link to [TRAE](https://www.trae.ai/) where relevant.

---

## 8. Cursor Bridge – minimal implementation guide

For implementers of the **Cursor Bridge** (separate repo or repo under HomeClaw):

- **Server**: HTTP server (e.g. FastAPI, Express) on a configurable port (e.g. 3102).
- **POST /run** (or configured path):
  - Read body as JSON → parse as **PluginRequest** (see `base/base.py` or PluginRequest in this repo).
  - Use `capability_id` and `capability_parameters` (or `user_input`) to decide the action.
  - Perform the action (run command, open file, etc.) using one of the mechanisms in §3.3.
  - Return JSON **PluginResult**: `{ "request_id": "...", "plugin_id": "cursor-bridge", "success": true, "text": "..." }` or `success: false` with `error`.
- **GET /health**: Return 200 (optionally `{"status":"ok"}`).
- **Auth**: If `api_key` or auth header is configured, validate it on each request; reject with 401 if missing or invalid.
- **Distribution**: Can be a small Python/Node app, or a Cursor extension that starts a local server; document how the user runs it and sets `base_url` in HomeClaw so Core can reach it (e.g. `http://<machine>:3102` over LAN or Tailscale).

**Intent router**: If HomeClaw uses the intent router (`intent_router` in `skills_and_plugins.yml`), add a category such as `cursor` or `ide` and map it to include the `cursor-bridge` plugin (and optionally coding-related tools). For TRAE, add a category such as `trae` or `ai_engineer` and map it to the `trae` plugin so “ask TRAE to build …” / “have TRAE implement …” are routed correctly.

---

## 9. Summary

| Integration | HomeClaw side | Backend | Entry from channels/Companion |
|-------------|----------------|---------|-------------------------------|
| **Cursor** | External plugin (type: http) | Cursor Bridge (HTTP server on user’s dev machine) | User says “run in Cursor” etc. → LLM → route_to_plugin(cursor-bridge) → Core POSTs to bridge → bridge talks to Cursor → result to user. |
| **TRAE** ([trae.ai](https://www.trae.ai/)) | External plugin (type: http) | TRAE API (if available) or TRAE Bridge (HTTP server next to TRAE) | User says “ask TRAE to build …” etc. → LLM → route_to_plugin(trae) → Core POSTs to TRAE API or bridge → result to user. |

Both flows use the existing channel and Companion entry (POST `/inbound`, `/ws`); only Core’s plugin/skill set and config change. No change to channel or Companion clients is required.
