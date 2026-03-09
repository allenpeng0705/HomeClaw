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

    monkeypatch.setattr(mod, "_candidate_openclaw_skills_dirs", lambda extra_dirs=None: [skills_dir])
    found = mod.find_openclaw_installed_skill_dir("weather")
    assert found is not None
    assert found.name == "weather"


def test_clawhub_install_and_convert_creates_download_dir_when_missing(tmp_path, monkeypatch):
    """When clawhub_download_dir is set and the dir does not exist, it is created before install (cwd must exist)."""
    from pathlib import Path
    from base import clawhub_integration as mod
    from base.clawhub_integration import ClawHubResult

    staging = tmp_path / "staging"
    assert not staging.exists()

    install_cwd = []

    def fake_install(spec, *, timeout_s=180, dry_run=False, with_deps=False, cwd=None):
        install_cwd.append(cwd)
        return ClawHubResult(ok=True, returncode=0)

    def fake_convert(*, skill_id, homeclaw_root, external_skills_dir, openclaw_search_dirs=None):
        return {"ok": True, "source": str(staging), "output": str(tmp_path / "external_skills" / skill_id)}

    monkeypatch.setattr(mod, "clawhub_install", fake_install)
    monkeypatch.setattr(mod, "convert_installed_openclaw_skill_to_homeclaw", fake_convert)

    out = mod.clawhub_install_and_convert(
        skill_spec="some-skill",
        skill_id_hint="some-skill",
        homeclaw_root=Path(tmp_path),
        external_skills_dir="external_skills",
        clawhub_download_dir="staging",
    )

    assert out.get("ok") is True
    assert staging.is_dir(), "staging dir should have been created"
    assert len(install_cwd) == 1 and install_cwd[0] is not None
    assert Path(install_cwd[0]).resolve() == staging.resolve()


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


def test_core_skills_install_invalid_json_returns_400(monkeypatch):
    """POST /api/skills/install with invalid JSON body should not 500; handler falls back to empty body and returns 400 Missing skill id."""
    pytest.importorskip("fastapi")
    import asyncio
    from unittest.mock import MagicMock, AsyncMock

    try:
        from core.routes import misc_api
        from fastapi.responses import JSONResponse
    except Exception as e:
        pytest.skip(f"Core routes not importable (need full deps): {e}")

    monkeypatch.setattr("base.clawhub_integration.clawhub_available", lambda: True)

    core = MagicMock()
    handler = misc_api.get_api_skills_install_handler(core)

    request = MagicMock()
    request.headers = {"content-type": "application/json"}
    request.json = AsyncMock(side_effect=ValueError("Invalid JSON"))

    async def run():
        return await handler(request)

    response = asyncio.run(run())
    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    body = response.body.decode("utf-8") if isinstance(response.body, bytes) else str(response.body)
    assert "Missing skill id" in body

