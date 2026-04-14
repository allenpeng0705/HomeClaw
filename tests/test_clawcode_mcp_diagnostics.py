"""Claw-Code Milestone C: MCP server list (sanitized config)."""

from __future__ import annotations

import pytest


def test_list_mcp_servers_sanitized(monkeypatch):
    from core import clawcode_mcp_diagnostics as m

    def fake_cfg():
        return {
            "mcp": {
                "servers": {
                    "demo": {
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "@demo/mcp"],
                    },
                    "remote": {"transport": "sse", "url": "http://127.0.0.1:9/sse"},
                }
            }
        }

    monkeypatch.setattr(m, "_get_tools_config", fake_cfg)
    d = m.list_mcp_servers_sanitized()
    assert d.get("mcp_enabled") is True
    ids = {s["server_id"] for s in d.get("servers") or []}
    assert ids == {"demo", "remote"}
    for row in d["servers"]:
        assert "server_id" in row and "transport" in row
