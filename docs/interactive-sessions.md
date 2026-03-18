# Interactive sessions (PTY / ConPTY)

Interactive sessions let HomeClaw run **long-lived processes with stdin/stdout** (e.g. shells, REPLs, Cursor/Claude agent) so users can type and see output in real time from the Companion app or WebChat.

---

## What are interactive sessions?

- **Core** (and the Dev Bridge) can start a process in a **PTY** (Unix) or **ConPTY** (Windows) and keep it running.
- Each session has a **session_id**. Clients send input with **write** and read output with **read**; **stop** ends the session.
- Use cases: local shell (`bash` / `powershell`), **Cursor agent** or **Claude Code** in interactive mode (started via the bridge so the process runs on the dev machine).

---

## Config (tools)

All interactive limits live under **`tools`** in `config/core.yml` or, when using `skills_and_plugins_config_file`, in **`config/skills_and_plugins.yml`**.

| Key | Meaning | Default |
|-----|--------|--------|
| **`interactive_max_sessions_per_user`** | Max concurrent sessions per user. | `3` |
| **`interactive_max_buffer_bytes`** | Max characters kept in each session’s output buffer; older output is trimmed. | `200000` |
| **`interactive_idle_ttl_sec`** | Idle TTL in seconds (reserved for future cleanup). | `1800` |
| **`interactive_allowed_commands`** | Allowed commands for **interactive_start**. List of regex patterns (e.g. `["bash", "powershell", "sh"]`). Empty or omitted ⇒ use **`exec_allowlist`**. | use `exec_allowlist` |

Example in `config/skills_and_plugins.yml`:

```yaml
tools:
  interactive_max_sessions_per_user: 5
  interactive_max_buffer_bytes: 300000
  interactive_idle_ttl_sec: 3600
  interactive_allowed_commands: ["bash", "sh", "powershell", "pwsh"]
```

---

## APIs

### Start a session

- **HTTP (Companion / API):**  
  `POST /api/interactive/start`  
  Body: `{ "command": "bash" }` or `{ "command": "bash", "cwd": "/path" }` for a **local** shell.  
  For **Cursor/Claude agent on the bridge:**  
  `{ "bridge_plugin": "cursor-bridge" }` or `{ "bridge_plugin": "claude-code-bridge" }` (optional `cwd`).
- **WebSocket:**  
  Send `{ "event": "interactive_start", "command": "bash", "cwd": "...", "user_id": "..." }`.  
  Reply: `{ "event": "interactive_started", "session_id": "...", "initial_output": "..." }`.
- **Tool (LLM):**  
  `interactive_start` with `command` (and optional `cwd`). Returns JSON with `session_id` and `initial_output`.

### Read output

- **HTTP:**  
  `GET /api/interactive/read?session_id=<id>&from_seq=1`
- **WebSocket:**  
  `{ "event": "interactive_read", "session_id": "...", "from_seq": 1 }`  
  Reply: `{ "event": "interactive_output", "chunks": [...], "status": "...", ... }`.
- **Tool:**  
  `interactive_read(session_id, from_seq)`.

### Write input

- **HTTP:**  
  `POST /api/interactive/write`  
  Body: `{ "session_id": "...", "data": "ls\n" }`.
- **WebSocket:**  
  `{ "event": "interactive_write", "session_id": "...", "data": "..." }`.
- **Tool:**  
  `interactive_write(session_id, data)`.

### Stop a session

- **HTTP:**  
  `POST /api/interactive/stop`  
  Body: `{ "session_id": "..." }`.
- **WebSocket:**  
  `{ "event": "interactive_stop", "session_id": "..." }`.
- **Tool:**  
  `interactive_stop(session_id)`.

Session IDs for **bridge** sessions have the form `bridge:<plugin_id>:<bridge_sess_id>`. Use the same ID for read/write/stop; Core routes them to the correct plugin.

---

## Companion and WebChat

- **Companion:** For **Cursor** and **ClaudeCode** friends, the chat screen has a **terminal** icon. Tapping it opens an “Interactive console” panel. Opening the panel starts the **agent on the bridge** (Cursor or Claude) so you can type and see output. The same panel supports **send** (write), **refresh** (read), and **stop**.
- **WebChat:** Can call `POST /api/interactive/start` (and read/write/stop) when authenticated; session state and UI are up to the client.

---

## Windows and ConPTY

- On **Windows**, interactive sessions use **ConPTY** when the optional dependency **pywinpty** is installed (`pip install pywinpty`).
- If **pywinpty** is not installed, starting a session on Windows returns a clear message: *“Interactive sessions on Windows require the optional 'pywinpty' dependency. Use a Unix-like environment (macOS, Linux, WSL) or install pywinpty and restart Core.”*
- **Unix** (macOS, Linux): PTY is built-in; no extra dependency.

---

## Summary

| Topic | Where |
|-------|--------|
| Config keys | `tools.interactive_*` in core.yml or skills_and_plugins.yml |
| Start/read/write/stop | HTTP `/api/interactive/*`, WebSocket events, tools `interactive_*` |
| Companion console | Terminal icon for Cursor/ClaudeCode → bridge agent session |
| Windows | ConPTY via **pywinpty**; install it for interactive support on Windows |
