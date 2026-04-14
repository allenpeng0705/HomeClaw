"""Optional smoke: official `mcp` package + homeclaw_mcp server module.

Skipped automatically when `mcp` is not installed (`pip install mcp`).
"""

from __future__ import annotations

import pytest


def test_homeclaw_mcp_server_module_imports() -> None:
    pytest.importorskip("mcp")

    from clients.homeclaw_mcp import server as homeclaw_mcp_server

    assert callable(getattr(homeclaw_mcp_server, "main", None))
