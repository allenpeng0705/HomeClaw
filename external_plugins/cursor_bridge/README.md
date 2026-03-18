# Cursor Bridge

Lets **HomeClaw** open a project in Cursor, chat with Cursor’s agent (run task and see results), or run shell commands on your dev machine. From Telegram, Companion, or any channel you can say e.g. “open my project in Cursor”, “have Cursor agent fix the bug and show me the result”, or “run npm test in Cursor”.

## Main features

| Feature | What it does |
|--------|----------------|
| **Open project** | Opens a folder in Cursor IDE (so you can then chat with the agent in Cursor). Uses `cursor <path>` CLI. |
| **Run agent** | Runs Cursor CLI `agent -p "task"` in non-interactive mode and returns the output to your channel (run and see results). |
| **Run command** | Runs a shell command (e.g. `npm test`) and returns stdout/stderr to your channel. |

## How it works

1. **HomeClaw** has the **Cursor Bridge** plugin (`plugins/CursorBridge/plugin.yaml`) pointing at this server’s URL.
2. You say e.g. “open D:\myproject in Cursor” or “run Cursor agent to add unit tests and show me the result”.
3. Core routes to `route_to_plugin(plugin_id='cursor-bridge', capability_id='open_project'|'run_agent'|'run_command', parameters={...})`.
4. This server opens the project in Cursor, or runs the agent/command, and returns a `PluginResult`. Core sends that back to you.

So the bridge must run on the **same machine (or a machine that can run commands / open files)** where you want the work to happen (typically where Cursor is).

## Requirements on the dev machine

- **Open project / open file:** Cursor IDE with the **shell command** installed (in Cursor: Command Palette → “Install cursor” or “Shell Command: Install 'cursor' command”). Then `cursor <path>` opens that folder or file in Cursor.
- **Run agent:** **Cursor CLI** so the `agent` command is available. Install: **macOS/Linux:** `curl https://cursor.com/install -fsS | bash` — **Windows (PowerShell):** `irm 'https://cursor.com/install?win32=true' | iex` (then restart the terminal). See [Cursor CLI](https://cursor.com/docs/cli). Then run **`agent login`** once (or set **`CURSOR_API_KEY`** in the environment). If Core auto-starts the bridge and you get "Authentication required", set `cursor_bridge_cursor_api_key` in config or `CURSOR_API_KEY` before starting Core.
- **Run command:** No extra requirement; the bridge runs shell commands in a subprocess.

## Run the bridge

**Option A — Auto-start with Core (recommended on same machine):** Set in `config/skills_and_plugins.yml` (or `config/core.yml`):

```yaml
cursor_bridge_auto_start: true
# cursor_bridge_port: 3104   # optional; default 3104
# If the bridge reports "agent not found", set the full path (Core may not have agent on PATH when it starts the bridge):
# cursor_bridge_agent_path: "C:\\Users\\You\\AppData\\Local\\Programs\\cursor\\agent.exe"   # PowerShell: (Get-Command agent).Source
# cursor_bridge_cursor_api_key: "your-cursor-api-key"   # if agent says "Authentication required"; prefer CURSOR_API_KEY in env for secrets
```

Then start Core as usual (`python -m main start`). If you see "agent not found", add `cursor_bridge_agent_path` with the output of `(Get-Command agent).Source` in PowerShell. No separate terminal needed.

**Option B — Manual:** From the project root (or any directory). Start the bridge from a terminal where `agent` is on PATH (e.g. where `agent --version` works).

```bash
# Default port 3104
python -m external_plugins.cursor_bridge.server
```

Optional environment variables:

- **`CURSOR_BRIDGE_PORT`** — Port (default `3104`). Must match `plugins/CursorBridge/plugin.yaml` `config.base_url` if Core runs elsewhere.
- **`CURSOR_BRIDGE_CWD`** — Default working directory for `run_command` when `cwd` is not provided (e.g. your project root).
- **`CURSOR_CLI_PATH`** — Full path to the `cursor` CLI (to open project/folder in Cursor IDE). If "open project" opens File Explorer instead of Cursor, set this (or `cursor_bridge_cursor_cli_path` in config when using auto-start). PowerShell: `(Get-Command cursor).Source`.
- **`CURSOR_API_KEY`** — Cursor API key for `agent` auth. If you get "Authentication required", run `agent login` once or set this (or `cursor_bridge_cursor_api_key` in config when using auto-start).

Example with custom port and project dir:

```bash
set CURSOR_BRIDGE_PORT=3104
set CURSOR_BRIDGE_CWD=D:\mygithub\MyProject
python -m external_plugins.cursor_bridge.server
```

The server listens on `0.0.0.0:3104` so it can be reached from another machine (e.g. where Core runs) on the same LAN or via Tailscale.

## Point HomeClaw at the bridge

- **Same machine as Core:** In `plugins/CursorBridge/plugin.yaml`, keep `base_url: "http://127.0.0.1:3104"` (or the port you use).
- **Core on another machine:** Set `base_url` to the bridge machine’s URL, e.g. `http://192.168.1.100:3104` or `http://my-pc:3104` (Tailscale/LAN). You can override in `config/skills_and_plugins.yml` under the plugin config if your deployment merges that.

Restart or reload Core after changing the plugin config so it picks up the new URL.

### No logs on the bridge when using Companion

If Core runs on a **different machine** (e.g. a server) and the plugin config there has `base_url: "http://127.0.0.1:3104"`, Core calls **127.0.0.1 on the server**, not your PC. Your bridge terminal shows no requests. **Fix:** On the machine where **Core** runs, set `plugins/CursorBridge/plugin.yaml` to `base_url: "http://<YOUR_PC_IP>:3104"` (your PC's IP or hostname). Allow inbound TCP 3104 on your PC firewall, then restart Core.

## Capabilities

| capability_id   | Description | Parameters |
|-----------------|-------------|------------|
| **open_project** | Open a folder/project in Cursor IDE (so you can chat with the agent there). Uses `cursor` CLI. | `path` or `folder` (required) |
| **run_agent**    | Run Cursor CLI agent with a task; returns output so you see results in the channel. | `task` (required), `cwd`, `timeout_sec` (optional) |
| **run_command**  | Run a shell command (e.g. `npm test`, `pip install`) and return output. | `command` (required), `cwd` (optional) |
| **open_file**    | Open a single file in Cursor (system default app). | `path` (required) |
| **ask_cursor**   | Natural-language; bridge infers open_project / run_agent / run_command or returns instructions. | `task` (optional; else user_input) |

## Security

- The bridge runs on your dev machine and can run arbitrary shell commands. Run it only in a trusted environment.
- If Core can reach the bridge from another host (LAN/Tailscale), consider adding auth (e.g. API key in a header). The current server does not enforce auth; add it if you expose the port.

## Health check

- **GET /health** — Returns `{"status":"ok"}`. Core or scripts can use this to verify the bridge is up.
