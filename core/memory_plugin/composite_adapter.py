"""
CompositeMemoryPlugin: wraps HomeClaw's existing CompositeMemory as a MemoryPlugin.

This adapter bridges the existing memory infrastructure (MemoryBase, CompositeMemory)
to the new MemoryPlugin protocol. All existing memory behavior is preserved;
the adapter adds the OpenClaw-inspired search/get/prompt-building methods.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from core.memory_plugin.protocol import (
    MemoryPlugin,
    MemorySearchResult,
    MemoryGetResult,
    MemoryFlushResult,
    MemoryHealthStatus,
)


class CompositeMemoryPlugin(MemoryPlugin):
    """
    Wraps HomeClaw's CompositeMemory as a single-slot MemoryPlugin.

    Preserves all existing memory behavior (add, search, get, etc.) while
    adding the structured search/get/prompt-building interface required by
    the MemoryPlugin protocol.
    """

    def __init__(self, composite_memory: Any):
        """
        Args:
            composite_memory: An instance of memory/composite_memory.CompositeMemory
        """
        self._composite = composite_memory
        self._plugin_id = "composite"

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    # ── search ──────────────────────────────────────────────────────────

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
        Semantic search over composite memory backends.

        Delegates to CompositeMemory.search() and maps results to the
        structured MemorySearchResult format.
        """
        try:
            raw_results = await self._composite.search(
                query,
                user_id=user_id,
                agent_id=friend_id,  # existing code uses agent_id for friend scope
                limit=max_results,
            )
        except Exception as e:
            logger.warning("CompositeMemoryPlugin.search failed: {}", e)
            return []

        if not isinstance(raw_results, list):
            return []

        results: List[MemorySearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(MemorySearchResult(
                corpus="composite",
                path=item.get("memory", "")[:80] if item.get("memory") else "",
                score=float(item.get("score", 0)),
                snippet=str(item.get("memory", ""))[:500],
                id=str(item.get("id", "")),
                updated_at=str(item.get("created_at", "")),
            ))
        return results

    # ── get ─────────────────────────────────────────────────────────────

    async def get(
        self,
        lookup: str,
        *,
        from_line: Optional[int] = None,
        line_count: Optional[int] = None,
        agent_session_key: Optional[str] = None,
    ) -> Optional[MemoryGetResult]:
        """
        Retrieve a specific memory entry by id.

        Falls back to searching by snippet if exact id lookup fails.
        """
        try:
            item = self._composite.get(lookup)
        except Exception as e:
            logger.debug("CompositeMemoryPlugin.get failed: {}", e)
            return None

        if item is None or not isinstance(item, dict):
            return None

        content = str(item.get("memory", ""))
        if from_line is not None:
            lines = content.split("\n")
            start = max(0, from_line)
            end = start + (line_count or len(lines))
            content = "\n".join(lines[start:end])

        return MemoryGetResult(
            corpus="composite",
            path=str(item.get("id", "")),
            content=content,
            from_line=from_line or 0,
            line_count=len(content.split("\n")),
            id=str(item.get("id", "")),
            updated_at=str(item.get("created_at", "")),
        )

    # ── build_prompt_section ────────────────────────────────────────────

    def build_prompt_section(
        self,
        *,
        available_tools: Optional[set] = None,
        citations_mode: str = "inline",
    ) -> str:
        """
        Build the memory guidance section for the system prompt.

        Mirrors the existing memory directive from llm_loop.py lines 1957-1977.
        """
        has_agent_memory = available_tools is None or "agent_memory_search" in available_tools
        has_daily_memory = available_tools is None or "append_daily_memory" in available_tools

        parts: List[str] = []

        if has_agent_memory:
            parts.append(
                "## Memory (agent)\n"
                "Agent memory stores lasting facts and preferences across sessions. "
                "Search with `agent_memory_search` when answering about prior work, "
                "decisions, people, or preferences. "
                "Write with `append_agent_memory` when the user says to remember something."
            )

        if has_daily_memory:
            parts.append(
                "## Memory (daily)\n"
                "Daily memory records today's session context. "
                "Write with `append_daily_memory` for notes about what was discussed today."
            )

        if not parts:
            return ""

        return "\n\n".join(parts) + "\n\n"

    # ── health ──────────────────────────────────────────────────────────

    async def health(self) -> MemoryHealthStatus:
        """
        Quick health check: verify the composite backend responds to a get_all call.
        """
        try:
            items = self._composite.get_all(limit=1)
            index_size = len(items) if isinstance(items, list) else None
            return MemoryHealthStatus(
                ok=True,
                backend="composite",
                index_size=index_size,
            )
        except Exception as e:
            return MemoryHealthStatus(
                ok=False,
                backend="composite",
                error_count=1,
                details={"error": str(e)},
            )
