"""
Tests for Portal Step 3: /setup, /login, /dashboard, root redirects, session cookie.
Uses temp config dir (monkeypatch) so admin state is controlled per test.
"""
import pytest

from portal.app import app
from tests.sync_asgi_client import SyncASGIClient


@pytest.fixture
def client():
    with SyncASGIClient(app) as c:
        yield c


def test_root_redirects_to_app_when_no_admin(portal_temp_config, client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/app"


def test_setup_get_redirects_to_spa_setup_when_no_admin(portal_temp_config, client):
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/app/setup"


def test_setup_get_follows_to_spa_shell(portal_temp_config, client):
    r = client.get("/setup")
    assert r.status_code == 200
    text = r.text or ""
    assert "HomeClaw Portal" in text
    assert "/static/app/" in text


def test_setup_post_creates_admin_and_redirects_to_login(portal_temp_config, client):
    r = client.post("/setup", data={"username": "admin", "password": "secret123"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/login"


def test_after_setup_root_redirects_to_app(portal_temp_config, client):
    client.post("/setup", data={"username": "admin", "password": "secret123"})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/app"


def test_login_post_sets_cookie_and_redirects_to_dashboard(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.post("/login", data={"username": "u", "password": "p"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/dashboard"
    assert "portal_session" in r.cookies


def test_dashboard_without_session_redirects_to_app(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/app"


def test_dashboard_with_session_returns_200(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    client.post("/login", data={"username": "u", "password": "p"})
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Dashboard" in (r.text or "")


def test_root_with_session_redirects_to_dashboard(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    client.post("/login", data={"username": "u", "password": "p"})
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/dashboard"


def test_login_wrong_password_redirects_to_login_with_error(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.post("/login", data={"username": "u", "password": "wrong"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/login?error=1"


def test_settings_without_session_redirects_to_app(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    r = client.get("/settings", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/app"


def test_settings_with_session_returns_200(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    client.post("/login", data={"username": "u", "password": "p"})
    r = client.get("/settings")
    assert r.status_code == 200
    assert "Manage settings" in (r.text or "")


def test_logout_clears_cookie_and_redirects(portal_temp_config, client):
    client.post("/setup", data={"username": "u", "password": "p"})
    client.post("/login", data={"username": "u", "password": "p"})
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/app/login"
    # Cookie should be cleared (max-age=0 or missing)
    set_cookie = r.headers.get("set-cookie") or ""
    # Cookie cleared: either portal_session appears (to clear it) or max-age=0 is set.
    assert "max-age=0" in set_cookie.lower(), f"Cookie should be cleared with max-age=0, got: {set_cookie}"
