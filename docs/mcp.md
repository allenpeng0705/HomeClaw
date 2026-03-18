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

## 4. Intent router and tool filtering

If you use the **intent router** (`intent_router.enabled: true`), MCP tools are included only when the router allows them. To make MCP available for a category (e.g. `coding` or `general_chat`), ensure that category’s `category_tools` includes `mcp_list_tools` and `mcp_call` (or a profile that contains them). Otherwise, add an explicit category or use a profile that exposes these tools.

---

## 5. Summary

| Step | Action |
|------|--------|
| Install | `pip install mcp` |
| Config | In `config/skills_and_plugins.yml`, set `tools.mcp.enabled: true` and define `tools.mcp.servers` with **server_id** and transport (stdio or sse). |
| Use | LLM calls **mcp_list_tools(server_id)** to discover tools, then **mcp_call(server_id, tool_name, arguments)** to run a tool. |

For the protocol and server implementations, see [Model Context Protocol](https://modelcontextprotocol.io/).
