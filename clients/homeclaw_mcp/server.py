"""
Stdio MCP server: exposes tools that call HomeClaw Core (GET /ready, POST /inbound).

Run: python3 -m clients.homeclaw_mcp  (from repo root; requires pip install mcp httpx)
Env: HOMECLAW_CORE_URL (default http://127.0.0.1:9000), HOMECLAW_API_KEY when Core auth is on.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def main() -> None:
    try:
        import asyncio

        import httpx
        import mcp.server.stdio
        import mcp.types as types
        from mcp.server.lowlevel import NotificationOptions, Server
        from mcp.server.models import InitializationOptions
    except ImportError as e:
        print("Install: pip install mcp httpx", file=sys.stderr)
        raise SystemExit(2) from e

    raw_base = (
        os.environ.get("HOMECLAW_CORE_URL")
        or os.environ.get("HOMCLAW_CORE_URL")
        or "http://127.0.0.1:9000"
    )
    base = str(raw_base).strip().rstrip("/")
    api_key = (os.environ.get("HOMECLAW_API_KEY") or "").strip()

    def _headers() -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if api_key:
            h["X-API-Key"] = api_key
        return h

    server = Server("homeclaw-mcp")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="homeclaw_ready",
                description="Check HomeClaw Core readiness (GET /ready).",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="homeclaw_inbound",
                description="Send one user message to Core via POST /inbound and return the assistant reply text.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "User message (required)."},
                        "user_id": {"type": "string", "description": "Core user_id (default: mcp_client)."},
                        "friend_id": {"type": "string", "description": "Friend / assistant id (optional)."},
                        "clawcode_session_id": {"type": "string", "description": "Optional Claw-Code session UUID."},
                        "tool_profile": {
                            "type": "string",
                            "description": "Optional: minimal, messaging, coding, clawcode, full.",
                        },
                        "channel_name": {"type": "string", "description": "Default: mcp."},
                    },
                    "required": ["text"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
        args = arguments or {}
        timeout = httpx.Timeout(600.0, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            if name == "homeclaw_ready":
                r = await client.get(f"{base}/ready", headers=_headers())
                body = (r.text or "").strip() or f"HTTP {r.status_code}"
                return [types.TextContent(type="text", text=body)]
            if name == "homeclaw_inbound":
                text = str(args.get("text") or "").strip()
                if not text:
                    return [types.TextContent(type="text", text="error: text is required")]
                payload: dict[str, Any] = {
                    "user_id": (args.get("user_id") or "mcp_client").strip() or "mcp_client",
                    "text": text,
                    "channel_name": (args.get("channel_name") or "mcp").strip() or "mcp",
                }
                fid = str(args.get("friend_id") or "").strip()
                if fid:
                    payload["friend_id"] = fid
                cc = str(args.get("clawcode_session_id") or "").strip()
                if cc:
                    payload["clawcode_session_id"] = cc
                tp = str(args.get("tool_profile") or "").strip()
                if tp:
                    payload["tool_profile"] = tp
                r = await client.post(f"{base}/inbound", headers=_headers(), json=payload)
                try:
                    data = r.json()
                except Exception:
                    data = None
                if isinstance(data, dict):
                    if r.status_code >= 400:
                        err = data.get("error") or data.get("detail") or r.text
                        return [types.TextContent(type="text", text=f"error HTTP {r.status_code}: {err}")]
                    if "text" in data:
                        return [types.TextContent(type="text", text=str(data.get("text") or ""))]
                    if data.get("error"):
                        return [types.TextContent(type="text", text=f"error: {data.get('error')}")]
                return [types.TextContent(type="text", text=f"HTTP {r.status_code}: {(r.text or '')[:4000]}")]
            return [types.TextContent(type="text", text=f"unknown tool: {name}")]

    async def run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="homeclaw-mcp",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    asyncio.run(run())
