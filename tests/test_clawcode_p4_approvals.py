"""P4: Claw-Code approval gate (file store + resolve)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from base.tools import ToolContext
from core import clawcode_approvals, clawcode_store


@pytest.fixture
def mock_cc_p4(tmp_path, monkeypatch):
    monkeypatch.setattr(clawcode_store, "sessions_base_dir", lambda: tmp_path / "cc_sess")
    monkeypatch.setattr(clawcode_approvals, "approvals_base_dir", lambda: tmp_path / "cc_appr")
    with patch("core.clawcode_store.Util") as mock_u, patch("core.clawcode_approvals.Util") as mock_u2:
        meta = SimpleNamespace(
            clawcode={
                "enabled": True,
                "allowed_roots": [],
                "approval_tools": ["file_write"],
                "approval_ttl_seconds": 3600,
            },
            tool_policy={},
            tool_timeout_seconds=120,
        )
        mock_u.return_value.get_core_metadata.return_value = meta
        mock_u.return_value.root_path.return_value = str(tmp_path)
        mock_u2.return_value.get_core_metadata.return_value = meta
        mock_u2.return_value.root_path.return_value = str(tmp_path)
        yield tmp_path


def _make_session(tmp_path, owner: str) -> str:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    rec = clawcode_store.create_session(owner_user_id=owner, cwd=str(cwd))
    return str(rec["clawcode_session_id"])


def test_maybe_block_skips_without_session(mock_cc_p4, tmp_path):
    ctx = ToolContext(
        core=None,
        user_id="alice",
        friend_id="HomeClaw",
        session_id="s",
        run_id="r",
        request=SimpleNamespace(request_metadata={}),
    )
    assert clawcode_approvals.maybe_block_clawcode_tool("file_write", {"path": "x"}, ctx) is None


def test_maybe_block_skips_when_tool_not_listed(mock_cc_p4, tmp_path):
    sid = _make_session(tmp_path, "alice")
    ctx = ToolContext(
        core=None,
        user_id="alice",
        friend_id="HomeClaw",
        session_id="s",
        run_id="r",
        request=SimpleNamespace(request_metadata={"clawcode_session_id": sid}),
    )
    assert clawcode_approvals.maybe_block_clawcode_tool("folder_list", {"path": "."}, ctx) is None


def test_maybe_block_creates_pending(mock_cc_p4, tmp_path):
    sid = _make_session(tmp_path, "alice")
    ctx = ToolContext(
        core=None,
        user_id="alice",
        friend_id="HomeClaw",
        session_id="chat-sess",
        run_id="run-1",
        request=SimpleNamespace(request_metadata={"clawcode_session_id": sid}),
    )
    msg = clawcode_approvals.maybe_block_clawcode_tool("file_write", {"path": "a.txt", "content": "hi"}, ctx)
    assert msg and "approval_id:" in msg
    pending = clawcode_approvals.list_pending_for_owner("alice")
    assert len(pending) == 1
    assert pending[0]["tool_name"] == "file_write"
    assert pending[0]["arguments"].get("path") == "a.txt"


def test_maybe_block_owner_mismatch(mock_cc_p4, tmp_path):
    sid = _make_session(tmp_path, "alice")
    ctx = ToolContext(
        core=None,
        user_id="bob",
        friend_id="HomeClaw",
        session_id="s",
        run_id="r",
        request=SimpleNamespace(request_metadata={"clawcode_session_id": sid}),
    )
    assert clawcode_approvals.maybe_block_clawcode_tool("file_write", {}, ctx) is None


def test_resolve_reject(mock_cc_p4, tmp_path):
    sid = _make_session(tmp_path, "alice")
    ctx = ToolContext(
        core=None,
        user_id="alice",
        friend_id="HomeClaw",
        session_id="s",
        run_id="r",
        request=SimpleNamespace(request_metadata={"clawcode_session_id": sid}),
    )
    clawcode_approvals.maybe_block_clawcode_tool("file_write", {"path": "x"}, ctx)
    aid = clawcode_approvals.list_pending_for_owner("alice")[0]["approval_id"]
    ok, msg, res = asyncio.run(
        clawcode_approvals.resolve_approval(
            SimpleNamespace(), approval_id=aid, owner_user_id="alice", decision="reject"
        )
    )
    assert ok and msg == "rejected" and res is None
    rec = clawcode_approvals.get_approval(aid)
    assert rec and rec["status"] == "rejected"


def test_resolve_approve_executes(mock_cc_p4, tmp_path):
    sid = _make_session(tmp_path, "alice")
    ctx = ToolContext(
        core=None,
        user_id="alice",
        friend_id="HomeClaw",
        session_id="s",
        run_id="r",
        request=SimpleNamespace(request_metadata={"clawcode_session_id": sid}),
    )
    clawcode_approvals.maybe_block_clawcode_tool("file_write", {"path": "x"}, ctx)
    aid = clawcode_approvals.list_pending_for_owner("alice")[0]["approval_id"]

    class FakeReg:
        async def execute_async(self, name, args, context):
            assert name == "file_write"
            assert isinstance(args, dict)
            return "wrote"

    with patch("base.tools.get_tool_registry", return_value=FakeReg()):
        ok, msg, res = asyncio.run(
            clawcode_approvals.resolve_approval(
                SimpleNamespace(), approval_id=aid, owner_user_id="alice", decision="approve"
            )
        )
    assert ok and msg == "executed" and res == "wrote"
    rec = clawcode_approvals.get_approval(aid)
    assert rec and rec["status"] == "executed"
