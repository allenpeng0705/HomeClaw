# OpenClaw CLI investigation and HomeClaw CLI roadmap

OpenClaw’s CLI is a **lightweight but full-featured** tool: one binary (`openclaw`) with many subcommands for gateway, nodes, channels, agent chat, status, and more. Our HomeClaw CLI today only has **chat** (POST /inbound). This doc summarizes OpenClaw’s CLI and proposes a phased roadmap for our CLI so it stays lightweight but becomes more useful.

---

## OpenClaw CLI at a glance

- **Install:** Global CLI via npm/pnpm (`openclaw`).
- **Config/state:** `~/.openclaw/` (config, state, workspace). Optional `--profile <name>` and `--dev`.
- **Global flags:** `-V`, `--version`, `--no-color`, `--profile`, `--dev`, `--json` (machine output).
- **Output:** ANSI colors, progress (OSC 9;4), OSC-8 links; `--json` for scripting.

### Command groups (summary)

| Group | Purpose | Examples |
|-------|---------|----------|
| **Setup / config** | First-run and config | `setup`, `onboard`, `configure`, `config get/set/unset`, `doctor` |
| **Gateway** | Run and manage the Gateway | `gateway run`, `gateway install/start/stop/restart`, `gateway status`, `gateway health`, `gateway discover`, `gateway call` |
| **Status / health** | Diagnostics | `status`, `health`, `sessions` |
| **Agent / chat** | One-shot agent and messaging | `agent --message "..."`, `message send --target ... --message "..."` |
| **Channels** | Channel accounts and login | `channels list`, `channels status`, `channels login/logout`, `channels add/remove`, `channels logs` |
| **Nodes** | Paired devices and node commands | `nodes list`, `nodes status`, `nodes pending`, `nodes approve`, `nodes invoke`, `nodes run`, `nodes canvas snapshot`, `nodes camera snap`, `nodes screen record`, `nodes notify` |
| **Node host** | Run headless node service | `node run`, `node install`, `node status`, `node start/stop/restart` |
| **Devices** | Device pairing | `devices list`, `devices approve/reject` |
| **Models** | LLM and image model config | `models list`, `models status`, `models set`, `models auth` |
| **Memory** | Vector memory | `memory search`, `memory index`, `memory status` |
| **Plugins** | Extensions | `plugins list`, `plugins info`, `plugins install`, `plugins enable/disable`, `plugins doctor` |
| **Skills** | Skills registry | `skills list`, `skills info`, `skills check` |
| **Cron** | Scheduled jobs | `cron list`, `cron add`, `cron run`, `cron enable/disable` |
| **Browser** | Dedicated browser control | `browser start/stop`, `browser navigate`, `browser snapshot`, `browser click`, `browser type`, … |
| **Approvals** | Exec allowlists | `approvals get/set`, `approvals allowlist add/remove` |
| **Logs** | Gateway logs | `logs --follow`, `logs --limit` |
| **TUI** | Terminal UI chat | `tui` (interactive chat over Gateway WS) |
| **Other** | Reset, security, pairing, etc. | `reset`, `uninstall`, `security audit`, `pairing list/approve`, `docs`, `dns setup` |

So OpenClaw’s CLI is **one entrypoint** with many subcommands; it stays “lightweight” because it’s a single tool that delegates to the Gateway (and config) instead of duplicating logic.

---

## How OpenClaw CLI relates to the stack

- **Gateway:** OpenClaw has a WebSocket Gateway (port 18789). The CLI talks to it via HTTP RPC or WS for `status`, `health`, `agent`, `nodes invoke`, `gateway call`, etc.
- **Config:** Stored under `~/.openclaw/`; CLI reads/writes via `config get/set/unset` and wizards.
- **Nodes:** Nodes connect to the Gateway as WS clients; the CLI calls Gateway RPCs that forward to nodes (`nodes invoke`, `nodes run`, `nodes canvas snapshot`, etc.).
- **Channels:** Channel state and login live in the Gateway; CLI runs `channels login` (e.g. WhatsApp QR) or `channels add` with tokens.

So the CLI is **thin**: it’s a front-end to the Gateway and config; the heavy work is in the Gateway and nodes.

---

## HomeClaw vs OpenClaw mapping

