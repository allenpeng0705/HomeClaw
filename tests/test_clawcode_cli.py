"""Claw-Code CLI: parser and config helpers (no Core)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clients.clawcode import cli as claw_cli


def test_run_cli_help_returns_zero():
    rc = claw_cli.run_cli(["--help"])
    assert rc == 0


def test_run_cli_session_new_requires_config(tmp_path, monkeypatch):
    monkeypatch.setattr(claw_cli, "config_path", lambda: tmp_path / "c.json")
    rc = claw_cli.run_cli(["session", "new", "--cwd", str(tmp_path)])
    assert rc == 2  # no login / no core_base_url


def test_config_save_load(tmp_path, monkeypatch):
    p = tmp_path / "clawcode.json"
    monkeypatch.setattr(claw_cli, "config_path", lambda: p)
    claw_cli.save_config({"core_base_url": "http://x:1", "owner_user_id": "u"})
    assert p.is_file()
    assert claw_cli.load_config().get("owner_user_id") == "u"


def test_parse_inbound_sse_done():
    lines = [
        b'data: {"event":"progress","message":"wait","tool":""}\n',
        b'data: {"event":"done","ok":true,"text":"hi","format":"plain","status":200}\n',
    ]
    ok, text, err = claw_cli._parse_inbound_sse(lines)
    assert ok and text == "hi" and not err


def test_parse_inbound_sse_no_done():
    lines = [b'data: {"event":"progress","message":"x","tool":""}\n']
    ok, text, err = claw_cli._parse_inbound_sse(lines)
    assert not ok and "done" in err


@patch("clients.clawcode.cli._client")
def test_cmd_session_new_success(mock_client_cls, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setattr(claw_cli, "config_path", lambda: cfg_path)
    cwd = tmp_path / "repo"
    cwd.mkdir()

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "clawcode_session_id": "abc-uuid",
        "owner_user_id": "alice",
        "cwd": str(cwd),
        "status": "idle",
    }
    mock_client = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_client

    claw_cli.save_config({"core_base_url": "http://127.0.0.1:9", "api_key": "k", "owner_user_id": "alice"})
    ns = type("NS", (), {"cwd": str(cwd), "owner": ""})()
    rc = claw_cli.cmd_session_new(ns, claw_cli.load_config())
    assert rc == 0
    saved = claw_cli.load_config()
    assert saved.get("default_clawcode_session_id") == "abc-uuid"


@patch("clients.clawcode.cli._client")
def test_cmd_session_show_success(mock_client_cls, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setattr(claw_cli, "config_path", lambda: cfg_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "clawcode_session_id": "s1",
        "owner_user_id": "alice",
        "cwd": "/tmp",
        "status": "idle",
        "last_run_id": "r1",
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_client

    claw_cli.save_config({"core_base_url": "http://127.0.0.1:9", "api_key": "k", "owner_user_id": "alice"})
    ns = type("NS", (), {"session": "s1", "owner": ""})()
    rc = claw_cli.cmd_session_show(ns, claw_cli.load_config())
    assert rc == 0
    mock_client.get.assert_called_once()
    url = mock_client.get.call_args[0][0]
    assert url.endswith("/api/clawcode/sessions/s1")
    assert mock_client.get.call_args[1]["params"]["owner_user_id"] == "alice"


@patch("clients.clawcode.cli._client")
def test_cmd_session_worktree_prints_hint(mock_client_cls, tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.json"
    monkeypatch.setattr(claw_cli, "config_path", lambda: cfg_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "clawcode_session_id": "s1",
        "worktree_hint": "git -C /repo worktree add /wt -b x",
        "usage_hint": "See trace",
    }
    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client_cls.return_value = mock_client

    claw_cli.save_config({"core_base_url": "http://127.0.0.1:9", "api_key": "k", "owner_user_id": "alice"})
    ns = type("NS", (), {"session": "s1", "owner": ""})()
    rc = claw_cli.cmd_session_worktree(ns, claw_cli.load_config())
    assert rc == 0
