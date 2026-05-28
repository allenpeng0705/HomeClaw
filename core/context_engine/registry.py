"""
ContextEngine registry: factory-based engine registration and resolution.

Inspired by OpenClaw's context-engine/registry.ts. Manages named engine slots
with ownership tracking. Plugins register engines; the runtime resolves the
active engine per slot.

Default slot: "legacy" → LegacyContextEngine (always available as fallback).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from loguru import logger


# ── types ──────────────────────────────────────────────────────────────────

ContextEngineFactory = Callable[..., Any]  # (core) → ContextEngine


@dataclass
class _EngineEntry:
    factory: ContextEngineFactory
    owner: str  # plugin id or "core"
    info: Optional[Dict[str, Any]] = None


# ── registry state ─────────────────────────────────────────────────────────

_registry: Dict[str, _EngineEntry] = {}
_initialized: bool = False


# ── public API ─────────────────────────────────────────────────────────────


def register_context_engine(
    engine_id: str,
    factory: ContextEngineFactory,
    *,
    owner: str = "core",
    allow_same_owner_refresh: bool = False,
) -> bool:
    """
    Register a ContextEngine factory under engine_id.

    Returns True on success, False if already registered by a different owner.
    If allow_same_owner_refresh is True, an existing registration by the same
    owner is replaced silently.
    """
    existing = _registry.get(engine_id)
    if existing is not None:
        if existing.owner == owner and allow_same_owner_refresh:
            _registry[engine_id] = _EngineEntry(factory=factory, owner=owner)
            logger.info("ContextEngine '{}' refreshed by owner '{}'", engine_id, owner)
            return True
        logger.warning(
            "ContextEngine '{}' already registered by '{}' (requested by '{}')",
            engine_id, existing.owner, owner,
        )
        return False

    _registry[engine_id] = _EngineEntry(factory=factory, owner=owner)
    logger.info("ContextEngine '{}' registered by '{}'", engine_id, owner)
    return True


def unregister_context_engine(engine_id: str, *, owner: str = "core") -> bool:
    """Unregister an engine. Only the original owner can unregister."""
    existing = _registry.get(engine_id)
    if existing is None:
        return False
    if existing.owner != owner:
        logger.warning(
            "Cannot unregister '{}': owned by '{}', requested by '{}'",
            engine_id, existing.owner, owner,
        )
        return False
    del _registry[engine_id]
    logger.info("ContextEngine '{}' unregistered by '{}'", engine_id, owner)
    return True


def resolve_context_engine(
    engine_id: str = "legacy",
    *,
    core: Any = None,
    agent_id: Optional[str] = None,
) -> Optional[Any]:
    """
    Resolve and instantiate a ContextEngine by id.

    When agent_id is provided, checks for a per-agent override first:
      context_engine.{agent_id} config key → engine_id override.
    Falls back to the global engine_id parameter.

    Returns None if no factory is registered for the resolved id.
    """
    # Per-agent override via config
    if agent_id and core is not None:
        try:
            from base.util import Util
            meta = Util().get_core_metadata()
            agent_engines = getattr(meta, "context_engine", None)
            if isinstance(agent_engines, dict):
                override = agent_engines.get(agent_id) or agent_engines.get("default")
                if override and isinstance(override, str) and override.strip():
                    engine_id = override.strip()
        except Exception:
            pass

    entry = _registry.get(engine_id)
    if entry is None:
        logger.debug("ContextEngine '{}' not found in registry", engine_id)
        return None

    try:
        engine = entry.factory(core)
        logger.debug("ContextEngine '{}' resolved (owner: '{}')", engine_id, entry.owner)
        return engine
    except Exception as e:
        logger.error("ContextEngine '{}' factory failed: {}", engine_id, e)
        return None


def list_engines() -> Dict[str, str]:
    """Return {engine_id: owner} for all registered engines."""
    return {eid: entry.owner for eid, entry in _registry.items()}


def is_registered(engine_id: str) -> bool:
    """Check if an engine id is registered."""
    return engine_id in _registry


def clear_registry() -> None:
    """Remove all registered engines and reset initialization flag. For testing only."""
    global _initialized
    _registry.clear()
    _initialized = False


# ── initialization ─────────────────────────────────────────────────────────


def ensure_context_engines_initialized() -> None:
    """
    Register built-in engines exactly once.

    The LegacyContextEngine is always registered as a safe fallback so
    resolve_context_engine() works without manual setup.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    # Legacy engine — always available fallback
    from core.context_engine.legacy_engine import LegacyContextEngine

    register_context_engine(
        "legacy",
        lambda core: LegacyContextEngine(core),
        owner="core",
    )
