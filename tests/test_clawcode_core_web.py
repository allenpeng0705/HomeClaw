"""Core-served Claw-Code browser UI: GET /clawcode and GET /clawcode/config (ASGI, no live Core)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from core.routes import clawcode_web


@pytest.fixture
def clawcode_web_app():
    app = FastAPI()
    app.add_api_route(
        "/clawcode/config",
        clawcode_web.get_clawcode_web_config_handler(None),
        methods=["GET"],
    )
    app.add_api_route(
        "/clawcode",
        clawcode_web.get_clawcode_page_handler(),
        methods=["GET"],
    )
    return app


@pytest.mark.asyncio
async def test_clawcode_page_200_html(clawcode_web_app):
    transport = ASGITransport(app=clawcode_web_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/clawcode")
    assert r.status_code == 200
    ct = r.headers.get("content-type") or ""
    assert "text/html" in ct
    assert "Claw-Code" in r.text


@pytest.mark.asyncio
async def test_clawcode_config_default_user(clawcode_web_app):
    transport = ASGITransport(app=clawcode_web_app)
    with patch("base.util.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(clawcode={})
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/clawcode/config")
    assert r.status_code == 200
    assert r.json().get("user_id") == "webchat_user"


@pytest.mark.asyncio
async def test_clawcode_config_web_ui_default_user_id(clawcode_web_app):
    transport = ASGITransport(app=clawcode_web_app)
    with patch("base.util.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"web_ui_default_user_id": "alice"}
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/clawcode/config")
    assert r.status_code == 200
    assert r.json().get("user_id") == "alice"
