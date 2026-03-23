# Coding with HomeClaw

HomeClaw can drive **Cursor**, **Claude Code**, and **Trae Agent** on your dev machine — from your phone, tablet, or any device. Open projects, run AI agents, execute commands, and see results, all through chat.

---

## Why use HomeClaw for coding?

Imagine you're away from your desk but want to:

- Have Cursor fix a bug in your project
- Run Claude Code to write tests
- Execute `npm test` and see the results
- Open a project and start coding when you get back

With HomeClaw, you chat with a **Cursor friend** or **ClaudeCode friend** in the Companion App (or Telegram, or any channel), and HomeClaw runs those tools on your dev machine and sends you the results.

---

## Quick start: Cursor via Companion App

### 1. Start the bridge server

On the machine where Cursor is installed:

```bash
python -m external_plugins.cursor_bridge.server
```

This starts a bridge server on port 3104 that connects HomeClaw to Cursor.

### 2. Add the Cursor friend

Edit `config/user.yml` and add the Cursor friend to your user:

```yaml
users:
  - name: Alice
    id: alice
    friends:
      - name: HomeClaw
      - name: Cursor
        preset: cursor
```

Restart Core.

### 3. Chat with Cursor

In the Companion App, tap **Cursor** in your friends list and say:

- *"Open /Users/alice/myproject in Cursor"*
- *"Run Cursor agent to add unit tests for the auth module"*
- *"Run npm test and show me the results"*
- *"What's the status of the current project?"*

HomeClaw sends the task to Cursor on your dev machine and returns the output to your chat.

---

## Quick start: Claude Code via Companion App

### 1. Install Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

### 2. Start the bridge server

Same server as Cursor — it handles both:

```bash
python -m external_plugins.cursor_bridge.server
```

### 3. Add the ClaudeCode friend

```yaml
users:
  - name: Alice
    id: alice
    friends:
      - name: HomeClaw
      - name: ClaudeCode
        preset: claude-code
```

Restart Core.

### 4. Chat with Claude Code

Tap **ClaudeCode** in the Companion App:

- *"Set project to /Users/alice/myapp"*
- *"Run Claude to refactor the database module"*
- *"Run Claude agent to fix the failing tests"*
- *"Run git status in the project"*

---

## Quick start: Trae Agent

[Trae Agent](https://github.com/bytedance/trae-agent) is an open-source CLI agent for software engineering.

### 1. Install Trae Agent

```bash
git clone https://github.com/bytedance/trae-agent.git
cd trae-agent
uv sync
```

Create a `trae_config.yaml` with your API key (see the [Trae Agent README](https://github.com/bytedance/trae-agent)).

### 2. Enable Trae in HomeClaw

In `config/skills_and_plugins.yml`:

```yaml
trae_agent_enabled: true
cursor_bridge_trae_agent_path: "/path/to/trae-agent/.venv/bin/trae-cli"
cursor_bridge_trae_agent_config: "/path/to/trae_config.yaml"
```

### 3. Add the Trae friend

```yaml
friends:
  - name: Trae
    preset: trae
```

Restart Core.

---

## What each friend can do

| Capability | Cursor | Claude Code | Trae |
|-----------|--------|------------|------|
| Open a project | Yes | Set CWD | Set CWD |
| Open a file | Yes | — | — |
| Run AI agent on a task | Yes (Cursor CLI) | Yes (Claude CLI) | Yes (trae-cli) |
| Run shell commands | Yes | Yes | Yes |
| Get project status | Yes | Yes | Yes |
| Interactive terminal (PTY) | Yes | Yes | Yes |

---

## Bridge architecture

All three tools share the same bridge server (`external_plugins/cursor_bridge/server.py`):

```
Companion App / Telegram / WebChat
        │
        ▼
   HomeClaw Core (port 9000)
        │
        ▼
   Bridge Server (port 3104)
   ├── Cursor IDE
   ├── Claude Code CLI
   └── Trae CLI
```

The bridge runs on the machine where your IDEs and CLIs are installed. HomeClaw Core can be on the same machine or a different one.

### Bridge on a different machine

If Core runs on a server but your dev tools are on your laptop:

1. Run the bridge on your laptop: `python -m external_plugins.cursor_bridge.server`
2. Edit `plugins/CursorBridge/plugin.yaml` and set `config.base_url` to your laptop's IP:

```yaml
config:
  base_url: "http://192.168.1.100:3104"
```

Or use a Tailscale IP if your machines are on different networks.

---

## Using Claude Code as an MCP server

Besides the bridge (which sends tasks to the Claude Code CLI), you can also use Claude Code as an **MCP server** — exposing its built-in tools (Read, Write, Edit, Bash, etc.) directly to HomeClaw's LLM.

### Setup

In `config/skills_and_plugins.yml`:

```yaml
tools:
  mcp:
    enabled: true
    auto_register_claude_code: true
```

Or manually add the server:

```yaml
tools:
  mcp:
    enabled: true
    servers:
      claude-code:
        transport: stdio
        command: claude
        args: [mcp, serve]
```

### When to use which

| Method | Best for |
|--------|----------|
| **Bridge (ClaudeCode friend)** | Natural-language tasks: "fix the bug", "add tests". Claude Code CLI runs autonomously. |
| **MCP server** | Fine-grained tool calls: HomeClaw's LLM can call Read, Write, Edit, Bash by name. |

You can use both: the ClaudeCode friend for interactive CLI tasks, and MCP for programmatic tool access.

---

## Install Cursor CLI and Claude Code with HomeClaw

The install script can set up both:

**Mac / Linux:**

```bash
HOMECLAW_INSTALL_CURSOR_CLI=1 HOMECLAW_INSTALL_CLAUDE_CODE=1 bash install.sh
```

**Windows:**

```powershell
$env:HOMECLAW_INSTALL_CURSOR_CLI="1"; $env:HOMECLAW_INSTALL_CLAUDE_CODE="1"; .\install.ps1
```

---

## Tips

- **Bridge must be running** on the dev machine for Cursor/Claude Code/Trae friends to work. Start it with `python -m external_plugins.cursor_bridge.server`.
- **Long-running tasks:** AI agent tasks can take several minutes. The Companion App uses async mode (returns 202, then polls for results) so the connection doesn't time out.
- **Security:** The bridge server has no auth by default. Only run it on trusted networks or behind a firewall. If Core and the bridge are on different machines, consider using Tailscale or SSH tunneling.
- **Interactive sessions:** You can start an interactive PTY session from the Companion App for real-time terminal access to Cursor or Claude Code.
- **Separate active projects:** Cursor, Claude Code, and Trae each maintain their own "active project" path. Setting one doesn't change the others.
