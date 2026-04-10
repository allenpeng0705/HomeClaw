"""
Tests for Portal (Step 1): minimal server and routes.
Uses in-process ASGI via httpx (httpx 0.28+ compatible); no running server or uvicorn required.
"""
import pytest

from portal.app import app
from tests.sync_asgi_client import SyncASGIClient


@pytest.fixture
def client():
    with SyncASGIClient(app) as c:
        yield c


def test_root_returns_200_and_text(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Portal" in (r.text or "")


def test_ready_returns_200(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.text.strip() == "ok"


def test_status_returns_json(client):
    r = client.get("/api/portal/status")
    assert r.status_code == 200
    data = r.json()
    assert data.get("service") == "portal"
    assert "config_dir" in data
    assert "config_dir_exists" in data
    assert isinstance(data["config_dir_exists"], bool)


def test_404_for_unknown_path(client):
    r = client.get("/nonexistent")
    assert r.status_code == 404
