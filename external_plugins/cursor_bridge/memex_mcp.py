"""
Run bundled @touchskyer/memex in MCP mode (stdio).

Use this as the MCP server command in Cursor or Claude Code so you do not need a
global `npm install -g @touchskyer/memex`. Install deps once:

    cd external_plugins/cursor_bridge/bundled_memex && npm ci

Requires Node.js 18+ on PATH. Cards still live under ~/.memex/cards/ (memex default).

Cursor MCP: prefer invoking this file by absolute path (``python3 /path/to/.../memex_mcp.py``)
so you do not need ``cwd`` or ``PYTHONPATH`` for ``external_plugins``. See docs/memex-with-cursor-and-claude.md.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_BUNDLE_DIR = Path(__file__).resolve().parent / "bundled_memex"
_MEMEX_CLI = _BUNDLE_DIR / "node_modules" / "@touchskyer" / "memex" / "dist" / "cli.js"


def main() -> None:
    node = shutil.which("node")
    if not node:
        print(
            "homeclaw-memex-mcp: Node.js 18+ is required. Install Node and ensure `node` is on PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not _MEMEX_CLI.is_file():
        print(
            "homeclaw-memex-mcp: bundled memex is missing. Install it with:\n"
            f"  cd {_BUNDLE_DIR}\n"
            "  npm ci",
            file=sys.stderr,
        )
        sys.exit(1)
    argv = [node, str(_MEMEX_CLI), "mcp"]
    if len(sys.argv) > 1:
        argv.extend(sys.argv[1:])
    # Windows: os.execv to another interpreter is brittle for MCP stdio; inherit console handles explicitly.
    if os.name == "nt":
        p = subprocess.run(
            argv,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            close_fds=False,
        )
        sys.exit(p.returncode)
    os.execv(node, argv)


if __name__ == "__main__":
    main()
