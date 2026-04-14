"""HTTP-level smoke for Claw-Code routes (in-process ASGI via httpx.AsyncClient; no running Core).

Uses AsyncClient + ASGITransport so tests pass with httpx 0.28+ (FastAPI TestClient is incompatible with httpx>=0.28 on some stacks; see requirements.txt).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from core.routes import clawcode_api


@pytest.fixture
def clawcode_asgi_app(tmp_path, monkeypatch):
    import core.clawcode_store as cs

    monkeypatch.setattr(cs, "sessions_base_dir", lambda: tmp_path / "cc_http")
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"enabled": True, "allowed_roots": []}
        )
        app = FastAPI()
        core = MagicMock()
        app.add_api_route(
            "/api/clawcode/sessions/{session_id}",
            clawcode_api.get_api_clawcode_session_patch_handler(core),
            methods=["PATCH"],
        )
        yield app, tmp_path


def _run(coro):
    return asyncio.run(coro)


def test_patch_session_http_ok_and_403(clawcode_asgi_app):
    app, tmp_path = clawcode_asgi_app
    from core import clawcode_store

    cwd = tmp_path / "repo"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]

    async def inner():
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            r403 = await ac.patch(
                f"/api/clawcode/sessions/{sid}",
                params={"owner_user_id": "bob"},
                json={"git_remote_hint": "x"},
            )
            assert r403.status_code == 403
            r200 = await ac.patch(
                f"/api/clawcode/sessions/{sid}",
                params={"owner_user_id": "alice"},
                json={"git_remote_hint": "origin main", "main_llm_ref": "cloud_models/X"},
            )
            assert r200.status_code == 200
            body = r200.json()
            assert body.get("git_remote_hint") == "origin main"
            assert body.get("main_llm_ref") == "cloud_models/X"
            assert "worktree_hint" in body
            assert "usage_hint" in body

    _run(inner())


def test_patch_session_http_400_empty_patch(clawcode_asgi_app):
    app, tmp_path = clawcode_asgi_app
    from core import clawcode_store

    cwd = tmp_path / "r2"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u", cwd=str(cwd))
    sid = rec["clawcode_session_id"]

    async def inner():
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.patch(
                f"/api/clawcode/sessions/{sid}",
                params={"owner_user_id": "u"},
                json={},
            )
            assert r.status_code == 400
            assert "error" in r.json()

    _run(inner())
