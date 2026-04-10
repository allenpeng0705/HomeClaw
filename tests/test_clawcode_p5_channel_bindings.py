"""P5: channel binding store + command parser."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from channels.clawcode_binding import parse_clawcode_command
from core import clawcode_channel_bindings, clawcode_store
from core.clawcode_store import prepare_prompt_request_clawcode, validate_clawcode_turn


@pytest.fixture
def mock_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(clawcode_store, "sessions_base_dir", lambda: tmp_path / "cc_sess")
    monkeypatch.setattr(clawcode_channel_bindings, "_path", lambda: tmp_path / "bindings.json")
    with patch("core.clawcode_store.Util") as mock_u, patch("core.clawcode_channel_bindings.Util") as mock_u2:
        meta = SimpleNamespace(clawcode={"enabled": True, "allowed_roots": []})
        mock_u.return_value.get_core_metadata.return_value = meta
        mock_u.return_value.root_path.return_value = str(tmp_path)
        mock_u2.return_value.root_path.return_value = str(tmp_path)
        yield tmp_path


def test_parse_telegram_variants():
    assert parse_clawcode_command("/clawcode status") == ("status", [])
    assert parse_clawcode_command("/clawcode@SomeBot bind abc") == ("bind", ["abc"])
    assert parse_clawcode_command("!clawcode clear") == ("clear", [])
    assert parse_clawcode_command("hello") is None


def test_validate_clawcode_turn_owner(mock_bindings, tmp_path):
    cwd = tmp_path / "r"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    assert validate_clawcode_turn(sid, "alice") == (None, None)
    err, code = validate_clawcode_turn(sid, "bob")
    assert err and code == 403


def test_validate_clawcode_turn_matches_system_user_id(mock_bindings, tmp_path):
    """IM channel user_id (e.g. telegram_1) may differ from session owner (alice) when user.yml maps to alice."""
    cwd = tmp_path / "r2"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    err, code = validate_clawcode_turn(sid, "telegram_1", system_user_id="alice")
    assert (err, code) == (None, None)
    err2, code2 = validate_clawcode_turn(sid, "telegram_1", system_user_id="bob")
    assert err2 and code2 == 403


def test_prepare_merges_binding_using_system_user_id(mock_bindings, tmp_path):
    cwd = tmp_path / "r3"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    clawcode_channel_bindings.set_binding("alice", sid)
    pr = SimpleNamespace(
        request_metadata={},
        user_id="telegram_99",
        system_user_id="alice",
        tool_profile=None,
    )
    assert prepare_prompt_request_clawcode(pr) is None
    assert pr.request_metadata.get("clawcode_session_id") == sid


def test_bindings_roundtrip(mock_bindings, tmp_path):
    cwd = tmp_path / "r"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="telegram_1", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    clawcode_channel_bindings.set_binding("telegram_1", sid)
    assert clawcode_channel_bindings.get_binding("telegram_1") == sid
    clawcode_channel_bindings.clear_binding("telegram_1")
    assert clawcode_channel_bindings.get_binding("telegram_1") is None


def test_run_cli_channel_status_requires_url(tmp_path, monkeypatch):
    from clients.clawcode import cli as claw_cli

    monkeypatch.setattr(claw_cli, "config_path", lambda: tmp_path / "c.json")
    rc = claw_cli.run_cli(["channel", "status"])
    assert rc == 2
