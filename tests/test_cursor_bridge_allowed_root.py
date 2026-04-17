"""CURSOR_BRIDGE_ALLOWED_ROOT / cursor_bridge_allowed_root: bridge path sandboxing."""

import pytest


def test_resolve_path_relative_under_allowed_root(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "proj").mkdir()
    monkeypatch.setenv("CURSOR_BRIDGE_ALLOWED_ROOT", str(root))
    from external_plugins.cursor_bridge.server import _allowed_root_resolved, _resolve_path

    assert _allowed_root_resolved() == root.resolve()
    assert _resolve_path("proj") == str((root / "proj").resolve())


def test_resolve_path_absolute_under_allowed_root(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    sub = root / "a"
    sub.mkdir()
    monkeypatch.setenv("CURSOR_BRIDGE_ALLOWED_ROOT", str(root))
    from external_plugins.cursor_bridge.server import _resolve_path

    assert _resolve_path(str(sub)) == str(sub.resolve())


def test_resolve_path_rejects_outside_allowed_root(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "other"
    outside.mkdir()
    monkeypatch.setenv("CURSOR_BRIDGE_ALLOWED_ROOT", str(root))
    from external_plugins.cursor_bridge.server import _resolve_path

    with pytest.raises(ValueError, match="CURSOR_BRIDGE_ALLOWED_ROOT"):
        _resolve_path(str(outside))


def test_resolve_path_rejects_traversal(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("CURSOR_BRIDGE_ALLOWED_ROOT", str(root))
    from external_plugins.cursor_bridge.server import _resolve_path

    with pytest.raises(ValueError, match="CURSOR_BRIDGE_ALLOWED_ROOT"):
        _resolve_path("../outside")


def test_set_active_cwd_ignored_outside_root(monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "evil"
    outside.mkdir()
    monkeypatch.setenv("CURSOR_BRIDGE_ALLOWED_ROOT", str(root))
    from external_plugins.cursor_bridge import server as srv

    srv._set_active_cwd(str(outside), backend="cursor")
    assert srv._get_active_cwd("cursor") is None
