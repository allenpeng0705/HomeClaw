"""
CogneeMemoryPlugin: wraps HomeClaw's Cognee adapter as a MemoryPlugin.

Same pattern as CompositeMemoryPlugin — bridges the existing MemoryBase
implementation to the new MemoryPlugin protocol.
"""

from __future__ import annotations

from typing import Any, List, Optional

from loguru import logger

from core.memory_plugin.protocol import (
    MemoryPlugin,
    MemorySearchResult,
    MemoryGetResult,
    MemoryHealthStatus,
)


class CogneeMemoryPlugin(MemoryPlugin):
    """Wraps memory/cognee_adapter.py as a single-backend MemoryPlugin."""

    def __init__(self, cognee_adapter: Any):
        self._backend = cognee_adapter
        self._plugin_id = "cognee"

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    async def search(
        self, query: str, *, max_results: int = 5,
        agent_session_key: Optional[str] = None,
        user_id: Optional[str] = None,
        friend_id: Optional[str] = None,
    ) -> List[MemorySearchResult]:
        try:
            raw = await self._backend.search(
                query, user_id=user_id, agent_id=friend_id, limit=max_results,
            )
        except Exception as e:
            logger.warning("CogneeMemoryPlugin.search failed: {}", e)
            return []
        if not isinstance(raw, list):
            return []
        results: List[MemorySearchResult] = []
        for item in raw[:max_results]:
            if not isinstance(item, dict):
                continue
            results.append(MemorySearchResult(
                corpus="cognee", path=str(item.get("id", "")),
                score=float(item.get("score", 0)),
                snippet=str(item.get("memory", ""))[:500],
                id=str(item.get("id", "")),
            ))
        return results

    async def get(
        self, lookup: str, *, from_line: Optional[int] = None,
        line_count: Optional[int] = None, agent_session_key: Optional[str] = None,
    ) -> Optional[MemoryGetResult]:
        try:
            item = self._backend.get(lookup)
        except Exception:
            return None
        if not isinstance(item, dict):
            return None
        content = str(item.get("memory", ""))
        return MemoryGetResult(
            corpus="cognee", content=content,
            from_line=from_line or 0, line_count=len(content.split("\n")),
            id=str(item.get("id", "")),
        )

    def build_prompt_section(
        self, *, available_tools: Optional[set] = None, citations_mode: str = "inline",
    ) -> str:
        if available_tools is not None and "agent_memory_search" not in available_tools:
            return ""
        return (
            "## Memory (Cognee)\n"
            "Cognee knowledge graph stores structured memories. "
            "Search with `agent_memory_search` when answering about prior context. "
            "Write with `append_agent_memory` when the user asks to remember something.\n\n"
        )

    async def health(self) -> MemoryHealthStatus:
        try:
            items = self._backend.get_all(limit=1)
            size = len(items) if isinstance(items, list) else None
            return MemoryHealthStatus(ok=True, backend="cognee", index_size=size)
        except Exception as e:
            return MemoryHealthStatus(ok=False, backend="cognee", error_count=1, details={"error": str(e)})
