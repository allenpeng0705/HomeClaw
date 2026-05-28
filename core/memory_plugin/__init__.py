"""
MemoryPlugin: single-slot pluggable memory backend system.

This module defines the MemoryPlugin protocol (ABC) that every memory
backend must implement, plus a single-slot registration system and an
adapter for HomeClaw's existing CompositeMemory.

Usage:
    from core.memory_plugin import (
        MemoryPlugin, MemorySearchResult, MemoryGetResult,
        register_memory_plugin, get_active_memory_plugin,
        CompositeMemoryPlugin,
    )
"""

from core.memory_plugin.protocol import (
    MemoryPlugin,
    MemorySearchResult,
    MemoryGetResult,
    MemoryFlushPlan,
    MemoryFlushResult,
    MemoryHealthStatus,
)
from core.memory_plugin.slot import (
    register_memory_plugin,
    unregister_memory_plugin,
    get_active_memory_plugin,
    get_active_plugin_info,
)
from core.memory_plugin.composite_adapter import CompositeMemoryPlugin
from core.memory_plugin.cognee_adapter import CogneeMemoryPlugin
from core.memory_plugin.memos_adapter import MemosMemoryPlugin

__all__ = [
    "MemoryPlugin",
    "MemorySearchResult",
    "MemoryGetResult",
    "MemoryFlushPlan",
    "MemoryFlushResult",
    "MemoryHealthStatus",
    "register_memory_plugin",
    "unregister_memory_plugin",
    "get_active_memory_plugin",
    "get_active_plugin_info",
    "CompositeMemoryPlugin",
    "CogneeMemoryPlugin",
    "MemosMemoryPlugin",
]
