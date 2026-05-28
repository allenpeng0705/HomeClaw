"""
MemoryPlugin protocol: single-slot pluggable memory backend.

Inspired by OpenClaw's memory-host-sdk and memory-state plugin design.
Defines the contract that every memory backend must implement to be used
as the active memory plugin for an agent session.

Only ONE MemoryPlugin is active at a time per agent (single-slot design).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Result types ───────────────────────────────────────────────────────────


@dataclass
class MemorySearchResult:
    """A single search hit from the memory backend."""
    corpus: str = ""          # e.g. "agent_memory", "daily_memory", "MEMORY.md"
    path: str = ""            # file path or memory collection name
    title: Optional[str] = None
    kind: Optional[str] = None
    score: float = 0.0
    snippet: str = ""         # relevant excerpt
    id: Optional[str] = None  # memory entry id for retrieval
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    citation: Optional[str] = None
    source: Optional[str] = None
    provenance_label: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class MemoryGetResult:
    """Full content retrieval for a specific memory entry."""
    corpus: str = ""
    path: str = ""
    title: Optional[str] = None
    kind: Optional[str] = None
    content: str = ""
    from_line: int = 0
    line_count: int = 0
    id: Optional[str] = None
    provenance_label: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class MemoryFlushPlan:
    """Resolved plan for when and how to flush memory."""
    soft_threshold_tokens: int = 30000
    force_flush_transcript_bytes: int = 0
    reserve_tokens_floor: int = 4096
    model: Optional[str] = None
    prompt: str = ""
    system_prompt: str = ""
    relative_path: str = ""


@dataclass
class MemoryFlushResult:
    """Result of a memory flush operation."""
    flushed: bool = False
    items_stored: int = 0
    reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class MemoryHealthStatus:
    """Health check result for a memory plugin."""
    ok: bool = True
    backend: str = ""             # e.g. "composite", "cognee", "memos"
    vector_store_ok: bool = True
    embedding_model_ok: bool = True
    index_size: Optional[int] = None
    last_flush_at: Optional[str] = None
    error_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


# ── MemoryPlugin ABC ────────────────────────────────────────────────────────


class MemoryPlugin(ABC):
    """
    Pluggable memory backend contract.

    Required methods: search, get, build_prompt_section
    Optional methods: flush, health, dispose

    Only one MemoryPlugin is active per agent at a time.
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier for this memory plugin."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        agent_session_key: Optional[str] = None,
        user_id: Optional[str] = None,
        friend_id: Optional[str] = None,
    ) -> List[MemorySearchResult]:
        """
        Semantic search over the memory corpus.

        Returns ranked results with snippets. The ContextEngine or LLM loop
        can use these to inject relevant context into the system prompt.
        """
        ...

    @abstractmethod
    async def get(
        self,
        lookup: str,
        *,
        from_line: Optional[int] = None,
        line_count: Optional[int] = None,
        agent_session_key: Optional[str] = None,
    ) -> Optional[MemoryGetResult]:
        """
        Retrieve full content for a specific memory entry by id or path.

        lookup: memory entry id, file path, or corpus key.
        """
        ...

    @abstractmethod
    def build_prompt_section(
        self,
        *,
        available_tools: Optional[set] = None,
        citations_mode: str = "inline",
    ) -> str:
        """
        Build the memory guidance section injected into the system prompt.

        Returns a string suitable for appending to the system prompt that
        tells the LLM: what memory tools are available, how to use them,
        and any cached memory content to bootstrap context.
        """
        ...

    async def flush(
        self,
        *,
        token_count: int = 0,
        force: bool = False,
    ) -> MemoryFlushResult:
        """
        Trigger a memory flush: store durable memories from the current session.

        Optional. Default no-op. Engines call this during compaction when
        token thresholds are breached.
        """
        return MemoryFlushResult()

    async def resolve_flush_plan(self) -> Optional[MemoryFlushPlan]:
        """
        Resolve the flush plan: when and how to flush.

        Optional. Returns None if flushing is not needed.
        """
        return None

    async def health(self) -> MemoryHealthStatus:
        """
        Return health status of this memory plugin.

        Optional. Default returns basic ok status.
        """
        return MemoryHealthStatus(
            ok=True,
            backend=self.plugin_id,
        )

    async def doctor(self) -> Dict[str, Any]:
        """
        Run diagnostic checks and return a report.

        Returns a dict with:
          - ok: bool — overall health
          - issues: list of {severity, message, fixable} dicts
          - fixes_applied: list of fix descriptions (if any)
        """
        health = await self.health()
        issues: List[Dict[str, Any]] = []
        if not health.ok:
            issues.append({
                "severity": "error",
                "message": f"Backend '{health.backend}' is unhealthy",
                "fixable": False,
                "details": health.details,
            })
        return {
            "ok": health.ok,
            "issues": issues,
            "fixes_applied": [],
        }

    async def dispose(self) -> None:
        """Release any resources. Optional."""
        return
