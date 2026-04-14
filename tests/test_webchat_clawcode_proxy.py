"""WebChat channel proxies Claw-Code API to Core (mocked httpx, no live Core)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_clawcode_proxy_forwards_to_core_url():
    from channels.webchat import channel as wc

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"sessions": [{"clawcode_session_id": "x"}]}
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.content = b"{}"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            assert "/api/clawcode/sessions" in url
            assert "owner_user_id=u" in url
            return mock_resp

    _real_async_client = httpx.AsyncClient

    def async_client_factory(*args, **kwargs):
        # ASGI test client uses AsyncClient(transport=ASGITransport(...)); proxy uses AsyncClient(timeout=...).
        if kwargs.get("transport") is not None:
            return _real_async_client(*args, **kwargs)
        return FakeClient()

    with patch.object(wc, "get_core_url", return_value="http://core.test:9000"):
        with patch("httpx.AsyncClient", side_effect=async_client_factory):
            transport = httpx.ASGITransport(app=wc.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://webchat") as client:
                r = await client.get("/api/clawcode/sessions", params={"owner_user_id": "u"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("sessions") and body["sessions"][0].get("clawcode_session_id") == "x"


@pytest.mark.asyncio
async def test_inbound_proxy_non_stream_json():
    from channels.webchat import channel as wc

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "ok", "format": "plain"}
    mock_resp.headers = {"content-type": "application/json"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            assert url.endswith("/inbound")
            return mock_resp

    _real_async_client = httpx.AsyncClient

    def async_client_factory(*args, **kwargs):
        if kwargs.get("transport") is not None:
            return _real_async_client(*args, **kwargs)
        return FakeClient()

    with patch.object(wc, "get_core_url", return_value="http://core.test:9000"):
        with patch("httpx.AsyncClient", side_effect=async_client_factory):
            transport = httpx.ASGITransport(app=wc.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://webchat") as client:
                r = await client.post(
                    "/api/inbound",
                    json={"user_id": "a", "text": "hi", "stream": False},
                )
    assert r.status_code == 200
    assert r.json().get("text") == "ok"
