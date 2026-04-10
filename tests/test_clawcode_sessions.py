"""Tests for Claw-Code session store and trace schema (no live Core)."""

from __future__ import annotations

from types import SimpleNamespace
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from core import clawcode_store
from core.routes import clawcode_api
from tests.workflow_framework.trace_schema import validate_event


@pytest.fixture
def mock_cc_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(clawcode_store, "sessions_base_dir", lambda: tmp_path / "cc_sess")
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"enabled": True, "allowed_roots": []}
        )
        yield tmp_path


def test_create_get_list(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "repo"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    assert sid
    assert rec.get("mode") in ("plan", "agent")
    assert rec["owner_user_id"] == "alice"
    got = clawcode_store.get_session(sid)
    assert got and got["cwd"] == str(cwd.resolve())
    lst = clawcode_store.list_sessions_for_owner("alice")
    assert len(lst) == 1
    assert lst[0]["clawcode_session_id"] == sid


def test_owner_filter(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "r"
    cwd.mkdir()
    clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    assert clawcode_store.list_sessions_for_owner("bob") == []


def test_record_clawcode_turn_finished_updates_touch(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "r2"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    with patch.object(clawcode_store, "touch_session") as mock_touch:
        clawcode_store.record_clawcode_turn_finished(sid, "req-99")
        mock_touch.assert_called_once()
        call_kw = mock_touch.call_args[1]
        assert call_kw.get("status") == "idle"
        assert call_kw.get("last_run_id") == "req-99"


def test_record_clawcode_turn_finished_noop_when_disabled(mock_cc_enabled, tmp_path):
    with patch.object(clawcode_store, "clawcode_feature_enabled", return_value=False):
        with patch.object(clawcode_store, "touch_session") as mock_touch:
            clawcode_store.record_clawcode_turn_finished("any-id", "r1")
            mock_touch.assert_not_called()


def test_record_clawcode_turn_finished_merges_last_usage(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "rusage"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    pr = SimpleNamespace(
        request_metadata={
            "clawcode_session_id": sid,
            "_clawcode_completion_usage": [
                {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            ],
        }
    )
    with patch.object(clawcode_store, "touch_session") as mock_touch:
        clawcode_store.record_clawcode_turn_finished(sid, "req-z", request=pr)
        mock_touch.assert_called_once()
        call_kw = mock_touch.call_args[1]
        lu = call_kw.get("last_usage") or {}
        assert lu.get("prompt_tokens") == 11
        assert lu.get("completion_tokens") == 22
        assert lu.get("total_tokens") == 33
        assert lu.get("rounds") == 2


def test_fallback_clawcode_usage_from_request():
    from base.llm_usage_buffer import fallback_clawcode_usage_from_request

    pr = SimpleNamespace(
        text="hi",
        request_metadata={
            "clawcode_session_id": "sess-1",
            "_clawcode_last_user_text": "a" * 80,
            "_clawcode_last_assistant_text": "b" * 80,
        },
    )
    out = fallback_clawcode_usage_from_request(pr)
    assert out and out.get("estimated") is True
    assert int(out.get("total_tokens") or 0) > 0


def test_record_clawcode_turn_finished_uses_estimate_without_api_usage(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "rest"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    pr = SimpleNamespace(
        request_metadata={
            "clawcode_session_id": sid,
            "_clawcode_last_user_text": "u" * 120,
            "_clawcode_last_assistant_text": "a" * 120,
        }
    )
    with patch.object(clawcode_store, "touch_session") as mock_touch:
        clawcode_store.record_clawcode_turn_finished(sid, "req-est", request=pr)
        call_kw = mock_touch.call_args[1]
        lu = call_kw.get("last_usage") or {}
        assert lu.get("estimated") is True
        assert int(lu.get("total_tokens") or 0) > 0


def test_clawcode_mcp_preset_note_reads_config(mock_cc_enabled, tmp_path):
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"enabled": True, "allowed_roots": [], "mcp_preset_note": "Use server `fs` for files."}
        )
        assert "fs" in clawcode_store.clawcode_mcp_preset_note()


def test_clawcode_mcp_allowlist(mock_cc_enabled, tmp_path):
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={
                "enabled": True,
                "allowed_roots": [],
                "mcp_tool_allowlist": ["myserver/read_file"],
            }
        )
        assert clawcode_store.clawcode_mcp_pair_allowed("myserver", "read_file")
        assert not clawcode_store.clawcode_mcp_pair_allowed("myserver", "delete_file")
        assert not clawcode_store.clawcode_mcp_pair_allowed("other", "delete_file")


def test_rebind_session_cwd(mock_cc_enabled, tmp_path):
    cwd1 = tmp_path / "r1"
    cwd2 = tmp_path / "r2"
    cwd1.mkdir()
    cwd2.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u", cwd=str(cwd1))
    sid = rec["clawcode_session_id"]
    out, err, code = clawcode_store.rebind_session_cwd(sid, "u", str(cwd2))
    assert err is None and code == 200
    assert out and out.get("cwd") == str(cwd2.resolve())


def test_clawcode_tool_preflight_absolute_path(mock_cc_enabled, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u", cwd=str(root))
    sid = rec["clawcode_session_id"]
    from base.tools import ToolContext

    req = SimpleNamespace(request_metadata={"clawcode_session_id": sid})
    ctx = ToolContext(core=MagicMock(), user_id="u", request=req)
    esc = clawcode_store.clawcode_tool_preflight(
        "file_read", {"path": str(other / "x.txt")}, ctx
    )
    assert esc and "escapes" in esc.lower()


def test_clawcode_git_exec_blocked_when_disabled(mock_cc_enabled, tmp_path):
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"enabled": True, "allowed_roots": [], "git_write_allowed": False}
        )
        from base.tools import ToolContext

        req = SimpleNamespace(request_metadata={"clawcode_session_id": "sess-1"})
        ctx = ToolContext(core=MagicMock(), request=req)
        msg = clawcode_store.clawcode_exec_git_block_message("git commit -m x", ctx)
        assert msg and "disabled" in msg.lower()


def test_patch_clawcode_session_metadata(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "patch_sess"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    out, err, code = clawcode_store.patch_clawcode_session_metadata(
        sid, "alice", {"git_remote_hint": "origin main"}
    )
    assert err is None and code == 200
    assert out and out.get("git_remote_hint") == "origin main"
    _, err2, code2 = clawcode_store.patch_clawcode_session_metadata(sid, "bob", {"git_remote_hint": "x"})
    assert code2 == 403
    _, err3, code3 = clawcode_store.patch_clawcode_session_metadata(sid, "alice", {})
    assert code3 == 400


def test_patch_clawcode_session_task_plan_and_resume(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "mile_b"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    assert isinstance(rec.get("task_plan"), list)
    out, err, code = clawcode_store.patch_clawcode_session_metadata(
        sid,
        "alice",
        {
            "task_plan": [{"id": "1", "title": "Step one", "status": "pending"}],
            "checkpoint": "after tests",
            "resume_hint": "fix failing test",
            "last_run_error": "timeout",
        },
    )
    assert err is None and code == 200
    assert out and out.get("checkpoint") == "after tests"
    assert out.get("resume_hint") == "fix failing test"
    assert out.get("last_run_error") == "timeout"
    assert isinstance(out.get("task_plan"), list) and out["task_plan"][0].get("id") == "1"


def test_api_session_patch_ok_and_forbidden(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "api_patch"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    handler = clawcode_api.get_api_clawcode_session_patch_handler(MagicMock())

    async def _run():
        body = clawcode_api.ClawcodeSessionPatchBody(git_remote_hint="my remote")
        r_ok = await handler(sid, body, owner_user_id="alice")
        assert r_ok.status_code == 200
        d = json.loads(r_ok.body.decode("utf-8"))
        assert d.get("git_remote_hint") == "my remote"
        body2 = clawcode_api.ClawcodeSessionPatchBody(main_llm_ref="cloud_models/foo")
        r403 = await handler(sid, body2, owner_user_id="bob")
        assert r403.status_code == 403

    asyncio.run(_run())


def test_api_session_detail_ok_and_forbidden(mock_cc_enabled, tmp_path):
    cwd = tmp_path / "api_sess"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id="alice", cwd=str(cwd))
    sid = rec["clawcode_session_id"]
    handler = clawcode_api.get_api_clawcode_session_detail_handler(MagicMock())

    async def _run():
        r_ok = await handler(sid, owner_user_id="alice")
        assert r_ok.status_code == 200
        d = json.loads(r_ok.body.decode("utf-8"))
        assert d.get("clawcode_session_id") == sid
        assert "worktree_hint" in d
        assert "usage_hint" in d
        assert isinstance(d.get("usage_hint"), str)
        r403 = await handler(sid, owner_user_id="bob")
        assert r403.status_code == 403
        r404 = await handler("not-a-real-uuid", owner_user_id="alice")
        assert r404.status_code == 404

    asyncio.run(_run())


def test_allowed_roots_rejects(mock_cc_enabled, tmp_path):
    allowed = tmp_path / "allowed"
    other = tmp_path / "other"
    allowed.mkdir()
    other.mkdir()
    proj = other / "proj"
    proj.mkdir()
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"enabled": True, "allowed_roots": [str(allowed.resolve())]}
        )
        with pytest.raises(PermissionError):
            clawcode_store.create_session(owner_user_id="u", cwd=str(proj))


def test_trace_schema_clawcode_events():
    base = {
        "schema_version": "1.0",
        "run_id": "r1",
        "turn_id": "t1",
        "timestamp": 1.0,
        "sequence": 1,
        "event_type": "clawcode_session_started",
        "component": "clawcode",
        "summary": "x",
        "details": {},
    }
    assert validate_event(base).ok
    base["event_type"] = "clawcode_session_patched"
    assert validate_event(base).ok
    base["event_type"] = "clawcode_turn_started"
    assert validate_event(base).ok
    base["event_type"] = "clawcode_approval_requested"
    assert validate_event(base).ok
    base["event_type"] = "clawcode_approval_resolved"
    assert validate_event(base).ok
