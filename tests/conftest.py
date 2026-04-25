"""
Shared pytest fixtures for HomeClaw tests.
"""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from base.tools import ToolContext
from base.util import Util


# ---------------------------------------------------------------------------
# Portal temp config fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def portal_temp_config(monkeypatch, tmp_path):
    """Point portal config and auth to tmp_path; create minimal config files."""
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
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


# ---------------------------------------------------------------------------
# ToolContext fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_context():
    """Minimal ToolContext for pending_user_action_dispatch tests."""
    return ToolContext(
        core=None,
        app_id="homeclaw",
        user_name="",
        user_id="u1",
        friend_id="HomeClaw",
        session_id="",
        request=None,
    )


@pytest.fixture
def ctx_u1():
    """ToolContext with user_id u1 for sandbox filename search tests."""
    return ToolContext(core=None, user_id="u1")


# ---------------------------------------------------------------------------
# Util singleton fixtures (with proper teardown)
# ---------------------------------------------------------------------------


@pytest.fixture
def util_paths(monkeypatch):
    """Util singleton with main_llm_chat_path / cloud_llm_chat_path set; restored after test."""
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    original = Util._instance
    Util._instance = None
    u = Util()

    monkeypatch.setattr(u, "core_metadata", SimpleNamespace(
        main_llm_chat_path="/v1/chat/completions",
        cloud_llm_chat_path="/cloud/v1/chat/completions",
    ))
    try:
        yield u
    finally:
        Util._instance = original


@pytest.fixture
def util_with_panda(monkeypatch):
    """Util singleton with panda config; restored after test."""
    monkeypatch.setattr(Util, "has_gpu_cuda", lambda self: False)
    original = Util._instance
    Util._instance = None
    u = Util()

    monkeypatch.setattr(u, "core_metadata", SimpleNamespace(
        panda={
            "enabled": True,
            "host": "10.0.1.2",
            "port": 9090,
            "paths": {
                "main_llm": "/v1/chat",
                "cloud_llm": "/v1/cloud",
                "embedding": "/v1/embeddings",
            },
            "timeout_seconds": 45,
        }
    ))
    try:
        yield u
    finally:
        Util._instance = original


# ---------------------------------------------------------------------------
# Shared mock core metadata
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_core_metadata():
    """Minimal core metadata for tests that need ToolContext.core_metadata."""
    return SimpleNamespace(
        clawcode={"enabled": True, "allowed_roots": []},
    )


# ---------------------------------------------------------------------------
# Shared SyncASGIClient fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def portal_client():
    """ASGI test client for portal app."""
    pytest.importorskip("fastapi")
    pytest.importorskip("starlette")
    from portal.app import app
    from tests.sync_asgi_client import SyncASGIClient

    with SyncASGIClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Fake base.util for tests that must not import the real torch-dependent util
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_base_util(monkeypatch):
    """
    Inject a minimal fake base.util module to avoid loading the real one
    (which may import torch and abort in sandbox environments).

    Yields (core_metadata_value) so tests can configure the metadata before
    importing core.result_viewer.
    """
    fake_meta = SimpleNamespace(
        auth_api_key="",
        core_public_url="",
        host="127.0.0.1",
        port=9000,
        file_link_style="token",
        file_static_prefix="files",
        file_view_link_expiry_sec=None,
    )

    fake_util_mod = ModuleType("base.util")

    class _FakeUtil:
        def get_core_metadata(self):
            return fake_meta

    fake_util_mod.Util = _FakeUtil

    original = sys.modules.get("base.util")
    sys.modules["base.util"] = fake_util_mod
    try:
        yield fake_meta
    finally:
        if original is not None:
            sys.modules["base.util"] = original
        else:
            sys.modules.pop("base.util", None)
