# Claude Code MCP Server — Investigation Summary

This document summarizes what **Claude Code’s MCP server** (`claude mcp serve`) exposes and how it corresponds to the CLI, for integration with HomeClaw’s MCP client.

---

## 1. How to run Claude Code as an MCP server

Claude Code can act as an **MCP server** so other MCP clients (e.g. HomeClaw) can call its tools:

```bash
claude mcp serve
```

- **Transport:** stdio only (no built-in HTTP/SSE for this mode).
- **Invocation:** The `claude` executable must be on PATH, or use the full path in config.
- **Config (e.g. Claude Desktop):**  
  `"command": "claude"`, `"args": ["mcp", "serve"]`, optional `"env": {}`.

**Optional:** Some usage (e.g. multi-agent) references `--allowedTools` to restrict which tools are exposed, e.g.  
`claude mcp serve --allowedTools Bash,Edit,Read,Write,...`  
Check current CLI with `claude mcp serve --help` for supported flags.

---

## 2. What the MCP server exposes

The official docs state:

> **Use Claude Code as an MCP server**  
> … This MCP server is only exposing **Claude Code’s tools** to your MCP client …  
> The server provides access to Claude’s tools like **View, Edit, LS**, etc.

So the server exposes **Claude Code’s built-in tools**, not the MCP servers that Claude Code itself is configured with (no proxy/aggregation of Claude’s own MCP config).

### 2.1 Tool list (from docs and community)

From the [Tools reference](https://code.claude.com/docs/en/tools-reference) and [GitHub issue #631](https://github.com/anthropics/claude-code/issues/631), the tools available when connecting to `claude mcp serve` typically include:

| Tool (typical name) | Corresponds to CLI / behavior |
|---------------------|-------------------------------|
| **Read** / **View** | Read file contents |
| **Write** | Create or overwrite files |
| **Edit** / **MultiEdit** | Targeted edits in files |
| **LS** | List directory contents |
| **Bash** | Run shell commands (persistent bash session; state kept between calls) |
| **Glob** | Find files by pattern |
| **Grep** | Search for patterns in file contents |
| **WebFetch** | Fetch URL content |
| **WebSearch** | Web search |
| **Task** | Run an agent task (description + prompt); used for subagents / “do this coding task” |
| **Agent** / **dispatch_agent** | Spawn subagents |
| **TodoRead** / **TodoWrite** | Task list (internal planning) |
| **Replace** | Replace text in files |
| **NotebookEdit** / **NotebookRead** | Jupyter notebook operations (if applicable) |

**Important:** The **exact** tool names and schema are defined by the running `claude mcp serve` process. To get the authoritative list and parameters for your environment:

1. Add Claude Code as an MCP server in HomeClaw (see §4).
2. Call **`mcp_list_tools(server_id='claude-code')`** and use the returned tool names and arguments in **`mcp_call(server_id='claude-code', tool_name=..., arguments={...})`**.

---

## 3. Correspondence with the CLI

- **CLI:** You run `claude` in the terminal and interact in natural language; Claude Code uses the same built-in tools (Read, Edit, Bash, etc.) internally.
- **MCP server:** The same tool implementations are exposed over MCP. So:
  - **“Run a task” in CLI** → corresponds to calling the **Task** (or similar) tool via MCP with a description/prompt.
  - **File read/edit, bash, grep, etc.** → same tools, callable via MCP by name with the right arguments.

The CLI does not expose a separate “run this one command” RPC; the MCP surface is **tool-based**. For a “run this and give me the result” flow (like Cursor’s run_agent), you would typically call the **Task** (or agent) tool with the user’s request as the task description/prompt.

---

## 4. HomeClaw integration (config sketch)

In `config/skills_and_plugins.yml` under `tools.mcp`:

```yaml
tools:
  mcp:
    enabled: true
    servers:
      claude-code:
        transport: stdio
        command: claude
        args: [mcp, serve]
        # Optional: working directory for Claude Code (e.g. project root)
        # cwd: /path/to/project
        # Optional: env if needed (e.g. CLAUDE_CONFIG_DIR)
        # env: {}
```

- **Windows:** If `claude` is not found, set `command` to the full path (e.g. from `where claude`). For local stdio servers that run `npx`, the Claude docs mention a `cmd /c` wrapper on Windows; for `claude mcp serve` the above is usually enough if `claude` is on PATH.
- After Core loads this, the LLM can use **mcp_list_tools(server_id='claude-code')** and **mcp_call(server_id='claude-code', tool_name=..., arguments={...})**.
- Optional: a **Claude** preset friend that only uses this server (system prompt: use `server_id='claude-code'` for all MCP calls). See recommendation in docs/mcp.md and the “Claude Code” discussion.

---

## 5. Limitations and notes

- **No proxy of Claude’s MCP servers:** `claude mcp serve` does **not** expose the MCP servers that Claude Code is configured with (e.g. GitHub, PostgreSQL). Only Claude Code’s **built-in** tools are exposed.
- **Confirmation:** The docs say the **client** is responsible for user confirmation for tool calls; HomeClaw’s MCP client does not implement interactive confirmation today, so use in a trusted environment or with care for destructive tools (Bash, Write, Edit).
- **Working directory:** For file-relative behavior (Read, Write, LS, etc.), the server’s cwd matters. If HomeClaw spawns `claude mcp serve`, set `cwd` in the server config if your MCP client supports it; otherwise ensure Claude Code is started in the desired project directory.

---

## 6. References

- [Connect Claude Code to tools via MCP](https://docs.anthropic.com/en/docs/claude-code/mcp) — “Use Claude Code as an MCP server” section.
- [Claude Code tools reference](https://code.claude.com/docs/en/tools-reference) — Built-in tools (Read, Write, Edit, Bash, etc.).
- [GitHub anthropics/claude-code #631](https://github.com/anthropics/claude-code/issues/631) — Confirms built-in tools only, no MCP proxy; lists tool names (Agent, Bash, Edit, Glob, Grep, LS, MultiEdit, NotebookEdit, NotebookRead, Read, TodoRead, TodoWrite, WebFetch, WebSearch, Write, Task).

---

## 7. Next steps

1. **Verify tool list:** In a dev setup, add `claude-code` to `tools.mcp.servers`, run Core, and call **mcp_list_tools(server_id='claude-code')**; record the exact tool names and schemas.
2. **Optional “Claude” friend:** Add a preset (e.g. `claude`) with tools_preset that includes only `mcp_list_tools` and `mcp_call`, and a system prompt that restricts usage to `server_id='claude-code'`.
3. **Optional doc:** Add a short “Using Claude Code with HomeClaw” section (or doc) that points to this investigation and to docs/mcp.md for MCP config.
