"""
Lifecycle hook system for HomeClaw agents.

Provides hook points that plugins can register for. Hooks fire at key
points in the agent lifecycle: before/after compaction, after each turn,
on memory flush, and on health check events.

Inspired by OpenClaw's plugin hook architecture (src/plugins/hook-types.ts).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


# ── Hook types ──────────────────────────────────────────────────────────────


class HookPoint(str, Enum):
    """Named hook points in the agent lifecycle."""
    AFTER_TURN = "after_turn"
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"
    BEFORE_MEMORY_FLUSH = "before_memory_flush"
    AFTER_MEMORY_FLUSH = "after_memory_flush"
    ON_HEALTH_CHECK = "on_health_check"


@dataclass
class HookContext:
    """Context passed to hook callbacks."""
    hook: HookPoint
    session_id: Optional[str] = None
    session_file: Optional[str] = None
    turn_count: int = 0
    token_count: int = 0
    compaction_result: Optional[Any] = None
    memory_flush_result: Optional[Any] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# ── Hook callback type ──────────────────────────────────────────────────────

HookCallback = Callable[[HookContext], None]


# ── Registry ────────────────────────────────────────────────────────────────


_registry: Dict[HookPoint, List[tuple[str, HookCallback]]] = {
    hp: [] for hp in HookPoint
}


def register_hook(hook: HookPoint, callback: HookCallback, *, owner: str = "core") -> None:
    """Register a callback for a lifecycle hook."""
    _registry[hook].append((owner, callback))
    logger.debug("Hook '{}' registered by '{}'", hook.value, owner)


def unregister_hooks(*, owner: str = "core") -> int:
    """Remove all hooks registered by an owner. Returns count removed."""
    removed = 0
    for hp in HookPoint:
        before = len(_registry[hp])
        _registry[hp] = [(o, cb) for o, cb in _registry[hp] if o != owner]
        removed += before - len(_registry[hp])
    return removed


def fire_hook(hook: HookPoint, ctx: Optional[HookContext] = None) -> None:
    """Fire all registered callbacks for a hook point."""
    if ctx is None:
        ctx = HookContext(hook=hook)
    for owner, callback in list(_registry[hook]):  # iterate copy for safety
        try:
            callback(ctx)
        except Exception as e:
            logger.warning("Hook '{}' (owner='{}') failed: {}", hook.value, owner, e)


def clear_hooks() -> None:
    """Remove all hooks. For testing only."""
    for hp in HookPoint:
        _registry[hp].clear()
