"""
Tests for Portal config backup: system copy, previous backup, restore, revert, save_as_system.
Uses a temp config dir via monkeypatch; does not touch real config.
"""
from pathlib import Path

import pytest


@pytest.fixture
def temp_config_dir(monkeypatch, tmp_path):
    """Point config_backup's get_config_dir to tmp_path (used by _config_dir())."""
    import portal.config_backup as backup_mod
    monkeypatch.setattr(backup_mod, "get_config_dir", lambda: tmp_path)
    return tmp_path


def test_backup_previous_creates_previous_file(temp_config_dir):
    from portal import config_backup
    (temp_config_dir / "core.yml").write_text("name: core\nport: 9000\n")
    ok = config_backup.backup_previous("core")
    assert ok is True
    prev = temp_config_dir / "core.yml.previous"
    assert prev.exists()
    assert prev.read_text() == "name: core\nport: 9000\n"


def test_restore_to_system_copies_system_to_current(temp_config_dir):
    from portal import config_backup
    (temp_config_dir / "system").mkdir()
    (temp_config_dir / "system" / "core.yml").write_text("name: restored\nport: 9000\n")
    (temp_config_dir / "core.yml").write_text("name: current\n")
    ok = config_backup.restore_to_system("core")
    assert ok is True
    assert (temp_config_dir / "core.yml").read_text() == "name: restored\nport: 9000\n"


def test_revert_to_previous_copies_previous_to_current(temp_config_dir):
    from portal import config_backup
    (temp_config_dir / "core.yml.previous").write_text("name: reverted\nport: 8000\n")
    (temp_config_dir / "core.yml").write_text("name: current\n")
    ok = config_backup.revert_to_previous("core")
    assert ok is True
    assert (temp_config_dir / "core.yml").read_text() == "name: reverted\nport: 8000\n"


def test_save_current_as_system_overwrites_system(temp_config_dir):
    from portal import config_backup
    (temp_config_dir / "core.yml").write_text("name: new_system\n")
    ok = config_backup.save_current_as_system("core")
    assert ok is True
    assert (temp_config_dir / "system" / "core.yml").read_text() == "name: new_system\n"


def test_ensure_system_copy_creates_system_from_current(temp_config_dir):
    from portal import config_backup
    (temp_config_dir / "llm.yml").write_text("main_llm: x\n")
    ok = config_backup.ensure_system_copy("llm")
    assert ok is True
    assert (temp_config_dir / "system" / "llm.yml").exists()
    assert (temp_config_dir / "system" / "llm.yml").read_text() == "main_llm: x\n"


def test_prepare_for_update_backs_up_previous(temp_config_dir):
    from portal import config_backup
    (temp_config_dir / "core.yml").write_text("before\n")
    ok = config_backup.prepare_for_update("core")
    assert ok is True
    assert (temp_config_dir / "core.yml.previous").read_text() == "before\n"
    assert (temp_config_dir / "system" / "core.yml").exists()


def test_unknown_name_returns_false():
    from portal import config_backup
    assert config_backup.backup_previous("unknown") is False
    assert config_backup.restore_to_system("unknown") is False
    assert config_backup.revert_to_previous("unknown") is False
    assert config_backup.save_current_as_system("unknown") is False
    assert config_backup.ensure_system_copy("unknown") is False
    assert config_backup.has_system_copy("unknown") is False
    assert config_backup.has_previous_backup("unknown") is False
