"""
Tests for Portal Step 3: /setup, /login, /dashboard, root redirects, session cookie.
Uses temp config dir (monkeypatch) so admin state is controlled per test.
"""
import pytest
from fastapi.testclient import TestClient

from portal.app import app


@pytest.fixture
def portal_temp_config(monkeypatch, tmp_path):
    """Point portal config and auth to tmp_path."""
    import portal.config as config_mod
    import portal.auth as auth_mod
    monkeypatch.setattr(config_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(auth_mod, "get_config_dir", lambda: tmp_path)
    return tmp_path


def test_root_redirects_to_setup_when_no_admin(portal_temp_config):
    client = TestClient(app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/setup"


def test_setup_get_returns_200_when_no_admin(portal_temp_config):
    client = TestClient(app)
    r = client.get("/setup")
    assert r.status_code == 200
    assert "Set admin account" in (r.text or "")


def test_setup_post_creates_admin_and_redirects_to_login(portal_temp_config):
    client = TestClient(app)
    r = client.post("/setup", data={"username": "admin", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/login"


def test_after_setup_root_redirects_to_login(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "admin", "password": "secret123"})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/login"


def test_login_post_sets_cookie_and_redirects_to_dashboard(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.post("/login", data={"username": "u", "password": "p"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/dashboard"
    assert "portal_session" in r.cookies


def test_dashboard_without_session_redirects_to_login(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/login"


def test_dashboard_with_session_returns_200(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "u", "password": "p"})
    client.post("/login", data={"username": "u", "password": "p"})
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Dashboard" in (r.text or "")


def test_root_with_session_redirects_to_dashboard(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "u", "password": "p"})
    client.post("/login", data={"username": "u", "password": "p"})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/dashboard"


def test_login_wrong_password_redirects_to_login_with_error(portal_temp_config):
    client = TestClient(app)
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.post("/login", data={"username": "u", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/login?error=1"
