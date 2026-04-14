# homeclaw-mcp (stdio)

First-party **Model Context Protocol** server over **stdio** so desktop tools (Cursor, Claude Desktop, etc.) can call your **HomeClaw Core** over HTTP.

## Python environment

On this project, prefer **`conda activate pytorch`** (includes **`mcp`** and **`httpx`**). Otherwise:

```bash
pip install mcp httpx
```

(`mcp` is the official [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk); not pinned in the main HomeClaw `requirements.txt`.)

## Run

From the repo root:

```bash
export HOMECLAW_CORE_URL=http://127.0.0.1:9000
export HOMECLAW_API_KEY=...   # if Core uses auth_enabled
python3 -m clients.homeclaw_mcp
```

Or:

```bash
python3 -m main homeclaw_mcp
```

## Tools

| Tool | Purpose |
|------|--------|
| `homeclaw_ready` | `GET /ready` — quick health check |
| `homeclaw_inbound` | `POST /inbound` with `text`, optional `user_id`, `friend_id`, `clawcode_session_id`, `tool_profile` |

Secrets stay in env / Core config; do not paste API keys into MCP chat prompts.

## Cursor / Claude Desktop

Add a stdio server entry pointing at `python3` with args `-m`, `clients.homeclaw_mcp` and `cwd` = this repository root (or use `python3 -m main homeclaw_mcp` from the same root).