| OpenClaw | HomeClaw |
|----------|----------|
| Gateway (WS + RPC) | **Core** (HTTP + WebSocket at port 9000) |
| Gateway config | **config/core.yml**, **config/user.yml** |
| Nodes (WS to Gateway) | **homeclaw-browser** plugin + Nodes page; optional future native nodes |
| Channels (WhatsApp, etc.) | **channels/** (e.g. whatsappweb, telegram) |
| `openclaw agent` | **POST /inbound** (we have `chat` already) |
| `openclaw status` / `health` | **GET** Core health or a small status API |
| `openclaw sessions` | **GET /api/sessions** (Core already has this) |
| `openclaw nodes list` | Would call **plugin** (e.g. homeclaw-browser `node_list`) or Core if we add a nodes API |
| `openclaw gateway *` | We don’t have a separate gateway process; Core is the “gateway.” So “status” = Core status. |

So our CLI should talk to **Core** (and optionally to the **plugin** for node list/invoke when we expose that).

---

## HomeClaw CLI today

- **Commands:** `chat "message"` (POST /inbound), **`status`** (Core reachability + session count), **`sessions`** (GET /api/sessions; `--json` for raw).
- **Global options:** `--url`, `--api-key` (apply to all commands).
- **Env:** `HOMECLAW_CORE_URL`, `HOMECLAW_API_KEY`.

Phase 1 (status, sessions) is implemented. Phases 2–4 are planned.

---

## Proposed HomeClaw CLI roadmap (stay lightweight, add useful commands)

Keep the CLI as **one script** (or one entrypoint) that calls Core (and later plugin) APIs. Add subcommands in phases.

### Phase 1: Core-only (minimal, high value)

- **`chat`** (existing): `homeclaw chat "message"` → POST /inbound.
- **`status`**: GET Core root or a simple health endpoint; print “Core reachable” and maybe version/config hint. If Core has no dedicated health URL, GET `/` or `/api/sessions` (with auth if needed) and treat 200 as “up.”
- **`sessions`**: GET /api/sessions (with auth if enabled); print session list (e.g. id, user_id, last activity). Optional `--json`.

This gives: chat + quick health check + session list with no new Core APIs.

### Phase 2: Convenience and scripting

- **`agent`**: Alias or variant of `chat` with `--timeout`, `--json` (output only the reply text or JSON for piping).
- **`config`**: Read Core URL / API key from a small local config file (e.g. `~/.config/homeclaw/cli.json` or `./.homeclaw`) so users don’t need to pass `--url` / `--api-key` every time. CLI still accepts env and flags override.

### Phase 3: Nodes (when we have a stable node API)

- **`nodes list`**: Call plugin (e.g. homeclaw-browser) or Core if we add something like GET /api/nodes; list connected nodes and maybe capabilities.
- **`nodes invoke`**: Invoke a capability on a node (e.g. `node_camera_snap`, `node_command`) via Core’s `route_to_plugin` or a dedicated nodes API. Requires Core and plugin support.

### Phase 4: Optional extras (only if needed)

- **`plugins list`** / **`plugins health`**: If Core exposes plugin registry/health (e.g. GET /api/plugins or /api/plugin-ui), CLI can show them.
- **`tui`**: Simple interactive TUI (REPL) that sends each line to POST /inbound or over WebSocket /ws and prints replies (like `openclaw tui` but for Core).

---

## Implementation notes

- **Single entrypoint:** Keep `homeclaw_cli.py` (or `homeclaw`) with subparsers: `chat`, `status`, `sessions`, and later `agent`, `config`, `nodes`, etc.
- **Shared Core client:** One function to build base URL and auth headers from env + config file + flags; use it in all commands that call Core.
- **Lightweight:** No need to reimplement OpenClaw’s full surface; add only what fits our stack (Core + plugin). Prefer “small and useful” over “feature parity.”
- **Output:** Support `--json` for status/sessions (and later nodes) for scripting; default human-readable.

---

## Summary

- **OpenClaw CLI:** One binary, many subcommands (gateway, nodes, channels, agent, status, sessions, config, doctor, etc.); lightweight because it delegates to the Gateway and config.
- **Our CLI:** Today only `chat`. We can extend it in phases: add **status** and **sessions** (Core already has /api/sessions), then **agent**/config, then **nodes list/invoke** when we have a node API, and optionally **tui** and plugin commands, while keeping one small CLI that talks to Core (and plugin) only.
