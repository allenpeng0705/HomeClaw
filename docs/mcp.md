# Using MCP (Model Context Protocol) in HomeClaw

HomeClaw can act as an **MCP client**: it connects to external [Model Context Protocol](https://modelcontextprotocol.io/) servers and exposes their tools to the LLM via **`mcp_list_tools`** and **`mcp_call`**. This lets the model use capabilities from any MCP-compatible server (e.g. GitHub, filesystem, databases, custom APIs).

---

## 1. Install the MCP client

The MCP client is **optional**. Install it when you want to use MCP servers:

```bash
pip install mcp
```

If `mcp` is not installed, the tools return a JSON error explaining that the package is required.

---

## 2. Configure MCP servers

Configure servers under **`tools.mcp`** in `config/skills_and_plugins.yml` (this file is merged into the main config; see `core.yml` → `skills_and_plugins_config_file`).

Example:

```yaml
tools:
  mcp:
    enabled: true
    servers:
      my-server:
        transport: stdio
        command: python
        args: [path/to/mcp_server.py, --transport, stdio]
      remote-server:
        transport: sse
        url: http://localhost:8000/sse
        timeout_seconds: 30
```

- **`enabled`**: Set to `true` to register `mcp_list_tools` and `mcp_call` and load `servers`. When `false` or omitted, MCP tools are not exposed.
- **`servers`**: Map of **server_id** → config. Each **server_id** is the value you pass to `mcp_list_tools(server_id=...)` and `mcp_call(server_id=..., ...)`.

### Transport: stdio

For a server that runs as a subprocess and talks over stdin/stdout:

| Key        | Required | Description |
|-----------|----------|-------------|
| `transport` | yes     | `stdio` |
| `command`  | yes     | Executable (e.g. `python`, `npx`) |
| `args`     | no      | List of arguments (e.g. script path and flags) |

Example:

```yaml
my-stdio-server:
  transport: stdio
  command: npx
  args: [-y, @modelcontextprotocol/server-filesystem, /path/to/allowed/dir]
```

### Transport: SSE

For a server that exposes an SSE endpoint:

| Key               | Required | Description |
|-------------------|----------|-------------|
| `transport`       | yes      | `sse` |
| `url`             | yes      | SSE URL (e.g. `http://localhost:8000/sse`) |
| `timeout_seconds` | no       | Request timeout (default if omitted) |

Example:

```yaml
remote-server:
  transport: sse
  url: http://127.0.0.1:8000/sse
  timeout_seconds: 30
```

---

## 3. Tools exposed to the LLM

When `tools.mcp.enabled` is `true` and at least one server is configured, the LLM sees:

| Tool | Description |
|------|-------------|
| **mcp_list_tools** | List tools exposed by an MCP server. Pass **server_id** (a key from `tools.mcp.servers`). Use this to discover what tools a server provides before calling `mcp_call`. |
| **mcp_call** | Call a tool on an MCP server. Pass **server_id**, **tool_name** (from `mcp_list_tools`), and **arguments** (JSON object). Use when the user wants to use an external MCP service (e.g. GitHub, filesystem, browser). |

- **server_id** must match a key in `tools.mcp.servers`.
- **tool_name** must be one of the names returned by `mcp_list_tools` for that server.
- **arguments** is the JSON object expected by that tool (e.g. `{"path": "/some/file"}`).

If the MCP package is missing or a server is not configured, the tools return JSON with an `error` field and no results.

---

## 4. Using Claude Code as an MCP server

You can run **Claude Code CLI** as an MCP server so HomeClaw can call its **built-in tools** (Read, Write, Edit, Bash, Task, WebFetch, etc.) via `mcp_list_tools` and `mcp_call`. This does **not** expose the MCP servers that Claude Code is configured with (e.g. GitHub, Notion); only Claude Code’s own tools are exposed.

1. Install [Claude Code CLI](https://code.claude.com/) and ensure `claude` is on PATH (or use the full path in config).
2. In `tools.mcp.servers`, add a stdio server:

```yaml
claude-code:
  transport: stdio
  command: claude
  args: [mcp, serve]
  # env: {}   # optional; e.g. ANTHROPIC_API_KEY
```

3. Set `tools.mcp.enabled: true`, or set **`tools.mcp.auto_register_claude_code: true`** so Core automatically enables MCP and adds the `claude-code` server at startup (no need to list it in `servers`).
4. Use a **friend** that receives the coding or messaging tool set: the **coding** and **messaging** profiles include `mcp_list_tools` and `mcp_call`. The **Cursor** and **ClaudeCode** friends use presets that do not include MCP tools, so use the default friend (or another without a restrictive preset) and phrase your message so the intent router classifies it as “coding” or “messaging” (e.g. “edit this file”, “run a script”).
5. The model can then call `mcp_list_tools(server_id="claude-code")` to discover tools, and `mcp_call(server_id="claude-code", tool_name="...", arguments={...})` to run them.

See **docs/cursor-claude-code-bridge.md** for how this fits with the Cursor/Claude Code bridge and **docs_design/ClaudeCodeMCPInvestigation.md** for tool names and behavior.

---

## 5. Intent router and tool filtering

If you use the **intent router** (`intent_router.enabled: true`), MCP tools are included only when the router allows them. To make MCP available for a category (e.g. `coding` or `general_chat`), ensure that category’s `category_tools` includes `mcp_list_tools` and `mcp_call` (or a profile that contains them). Otherwise, add an explicit category or use a profile that exposes these tools.

---

## 6. Summary

| Step | Action |
|------|--------|
| Install | `pip install mcp` |
| Config | In `config/skills_and_plugins.yml`, set `tools.mcp.enabled: true` and define `tools.mcp.servers` with **server_id** and transport (stdio or sse). |
| Use | LLM calls **mcp_list_tools(server_id)** to discover tools, then **mcp_call(server_id, tool_name, arguments)** to run a tool. |

For the protocol and server implementations, see [Model Context Protocol](https://modelcontextprotocol.io/).
