"""
ContextEngine: pluggable context management lifecycle.

This module defines the ContextEngine protocol that owns the full context
pipeline for LLM interactions: ingestion, assembly, compaction, and maintenance.

Engines implement ContextEngine; the runtime resolves one per session.

Usage:
    from core.context_engine import (
        ContextEngine, ContextEngineInfo,
        AssembleResult, CompactResult, IngestResult,
        LegacyContextEngine,
    )
"""

from core.context_engine.legacy_engine import LegacyContextEngine
from core.context_engine.registry import (
    register_context_engine,
    unregister_context_engine,
    resolve_context_engine,
    list_engines,
    is_registered,
    clear_registry,
    ensure_context_engines_initialized,
)
from core.context_engine.compact_runtime import (
    generate_compaction_summary,
    generate_llm_compaction_summary,
    create_compaction_system_message,
    rotate_session_id,
    rotate_session,
)

from core.context_engine.protocol import (
    ContextEngine,
    ContextEngineInfo,
    ContextEngineHostCapability,
    ContextEngineOperation,
    ContextEngineHostRequirements,
    ContextEngineProjection,
    ContextProjectionMode,
    ContextEnginePromptCacheInfo,
    ContextEngineRuntimeContext,
    TurnMaintenanceMode,
    PromptAuthority,
    SubagentEndReason,
    AssembleResult,
    CompactResult,
    IngestResult,
    IngestBatchResult,
    BootstrapResult,
    TranscriptRewriteReplacement,
    TranscriptRewriteRequest,
    TranscriptRewriteResult,
    ContextEngineMaintenanceResult,
    SubagentSpawnPreparation,
)

__all__ = [
    "LegacyContextEngine",
    "register_context_engine",
    "unregister_context_engine",
    "resolve_context_engine",
    "list_engines",
    "is_registered",
    "clear_registry",
    "ensure_context_engines_initialized",
    "generate_compaction_summary",
    "generate_llm_compaction_summary",
    "create_compaction_system_message",
    "rotate_session_id",
    "rotate_session",
    "ContextEngine",
    "ContextEngineInfo",
    "ContextEngineHostCapability",
    "ContextEngineOperation",
    "ContextEngineHostRequirements",
    "ContextEngineProjection",
    "ContextProjectionMode",
    "ContextEnginePromptCacheInfo",
    "ContextEngineRuntimeContext",
    "TurnMaintenanceMode",
    "PromptAuthority",
    "SubagentEndReason",
    "AssembleResult",
    "CompactResult",
    "IngestResult",
    "IngestBatchResult",
    "BootstrapResult",
    "TranscriptRewriteReplacement",
    "TranscriptRewriteRequest",
    "TranscriptRewriteResult",
    "ContextEngineMaintenanceResult",
    "SubagentSpawnPreparation",
]
