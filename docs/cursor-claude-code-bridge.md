# Cursor and Claude Code Bridge — How It Works

This doc reviews how HomeClaw integrates with **Cursor** and **Claude Code** on the user’s dev machine, and how to use **Claude Code’s MCP server** so HomeClaw can call Claude Code’s tools.

---

## 1. Overview

- **Cursor Bridge** and **Claude Code Bridge** are two **plugins** that talk to the **same bridge server** (`external_plugins/cursor_bridge/server.py`) running on the dev machine (e.g. `http://127.0.0.1:3104`).
- **Cursor friend** uses plugin `cursor-bridge`; **ClaudeCode friend** uses plugin `claude-code-bridge`. Each has its own preset and plugin id so Companion can show separate chats.
- The bridge does **not** use HomeClaw’s LLM for these friends: messages are **pattern-routed** in `llm_loop.py` to the right capability and sent to the bridge via `route_to_plugin`.

---

## 2. Cursor Bridge (plugin: `cursor-bridge`)

| Capability | Purpose |
|------------|--------|
| `open_project` | Open a folder in Cursor IDE (path). |
| `open_file` | Open a single file in Cursor. |
| `run_agent` | Run Cursor CLI **agent** with a task; returns output (non-interactive). |
| `run_command` | Run a shell command (e.g. `npm test`) and return output. |
| `get_status` | Return active project cwd and bridge status. |
| `run_agent_interactive` | Start Cursor agent in a PTY; Companion/WebChat use interactive_read/write/stop. |
| `run_command_interactive` | Start a shell in a PTY for interactive use. |
| `interactive_read` / `interactive_write` / `interactive_stop` | Operate on a bridge interactive session. |

- **Active CWD:** The bridge keeps a **cursor** active project path (and a separate one for **claude**). It’s set by `open_project` / `open_file` and used as default `cwd` for `run_agent` / `run_command`. State is persisted in `~/.homeclaw/cursor_bridge_state.json`.
- **Routing:** For the Cursor friend, `_cursor_bridge_capability_and_params()` maps the user message to one of the capabilities above (e.g. “open X in Cursor” → `open_project`, “run agent to fix the bug” → `run_agent`).

---

## 3. Claude Code Bridge (plugin: `claude-code-bridge`)

| Capability | Purpose |
|------------|--------|
| `set_cwd` | Set the **claude** active project path on the bridge. |
| `run_agent` | Run **Claude Code CLI** (`claude`) with a task; uses `--dangerously-skip-permissions` and optional `--output-format json`; returns output. |
| `run_command` | Run a shell command in the active project. |
| `get_status` | Return bridge status (including claude active cwd). |
| `run_agent_interactive` | Start Claude Code CLI in a PTY for interactive use. |
| `run_command_interactive` | Start a shell in a PTY. |
| `interactive_read` / `interactive_write` / `interactive_stop` | Same as Cursor. |

- **Active CWD:** Separate from Cursor; stored as `claude_active_cwd` in the same state file.
- **Routing:** For the ClaudeCode friend, `_claude_bridge_capability_and_params()` does the same kind of pattern routing to these capabilities.

When you send a task via `run_agent`, the **Claude Code CLI** runs on the bridge machine. If you have configured MCP servers in Claude Code (e.g. `claude mcp add`), the CLI can use those **inside** that run (e.g. GitHub, Notion). The bridge does not expose those MCP servers to HomeClaw directly; it only sends the task and returns the CLI output.

---

## 4. Using Claude Code’s MCP Server from HomeClaw

Claude Code can also run as an **MCP server** (`claude mcp serve`). That exposes **Claude Code’s built-in tools** (Read, Write, Edit, Bash, Task, etc.) over stdio so that **HomeClaw’s MCP client** can call them via `mcp_list_tools` and `mcp_call`.

