"""
Synchronous ASGI app tests via httpx.AsyncClient + ASGITransport.

Use when FastAPI's TestClient breaks (httpx>=0.28 removed Client(app=...); see requirements.txt).
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional

import httpx
from httpx import ASGITransport


class SyncASGIClient:
    """Minimal Starlette TestClient-style API with cookie persistence within a `with` block."""

    def __init__(self, app: Any, base_url: str = "http://test"):
        self._app = app
        self._base_url = base_url.rstrip("/")
        self._loop = asyncio.new_event_loop()
        self._ac: Optional[httpx.AsyncClient] = None

    def __enter__(self) -> SyncASGIClient:
        async def _open() -> None:
            transport = ASGITransport(app=self._app)
            self._ac = httpx.AsyncClient(transport=transport, base_url=self._base_url)
            await self._ac.__aenter__()

        self._loop.run_until_complete(_open())
        return self

    def __exit__(self, *args: Any) -> None:
        async def _close() -> None:
            if self._ac is not None:
                await self._ac.__aexit__(None, None, None)

        try:
            self._loop.run_until_complete(_close())
        finally:
            self._loop.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: Any = None,
        json: Any = None,
        follow_redirects: bool = True,
        headers: Optional[Mapping[str, str]] = None,
    ) -> httpx.Response:
        async def do() -> httpx.Response:
            assert self._ac is not None
            return await self._ac.request(
                method,
                url,
                data=data,
                json=json,
                follow_redirects=follow_redirects,
                headers=dict(headers) if headers else None,
            )

        return self._loop.run_until_complete(do())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self._request("DELETE", url, **kwargs)
