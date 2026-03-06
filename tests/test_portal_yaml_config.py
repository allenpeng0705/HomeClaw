"""
Tests for Portal YAML layer (Step 2): load_yml_preserving, update_yml_preserving, whitelist, comment preservation.
Uses temp files; does not modify real config.
"""
import tempfile
from pathlib import Path

import pytest

from portal.yaml_config import (
    load_yml_preserving,
    update_yml_preserving,
    WHITELIST_LLM,
    WHITELIST_FRIEND_PRESETS,
)


def test_load_yml_preserving_missing_file_returns_none():
    assert load_yml_preserving("/nonexistent/path/file.yml") is None


def test_load_yml_preserving_returns_dict():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("# comment\nkey: value\n")
        path = f.name
    try:
        data = load_yml_preserving(path)
        assert data is not None
        assert isinstance(data, dict)
        assert data.get("key") == "value"
    finally:
        Path(path).unlink(missing_ok=True)


def test_update_yml_preserving_creates_file_if_missing():
    with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
        path = f.name
    Path(path).unlink(missing_ok=True)
    assert not Path(path).exists()
    ok = update_yml_preserving(path, {"a": 1}, whitelist=None)
    assert ok is True
    try:
        data = load_yml_preserving(path)
        assert data == {"a": 1}
    finally:
        Path(path).unlink(missing_ok=True)


def test_update_yml_preserving_merges_and_preserves_comment():
    content = "# Portal test comment line\nmain_llm: old_value\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(content)
        path = f.name
    try:
        ok = update_yml_preserving(path, {"main_llm": "local_models/new_model"}, whitelist=WHITELIST_LLM)
        assert ok is True
        data = load_yml_preserving(path)
        assert data is not None
        assert data.get("main_llm") == "local_models/new_model"
        raw = Path(path).read_text(encoding="utf-8")
        assert "Portal test comment line" in raw or "comment" in raw
    finally:
        Path(path).unlink(missing_ok=True)


def test_update_yml_preserving_whitelist_ignores_unknown_keys():
    content = "presets:\n  x: y\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(content)
        path = f.name
    try:
        # unknown_key not in WHITELIST_FRIEND_PRESETS; only presets is
        ok = update_yml_preserving(
            path,
            {"presets": {"reminder": {"tools_preset": "reminder"}}, "unknown_key": "ignored"},
            whitelist=WHITELIST_FRIEND_PRESETS,
        )
        assert ok is True
        data = load_yml_preserving(path)
        assert data is not None
        assert "presets" in data
        assert "unknown_key" not in data
    finally:
        Path(path).unlink(missing_ok=True)


def test_update_yml_preserving_empty_updates_returns_true():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write("k: v\n")
        path = f.name
    try:
        assert update_yml_preserving(path, {}) is True
        assert update_yml_preserving(path, {"only_unknown": 1}, whitelist=frozenset({"k"})) is True
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_real_config_if_present_never_crashes():
    """Load real config files if they exist; must not raise. Ensures stability."""
    root = Path(__file__).resolve().parent.parent
    for name in ("llm.yml", "memory_kb.yml", "skills_and_plugins.yml", "friend_presets.yml"):
        path = root / "config" / name
        if not path.exists():
            continue
        data = load_yml_preserving(str(path))
        assert data is None or isinstance(data, dict)