- **What you get:** HomeClaw’s LLM (with MCP tools enabled) can discover and call tools like Read, Write, Edit, Bash, Task, WebFetch, etc., implemented by Claude Code, without running the full CLI for each request.
- **What you don’t get:** The MCP server does **not** re-expose the MCP servers that Claude Code is configured with (e.g. GitHub, Notion). Those are only used when the Claude Code **CLI** runs (e.g. via the bridge’s `run_agent`).

### 4.1 Configure Claude Code as an MCP server

1. Install the MCP client: `pip install mcp`.
2. **Automatic (recommended):** In `config/skills_and_plugins.yml` under `tools:`, add `mcp:` and set **`auto_register_claude_code: true`**. When Core starts, it enables MCP and registers the `claude-code` server (stdio, `claude mcp serve`) so you don’t have to list it in `servers`.
3. **Manual:** In `config/skills_and_plugins.yml`, under `tools.mcp`, set `enabled: true` and add the server to `servers`:

```yaml
tools:
  mcp:
    enabled: true
    servers:
      claude-code:
        transport: stdio
        command: claude   # or full path, e.g. C:\path\to\claude.cmd on Windows
        args: [mcp, serve]
        # Optional: env (e.g. ANTHROPIC_API_KEY if not in system env)
        # env: {}
```

4. Ensure the model can see MCP tools. HomeClaw chooses tools in two steps: **(1)** the **intent router** picks a category (e.g. “coding”, “messaging”) and filters tools by that category’s **profile**; **(2)** if the **friend** has a **preset** (e.g. Cursor, ClaudeCode, Reminder), tools are further restricted to that preset’s list. The **coding** and **messaging** profiles include `mcp_list_tools` and `mcp_call`. So:
   - Use a **friend that does not use a narrow preset** (e.g. the default “HomeClaw” friend with no preset). Then when your message is classified as “coding” or “messaging”, the model gets the coding/messaging profile and will have `mcp_list_tools` and `mcp_call`.
   - **Cursor** and **ClaudeCode** friends use presets whose tool list does **not** include MCP tools (they only have `route_to_plugin`, `folder_list`, etc.), so those friends never see `mcp_list_tools` / `mcp_call`. To use Claude Code’s MCP server, chat with a friend that gets the coding or messaging profile (e.g. default friend) and say something that triggers “coding” or “messaging” (e.g. “edit this file”, “run a script”, “use the claude-code MCP tools”).
5. The model can then call `mcp_list_tools(server_id="claude-code")` and `mcp_call(server_id="claude-code", ...)`.

See **docs/mcp.md** for full MCP config (transports, timeouts) and **docs_design/ClaudeCodeMCPInvestigation.md** for tool names and behavior.

### 4.2 Two ways to “use Claude Code” from HomeClaw

| Method | When to use |
|--------|----------------|
| **Bridge (ClaudeCode friend)** | Send natural-language tasks; Claude Code CLI runs on the dev machine and can use its own MCP config (GitHub, etc.). Good for “run Claude to do X and show me the result” and interactive PTY. |
| **MCP server (`claude mcp serve`)** | HomeClaw’s LLM calls Claude Code’s **built-in** tools by name (Read, Write, Edit, Bash, Task, …). Good for fine-grained control from any friend that has `mcp_list_tools` and `mcp_call` (e.g. coding profile). |

You can use both: e.g. ClaudeCode friend for interactive CLI and PTY, and MCP for scripted or tool-based flows from HomeClaw.

---

## 5. References

- Plugin manifests: `plugins/CursorBridge/plugin.yaml`, `plugins/ClaudeCodeBridge/plugin.yaml`
- Bridge server: `external_plugins/cursor_bridge/server.py`
- Routing: `core/llm_loop.py` (`_cursor_bridge_capability_and_params`, `_claude_bridge_capability_and_params`)
- MCP client: `docs/mcp.md`; tool registration and profiles: `tools/builtin.py`, `base/tool_profiles.py`
- Claude Code MCP: `docs_design/ClaudeCodeMCPInvestigation.md`
