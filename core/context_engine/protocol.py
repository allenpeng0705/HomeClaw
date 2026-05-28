"""
ContextEngine protocol: pluggable context management lifecycle.

Inspired by OpenClaw's ContextEngine interface (src/context-engine/types.ts).
Defines the ABC that owns the full context pipeline: ingestion, assembly,
compaction, and maintenance.

Engines implement this protocol; the runtime resolves one engine per session.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# ── Enums ────────────────────────────────────────────────────────────────


class ContextEngineHostCapability(str, Enum):
    """Capabilities a host must support for certain engine operations."""
    BOOTSTRAP = "bootstrap"
    ASSEMBLE_BEFORE_PROMPT = "assemble-before-prompt"
    AFTER_TURN = "after-turn"
    MAINTAIN = "maintain"
    COMPACT = "compact"
    RUNTIME_LLM_COMPLETE = "runtime-llm-complete"
    THREAD_BOOTSTRAP_PROJECTION = "thread-bootstrap-projection"


class ContextEngineOperation(str, Enum):
    AGENT_RUN = "agent-run"
    MANUAL_COMPACT = "manual-compact"
    SUBAGENT_SPAWN = "subagent-spawn"


class ContextProjectionMode(str, Enum):
    """How assembled context should be projected into the backend runtime."""
    PER_TURN = "per_turn"
    THREAD_BOOTSTRAP = "thread_bootstrap"


class PromptAuthority(str, Enum):
    """
    Controls which token estimate the runner treats as authoritative for
    preemptive overflow prechecks.
    """
    ASSEMBLED = "assembled"
    PREASSEMBLY_MAY_OVERFLOW = "preassembly_may_overflow"


class SubagentEndReason(str, Enum):
    DELETED = "deleted"
    COMPLETED = "completed"
    SWEPT = "swept"
    RELEASED = "released"


class TurnMaintenanceMode(str, Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


# ── Dataclasses ───────────────────────────────────────────────────────────


@dataclass
class ContextEngineProjection:
    """Optional projection lifecycle for hosts with persistent backend threads."""
    mode: ContextProjectionMode = ContextProjectionMode.PER_TURN
    epoch: Optional[str] = None
    fingerprint: Optional[str] = None


@dataclass
class ContextEnginePromptCacheInfo:
    """Prompt-cache telemetry for cache-aware engines."""
    retention: Optional[str] = None
    last_call_usage: Optional[Dict[str, int]] = None
    observation_broken: bool = False
    previous_cache_read: Optional[int] = None
    cache_read: Optional[int] = None
    last_cache_touch_at: Optional[float] = None
    expires_at: Optional[float] = None


@dataclass
class ContextEngineHostRequirements:
    """Host capability requirements for an operation."""
    required_capabilities: List[ContextEngineHostCapability] = field(default_factory=list)
    unsupported_message: Optional[str] = None


@dataclass
class ContextEngineInfo:
    """Engine identifier and metadata."""
    id: str
    name: str
    version: Optional[str] = None
    owns_compaction: bool = False
    turn_maintenance_mode: TurnMaintenanceMode = TurnMaintenanceMode.FOREGROUND
    host_requirements: Dict[ContextEngineOperation, ContextEngineHostRequirements] = field(default_factory=dict)


@dataclass
class AssembleResult:
    """Result of context assembly."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    estimated_tokens: int = 0
    prompt_authority: PromptAuthority = PromptAuthority.ASSEMBLED
    system_prompt_addition: Optional[str] = None
    context_projection: Optional[ContextEngineProjection] = None


@dataclass
class CompactResult:
    """Result of context compaction."""
    ok: bool = False
    compacted: bool = False
    reason: Optional[str] = None
    summary: Optional[str] = None
    first_kept_entry_id: Optional[str] = None
    tokens_before: int = 0
    tokens_after: Optional[int] = None
    details: Optional[Any] = None
    session_id: Optional[str] = None
    session_file: Optional[str] = None


@dataclass
class IngestResult:
    """Result of ingesting a single message."""
    ingested: bool = False


@dataclass
class IngestBatchResult:
    """Result of ingesting a batch of messages."""
    ingested_count: int = 0


@dataclass
class BootstrapResult:
    """Result of engine bootstrap for a session."""
    bootstrapped: bool = False
    imported_messages: Optional[int] = None
    reason: Optional[str] = None


@dataclass
class TranscriptRewriteReplacement:
    """A single transcript entry replacement."""
    entry_id: str
    message: Dict[str, Any]  # role + content dict


@dataclass
class TranscriptRewriteRequest:
    """Request to rewrite transcript entries on the active branch."""
    replacements: List[TranscriptRewriteReplacement] = field(default_factory=list)
    allowed_rewrite_suffix_entry_ids: Optional[List[str]] = None


@dataclass
class TranscriptRewriteResult:
    """Result of transcript rewrite."""
    changed: bool = False
    bytes_freed: int = 0
    rewritten_entries: int = 0
    reason: Optional[str] = None


@dataclass
class ContextEngineMaintenanceResult:
    """Result of transcript maintenance."""
    changed: bool = False
    bytes_freed: int = 0
    rewritten_entries: int = 0
    reason: Optional[str] = None


@dataclass
class SubagentSpawnPreparation:
    """Preparation result for subagent spawn."""
    rollback: Optional[callable] = None


