# Claw-Code and MCP (integrations)

Claw-Code turns already support the generic **`mcp_call`** / **`mcp_list_tools`** tools when MCP servers are defined under **`tools.mcp.servers`** in merged config.

## What ships today

- **Operator note:** `clawcode.mcp_preset_note` in `config/core.yml` is appended to the system prompt as **“MCP (configured servers)”** when a Claw-Code session is active — use it to tell the model which `server_id` keys exist and how to use them.
- **Allowlist:** `clawcode.mcp_tool_allowlist` restricts Claw-Code turns to explicit **`server_id/tool_name`** pairs (and filters `mcp_list_tools` output the same way).
- **Core** runs MCP over the existing in-process client (`tools/builtin.py`); no separate `homeclaw-mcp` binary is required for server-backed MCP.

## Desktop / IDE-style “stdio MCP” (first-party server)

Shipped as **`clients/homeclaw_mcp/`**: a small **stdio MCP server** (official `mcp` + `httpx` packages) that exposes tools **`homeclaw_ready`** and **`homeclaw_inbound`** against Core. Run from repo root:

```bash
pip install mcp httpx
export HOMECLAW_CORE_URL=http://127.0.0.1:9000
export HOMECLAW_API_KEY=...   # if Core auth_enabled
python3 -m main homeclaw_mcp
# or: python3 -m clients.homeclaw_mcp
```

See **`clients/homeclaw_mcp/README.md`**. This is **not** the same as `tools.mcp.servers` (Core as **client** to external MCP); it is Core as **HTTP backend** for an MCP-capable IDE.

For **in-Core** stdio MCP servers (filesystem, etc.), keep using **`tools.mcp.servers.<id>`** with `transport: stdio` and `command` / `args` as today in `skills_and_plugins.yml`.
