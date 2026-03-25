# Bundled memex (Cursor bridge pack)

Pinned **[`@touchskyer/memex`](https://www.npmjs.com/package/@touchskyer/memex)** for the HomeClaw MCP launcher:

```bash
python -m external_plugins.cursor_bridge.memex_mcp
```

From any directory you can also run `../homeclaw_memex_mcp.sh` (macOS/Linux) or `..\homeclaw_memex_mcp.cmd` (Windows), which `cd` to the repo root first.

From the **HomeClaw repo root**, install once (macOS, Linux, or Windows — **Command Prompt** / **PowerShell**):

```bash
cd external_plugins/cursor_bridge/bundled_memex
npm ci
```

On Windows you can use `cd external_plugins\cursor_bridge\bundled_memex` if you prefer.

Use **`npm ci`** so versions match `package-lock.json`. After that, point Cursor’s MCP config at `python` with args `-m`, `external_plugins.cursor_bridge.memex_mcp` (see [memex with Cursor & Claude Code](../../../docs/memex-with-cursor-and-claude.md)).

`node_modules/` is gitignored; only `package.json` and `package-lock.json` are tracked.
