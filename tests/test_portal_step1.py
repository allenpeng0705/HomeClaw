"""
Tests for Portal (Step 1): minimal server and routes.
Uses FastAPI TestClient; no running server or uvicorn required.
"""
import pytest
from fastapi.testclient import TestClient

from portal.app import app

client = TestClient(app)


def test_root_returns_200_and_text():
    r = client.get("/")
    assert r.status_code == 200
    assert "Portal" in (r.text or "")


def test_ready_returns_200():
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.text.strip() == "ok"


def test_status_returns_json():
    r = client.get("/api/portal/status")
    assert r.status_code == 200
    data = r.json()
    assert data.get("service") == "portal"
    assert "config_dir" in data
    assert "config_dir_exists" in data
    assert isinstance(data["config_dir_exists"], bool)


def test_404_for_unknown_path():
    r = client.get("/nonexistent")
    assert r.status_code == 404
