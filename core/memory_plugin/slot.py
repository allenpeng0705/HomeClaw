"""
Memory plugin slot: single-slot registration and resolution.

Only one MemoryPlugin can be active per agent at a time. This module
manages the active plugin registration and provides resolution.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from core.memory_plugin.protocol import MemoryPlugin

# Slot state
_active_plugin: Optional[MemoryPlugin] = None
_active_owner: Optional[str] = None


def register_memory_plugin(plugin: MemoryPlugin, *, owner: str = "core") -> bool:
    """
    Register a MemoryPlugin. Replaces any existing active plugin.

    Returns True on success. Only one plugin can be active at a time.
    If a different plugin is already active, it is displaced.
    """
    global _active_plugin, _active_owner

    if _active_plugin is not None and _active_owner != owner:
        logger.info(
            "MemoryPlugin '{}' (owner: '{}') displaced by '{}' (owner: '{}')",
            _active_plugin.plugin_id, _active_owner,
            plugin.plugin_id, owner,
        )

    _active_plugin = plugin
    _active_owner = owner
    logger.info("MemoryPlugin '{}' registered (owner: '{}')", plugin.plugin_id, owner)
    return True


def unregister_memory_plugin(*, owner: str = "core") -> bool:
    """Unregister the active MemoryPlugin. Only the owner can unregister."""
    global _active_plugin, _active_owner

    if _active_plugin is None:
        return False
    if _active_owner != owner:
        logger.warning(
            "Cannot unregister MemoryPlugin: owned by '{}', requested by '{}'",
            _active_owner, owner,
        )
        return False

    logger.info("MemoryPlugin '{}' unregistered", _active_plugin.plugin_id)
    _active_plugin = None
    _active_owner = None
    return True


def get_active_memory_plugin() -> Optional[MemoryPlugin]:
    """Return the currently active MemoryPlugin, or None."""
    return _active_plugin


def get_active_plugin_info() -> Dict[str, Any]:
    """Return metadata about the active plugin."""
    if _active_plugin is None:
        return {"active": False}
    return {
        "active": True,
        "plugin_id": _active_plugin.plugin_id,
        "owner": _active_owner,
    }
