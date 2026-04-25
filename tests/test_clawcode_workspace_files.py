"""Claw-Code workspace file listing under session cwd (allowed_roots respected via session)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import clawcode_store


@pytest.fixture
def mock_cc_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(clawcode_store, "sessions_base_dir", lambda: tmp_path / "cc_sess")
    with patch("core.clawcode_store.Util") as mock_u:
        mock_u.return_value.get_core_metadata.return_value = SimpleNamespace(
            clawcode={"enabled": True, "allowed_roots": []}
        )
        yield tmp_path


def test_list_workspace_files_root(mock_cc_enabled, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("x", encoding="utf-8")
    sub = root / "pkg"
    sub.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u1", cwd=str(root))
    sid = rec["clawcode_session_id"]
    entries, err, code = clawcode_store.list_workspace_files(sid, "u1", "")
    assert err is None and code == 200
    names = sorted(e["name"] for e in (entries or []))
    assert "a.py" in names and "pkg" in names
    types = {e["name"]: e["type"] for e in (entries or [])}
    assert types["pkg"] == "directory"
    assert types["a.py"] == "file"


def test_list_workspace_files_nested(mock_cc_enabled, tmp_path):
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "b.txt").write_text("y", encoding="utf-8")
    rec = clawcode_store.create_session(owner_user_id="u1", cwd=str(root))
    sid = rec["clawcode_session_id"]
    entries, err, code = clawcode_store.list_workspace_files(sid, "u1", "pkg")
    assert err is None and code == 200
    assert len(entries) == 1
    assert entries[0]["name"] == "b.txt"


def test_list_workspace_files_rejects_escape(mock_cc_enabled, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u1", cwd=str(root))
    sid = rec["clawcode_session_id"]
    entries, err, code = clawcode_store.list_workspace_files(sid, "u1", "../..")
    assert entries is None
    assert code == 400


def test_list_workspace_files_wrong_owner(mock_cc_enabled, tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u1", cwd=str(root))
    sid = rec["clawcode_session_id"]
    entries, err, code = clawcode_store.list_workspace_files(sid, "u2", "")
    assert entries is None and code == 403


def test_list_workspace_files_nonexistent_subdir(mock_cc_enabled, tmp_path):
    """Non-existent subdirectory should return empty list (not an error)."""
    root = tmp_path / "proj"
    root.mkdir()
    rec = clawcode_store.create_session(owner_user_id="u1", cwd=str(root))
    sid = rec["clawcode_session_id"]
    entries, err, code = clawcode_store.list_workspace_files(sid, "u1", "nonexistent_dir")
    assert entries == [] and code == 200


def test_list_workspace_files_empty_directory(mock_cc_enabled, tmp_path):
    """Empty directory should return empty list (not an error)."""
    root = tmp_path / "proj"
    (root / "empty_dir").mkdir()
    rec = clawcode_store.create_session(owner_user_id="u1", cwd=str(root))
    sid = rec["clawcode_session_id"]
    entries, err, code = clawcode_store.list_workspace_files(sid, "u1", "empty_dir")
    assert entries == [] and code == 200
