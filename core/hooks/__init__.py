"""
Hooks: lifecycle hook system for agent operations.

Plugins and core modules can register callbacks that fire at key
points in the agent lifecycle: after turns, around compaction,
on memory flushes, and on health checks.
"""

from core.hooks.lifecycle import (
    HookPoint,
    HookContext,
    HookCallback,
    register_hook,
    unregister_hooks,
    fire_hook,
    clear_hooks,
)

__all__ = [
    "HookPoint",
    "HookContext",
    "HookCallback",
    "register_hook",
    "unregister_hooks",
    "fire_hook",
    "clear_hooks",
]
