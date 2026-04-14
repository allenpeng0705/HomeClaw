"""WebChat channel: Claw-Code static page and proxy routes (ASGI, no live Core)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_clawcode_page_served():
    from channels.webchat.channel import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/clawcode")
    assert r.status_code == 200
    assert b"Claw-Code" in r.content
    assert b"clawcode_session_id" in r.content
    assert b"Run activity" in r.content
    assert b"Workspace" in r.content