@dataclass
class ContextEngineRuntimeContext:
    """
    Runtime-owned context passed to engine methods.
    Engines use this to access caller state without tight coupling.
    """
    # Prompt-cache telemetry
    prompt_cache: Optional[ContextEnginePromptCacheInfo] = None

    # Token budget for the active model call
    token_budget: Optional[int] = None

    # Best-effort current token estimate for this turn
    current_token_count: Optional[int] = None

    # True when the host has opted this maintenance into deferred compaction
    allow_deferred_compaction_execution: bool = False

    # Extensible: arbitrary additional context
    extra: Dict[str, Any] = field(default_factory=dict)


# ── ContextEngine ABC ─────────────────────────────────────────────────────


class ContextEngine(ABC):
    """
    Pluggable protocol for context management.

    Required methods: ingest, assemble, compact
    Optional methods: bootstrap, maintain, ingestBatch, afterTurn,
                       prepareSubagentSpawn, onSubagentEnded, dispose

    The runtime resolves one engine per session and calls methods in
    the lifecycle order: bootstrap → maintain → ingest → assemble → compact → afterTurn.
    """

    @property
    @abstractmethod
    def info(self) -> ContextEngineInfo:
        """Engine identifier and metadata."""
        ...

    # ── Optional: session bootstrap ───────────────────────────────────────

    async def bootstrap(self, *, session_id: str, session_key: Optional[str] = None,
                        session_file: str) -> BootstrapResult:
        """Initialize engine state for a session. Optional."""
        return BootstrapResult()

    # ── Optional: transcript maintenance ───────────────────────────────────

    async def maintain(self, *, session_id: str, session_key: Optional[str] = None,
                       session_file: str,
                       runtime_context: Optional[ContextEngineRuntimeContext] = None,
                       ) -> ContextEngineMaintenanceResult:
        """Run transcript maintenance after bootstrap or compaction. Optional."""
        return ContextEngineMaintenanceResult()

    # ── Required: message ingestion ────────────────────────────────────────

    @abstractmethod
    async def ingest(self, *, session_id: str, session_key: Optional[str] = None,
                     message: Dict[str, Any], is_heartbeat: bool = False) -> IngestResult:
        """Ingest a single message into the engine's store."""
        ...

    # ── Optional: batch ingestion ──────────────────────────────────────────

    async def ingest_batch(self, *, session_id: str, session_key: Optional[str] = None,
                           messages: List[Dict[str, Any]],
                           is_heartbeat: bool = False) -> IngestBatchResult:
        """Ingest a completed turn batch as a single unit. Optional."""
        ingested = 0
        for msg in messages:
            result = await self.ingest(session_id=session_id, session_key=session_key,
                                       message=msg, is_heartbeat=is_heartbeat)
            if result.ingested:
                ingested += 1
        return IngestBatchResult(ingested_count=ingested)

    # ── Optional: post-turn lifecycle ──────────────────────────────────────

    async def after_turn(self, *, session_id: str, session_key: Optional[str] = None,
                         session_file: str, messages: List[Dict[str, Any]],
                         pre_prompt_message_count: int,
                         auto_compaction_summary: Optional[str] = None,
                         is_heartbeat: bool = False,
                         token_budget: Optional[int] = None,
                         runtime_context: Optional[ContextEngineRuntimeContext] = None) -> None:
        """Post-turn lifecycle work. Optional."""
        return

    # ── Required: context assembly ─────────────────────────────────────────

    @abstractmethod
    async def assemble(self, *, session_id: str, session_key: Optional[str] = None,
                       messages: List[Dict[str, Any]], token_budget: Optional[int] = None,
                       available_tools: Optional[Set[str]] = None,
                       citations_mode: Optional[str] = None,
                       model: Optional[str] = None,
                       prompt: Optional[str] = None) -> AssembleResult:
        """Assemble model context under a token budget. Returns ordered messages."""
        ...

    # ── Required: context compaction ───────────────────────────────────────

    @abstractmethod
    async def compact(self, *, session_id: str, session_key: Optional[str] = None,
                      session_file: str, token_budget: Optional[int] = None,
                      force: bool = False, current_token_count: Optional[int] = None,
                      compaction_target: str = "budget",
                      custom_instructions: Optional[str] = None,
                      runtime_context: Optional[ContextEngineRuntimeContext] = None,
                      abort_signal: Optional[Any] = None) -> CompactResult:
        """Compact context to reduce token usage. May create summaries, prune turns, etc."""
        ...

    # ── Optional: subagent lifecycle ───────────────────────────────────────

    async def prepare_subagent_spawn(self, *, parent_session_key: str,
                                     child_session_key: str,
                                     context_mode: str = "isolated",
                                     parent_session_id: Optional[str] = None,
                                     parent_session_file: Optional[str] = None,
                                     child_session_id: Optional[str] = None,
                                     child_session_file: Optional[str] = None,
                                     ttl_ms: Optional[int] = None,
                                     ) -> Optional[SubagentSpawnPreparation]:
        """Prepare context-engine-managed state before subagent run. Optional."""
        return None

    async def on_subagent_ended(self, *, child_session_key: str,
                                reason: SubagentEndReason) -> None:
        """Notify that a subagent lifecycle ended. Optional."""
        return

    # ── Optional: cleanup ──────────────────────────────────────────────────

    async def dispose(self) -> None:
        """Release any resources held by the engine. Optional."""
        return
