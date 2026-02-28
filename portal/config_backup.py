"""
System copy and previous backup for Portal config files.
- System copy: config/system/<name>.yml — original; never changed except by system upgrade.
- Previous backup: config/<name>.yml.previous — state before last write; one level only.
User can restore to system or revert to previous. All functions never raise.
"""
import logging
import shutil
from pathlib import Path
from portal.config import get_config_dir

_log = logging.getLogger(__name__)

# Config file names (without .yml) that support system/previous.
CONFIG_NAMES = ("core", "llm", "memory_kb", "skills_and_plugins", "user", "friend_presets")


def _config_dir() -> Path:
    return Path(get_config_dir())


def get_config_path(name: str) -> Path:
    """Path to current config file, e.g. config/core.yml."""
    return _config_dir() / f"{name}.yml"


def get_system_path(name: str) -> Path:
    """Path to system copy, e.g. config/system/core.yml."""
    return _config_dir() / "system" / f"{name}.yml"


def get_previous_path(name: str) -> Path:
    """Path to previous backup, e.g. config/core.yml.previous."""
    return _config_dir() / f"{name}.yml.previous"


def ensure_system_copy(name: str) -> bool:
    """If system copy does not exist and current config exists, copy current → system (one-time bootstrap).
    Creates config/system/ if needed. Returns True if system copy exists after call (or was created). Never raises."""
    if name not in CONFIG_NAMES:
        return False
    current = get_config_path(name)
    system = get_system_path(name)
    try:
        if system.exists():
            return True
        if not current.exists():
            return False
        system.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, system)
        _log.info("config_backup: created system copy for %s", name)
        return True
    except Exception as e:
        _log.warning("ensure_system_copy %s: %s", name, e)
        return False


def backup_previous(name: str) -> bool:
    """Copy current config to .previous (overwrite). Call before applying a PATCH.
    Returns True if copy succeeded. Never raises."""
    if name not in CONFIG_NAMES:
        return False
    current = get_config_path(name)
    previous = get_previous_path(name)
    try:
        if not current.exists():
            return False
        shutil.copy2(current, previous)
        return True
    except Exception as e:
        _log.warning("backup_previous %s: %s", name, e)
        return False


def restore_to_system(name: str) -> bool:
    """Copy system copy → current config. Returns True if copy succeeded. Never raises."""
    if name not in CONFIG_NAMES:
        return False
    system = get_system_path(name)
    current = get_config_path(name)
    try:
        if not system.exists():
            _log.warning("restore_to_system %s: system copy missing", name)
            return False
        shutil.copy2(system, current)
        _log.info("config_backup: restored %s from system", name)
        return True
    except Exception as e:
        _log.warning("restore_to_system %s: %s", name, e)
        return False


def revert_to_previous(name: str) -> bool:
    """Copy previous backup → current config. Returns True if copy succeeded. Never raises."""
    if name not in CONFIG_NAMES:
        return False
    previous = get_previous_path(name)
    current = get_config_path(name)
    try:
        if not previous.exists():
            _log.warning("revert_to_previous %s: previous backup missing", name)
            return False
        shutil.copy2(previous, current)
        _log.info("config_backup: reverted %s from previous", name)
        return True
    except Exception as e:
        _log.warning("revert_to_previous %s: %s", name, e)
        return False


def save_current_as_system(name: str) -> bool:
    """Copy current config → system copy (system upgrade). Overwrites system copy. Never raises."""
    if name not in CONFIG_NAMES:
        return False
    current = get_config_path(name)
    system = get_system_path(name)
    try:
        if not current.exists():
            return False
        system.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, system)
        _log.info("config_backup: saved current as system for %s", name)
        return True
    except Exception as e:
        _log.warning("save_current_as_system %s: %s", name, e)
        return False


def has_system_copy(name: str) -> bool:
    """True if system copy exists. Never raises."""
    if name not in CONFIG_NAMES:
        return False
    try:
        return get_system_path(name).exists()
    except Exception:
        return False


def has_previous_backup(name: str) -> bool:
    """True if previous backup exists. Never raises."""
    if name not in CONFIG_NAMES:
        return False
    try:
        return get_previous_path(name).exists()
    except Exception:
        return False


def prepare_for_update(name: str) -> bool:
    """Call before applying a PATCH: ensure system copy exists (bootstrap if needed), then backup current to .previous.
    Returns True if backup_previous succeeded (so we have a previous to revert to). Never raises."""
    ensure_system_copy(name)
    return backup_previous(name)
