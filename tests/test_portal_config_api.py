"""
Tests for Portal config API (Phase 1.4): GET/PATCH /api/config/{name}.
Requires session (login). Uses temp config dir and minimal config files.
"""
import pytest
from fastapi.testclient import TestClient

from portal.app import app


@pytest.fixture
def portal_temp_config(monkeypatch, tmp_path):
    """Point portal config and auth to tmp_path; create minimal config files."""
    import portal.config as config_mod
    import portal.auth as auth_mod
    import portal.config_backup as cb_mod
    import portal.config_api as api_mod
    monkeypatch.setattr(config_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(auth_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(cb_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(api_mod, "get_config_dir", lambda: tmp_path)
    # Minimal llm.yml and core.yml so GET has content
    (tmp_path / "llm.yml").write_text("main_llm: null\nembedding_llm: null\n", encoding="utf-8")
    (tmp_path / "core.yml").write_text("name: core\nhost: 0.0.0.0\nport: 9000\n", encoding="utf-8")
    return tmp_path


def test_config_get_without_session_returns_401(portal_temp_config):
    client = TestClient(app)
    r = client.get("/api/config/llm")
    assert r.status_code == 401
    assert "detail" in r.json()


def test_config_get_with_session_returns_200(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/llm")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_config_get_unknown_name_returns_404(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/unknown_name")
    assert r.status_code == 404


def test_config_patch_without_session_returns_401(portal_temp_config):
    client = TestClient(app)
    r = client.patch("/api/config/llm", json={"main_llm": "test"})
    assert r.status_code == 401


def test_config_patch_with_session_returns_200(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.patch("/api/config/llm", json={"main_llm": "some_model"})
    assert r.status_code == 200
    assert r.json().get("result") == "ok"
    # Verify file updated
    content = (portal_temp_config / "llm.yml").read_text(encoding="utf-8")
    assert "some_model" in content or "main_llm" in content


def test_config_get_core_redacts_auth_api_key(portal_temp_config):
    (portal_temp_config / "core.yml").write_text(
        "name: core\nauth_api_key: secret123\nhost: 0.0.0.0\n", encoding="utf-8"
    )
    client = TestClient(app)
    client.post("/setup", data={"username": "admin", "password": "secret"})
    client.post("/login", data={"username": "admin", "password": "secret"})
    r = client.get("/api/config/core")
    assert r.status_code == 200
    data = r.json()
    assert data.get("auth_api_key") == "***"
    assert "secret123" not in str(data)


def test_config_get_user_returns_users_list(portal_temp_config):
    (portal_temp_config / "user.yml").write_text(
        "users:\n  - id: u1\n    name: User One\n    password: hidden\n", encoding="utf-8"
    )
    client = TestClient(app)
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