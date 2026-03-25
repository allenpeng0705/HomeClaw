#!/usr/bin/env python3
"""
Cursor MCP entry point: run this file by absolute path (no ``python -m``, no PYTHONPATH).

Example (conda):

    "command": "/opt/anaconda3/envs/pytorch/bin/python",
    "args": ["/absolute/path/to/HomeClaw/homeclaw_memex_mcp.py"]
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_target = Path(__file__).resolve().parent / "external_plugins" / "cursor_bridge" / "memex_mcp.py"
if not _target.is_file():
    print(f"homeclaw_memex_mcp: expected launcher at {_target}", file=sys.stderr)
    sys.exit(1)
runpy.run_path(str(_target), run_name="__main__")
