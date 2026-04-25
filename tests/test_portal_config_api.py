"""
Tests for Portal config API (Phase 1.4): GET/PATCH /api/config/{name}.
Requires session (login). Uses temp config dir and minimal config files.
"""
import pytest

from portal.app import app
from tests.sync_asgi_client import SyncASGIClient


@pytest.fixture
def client():
    with SyncASGIClient(app) as c:
        yield c


def test_config_get_without_session_returns_401(portal_temp_config, client):
    r = client.get("/api/config/llm")
    assert r.status_code == 401
    assert "detail" in r.json()


def test_config_get_with_session_returns_200(portal_temp_config, client):
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/llm")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_config_get_unknown_name_returns_404(portal_temp_config, client):
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/unknown_name")
    assert r.status_code == 404


def test_config_patch_without_session_returns_401(portal_temp_config, client):
    r = client.patch("/api/config/llm", json={"main_llm": "test"})
    assert r.status_code == 401


def test_config_patch_with_session_returns_200(portal_temp_config, client):
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.patch("/api/config/llm", json={"main_llm": "some_model"})
    assert r.status_code == 200
    assert r.json().get("result") == "ok"
    # Verify file updated with the patched value
    content = (portal_temp_config / "llm.yml").read_text(encoding="utf-8")
    assert "some_model" in content, f"Expected 'some_model' in patched llm.yml, got: {content}"


def test_config_get_core_redacts_auth_api_key(portal_temp_config, client):
    (portal_temp_config / "core.yml").write_text(
        "name: core\nauth_api_key: secret123\nhost: 0.0.0.0\n", encoding="utf-8"
    )
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/core")
    assert r.status_code == 200
    data = r.json()
    assert data.get("auth_api_key") == "***"
    assert "secret123" not in str(data)


def test_config_get_user_returns_users_list(portal_temp_config, client):
    (portal_temp_config / "user.yml").write_text(
        "users:\n  - id: u1\n    name: User One\n    password: hidden\n", encoding="utf-8"
    )
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/user")
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    assert isinstance(data["users"], list)
    # Password should be redacted
    for u in data["users"]:
        if u.get("password"):
            assert u["password"] == "***"
            break
    else:
        assert len(data["users"]) >= 1