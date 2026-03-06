import pytest


def test_clawhub_search_parses_json(monkeypatch):
    from base import clawhub_integration as mod

    def fake_run_cmd(argv, **kwargs):  # noqa: ARG001
        # Simulate: clawhub search ... --json
        return mod.ClawHubResult(
            ok=True,
            stdout='[{"id":"summarize","name":"summarize","description":"Text summarization","downloads":123,"stars":4.8}]',
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(mod, "_run_cmd", fake_run_cmd)
    results, raw = mod.clawhub_search("summarize", limit=5)
    assert raw.ok is True
    assert isinstance(results, list)
    assert results and results[0]["id"] == "summarize"
    assert "description" in results[0]


def test_find_openclaw_installed_skill_dir_prefers_exact(tmp_path, monkeypatch):
    from base import clawhub_integration as mod

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "weather").mkdir()
    (skills_dir / "weather-extra").mkdir()

    monkeypatch.setattr(mod, "_candidate_openclaw_skills_dirs", lambda: [skills_dir])
    found = mod.find_openclaw_installed_skill_dir("weather")
    assert found is not None
    assert found.name == "weather"


@pytest.fixture
def portal_temp_config(monkeypatch, tmp_path):
    """Point portal config and auth to tmp_path."""
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
    import portal.config as config_mod
    import portal.auth as auth_mod
    monkeypatch.setattr(config_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(auth_mod, "get_config_dir", lambda: tmp_path)
    return tmp_path


def test_portal_skills_page_requires_login(portal_temp_config):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
    from fastapi.testclient import TestClient
    from portal.app import app

    client = TestClient(app)
    # no admin yet -> redirect to setup
    r = client.get("/skills", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers.get("location") == "/setup"


def test_portal_skills_search_api_returns_results(monkeypatch, portal_temp_config, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
    from fastapi.testclient import TestClient
    from portal.app import app

    # setup + login
    client = TestClient(app)
    client.post("/setup", data={"username": "admin", "password": "pw"})
    client.post("/login", data={"username": "admin", "password": "pw"})

    # mock clawhub
    from base import clawhub_integration as chi

    monkeypatch.setattr(chi, "clawhub_available", lambda: True)
    monkeypatch.setattr(
        chi,
        "clawhub_search",
        lambda query, limit=20, timeout_s=30: ([{"id": "summarize", "name": "summarize", "description": "Text"}], chi.ClawHubResult(ok=True)),
    )

    r = client.get("/api/portal/skills/search?query=summarize")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert data["results"] and data["results"][0]["id"] == "summarize"

