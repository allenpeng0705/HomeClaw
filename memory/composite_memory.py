"""
Composite memory backend: use multiple backends (e.g. Cognee + MemOS) together.

- add(): writes to all configured backends (failures on one do not block others).
- search(): queries all backends and merges results by score (union, sorted by score, top limit).
- get/get_all/update/delete/delete_all: delegate to first backend or all where applicable.
- reset(): calls reset() on each backend.
- supports_summarization: False (each backend manages its own; batch summarization not run on composite).

Config: memory_backend: composite, then composite.backends: [cognee, memos] with cognee/memos sections as usual.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.base import MemoryBase


def _dedupe_by_content(items: List[Dict[str, Any]], key: str = "memory") -> List[Dict[str, Any]]:
    """Keep first occurrence of each distinct key value (e.g. memory text)."""
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for x in items:
        val = (x.get(key) or "").strip() or ""
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(x)
    return out


class CompositeMemory(MemoryBase):
    """Memory backend that delegates to multiple backends; add writes to all, search merges results."""

    def __init__(self, backends: List[tuple[str, MemoryBase]], merge_by_score: bool = True):
        """
        backends: list of (name, MemoryBase) e.g. [("cognee", cognee_instance), ("memos", memos_instance)].
        merge_by_score: when True, search() merges results from all backends and sorts by score desc.
        """
        self._backends = list(backends)
        self._merge_by_score = bool(merge_by_score)
        if not self._backends:
            raise ValueError("composite memory requires at least one backend")

    def get_memos_adapter(self) -> Optional[Any]:
        """Return the MemOS backend instance if present, for task/skill tools (memory_task_summary, memory_skill_search, memory_skill_get)."""
        for name, backend in self._backends:
            if name == "memos" and hasattr(backend, "get_task_summary_async"):
                return backend
        return None

    async def add(
        self,
        data: str,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        filters: Optional[Dict] = None,
        prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for name, backend in self._backends:
            try:
                if asyncio.iscoroutinefunction(backend.add):
                    out = await backend.add(
                        data,
                        user_name=user_name,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        metadata=metadata,
                        filters=filters,
                        prompt=prompt,
                    )
                else:
                    out = backend.add(
                        data,
                        user_name=user_name,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        metadata=metadata,
                        filters=filters,
                        prompt=prompt,
                    )
                if isinstance(out, list):
                    results.extend(out)
                else:
                    mem_preview = (data[:200] if isinstance(data, str) else (str(data[0].get("content", ""))[:200] if isinstance(data, list) and data and isinstance(data[0], dict) else ""))
                    results.append({"id": str(uuid.uuid4()), "memory": mem_preview})
            except Exception as e:
                logger.warning("composite add failed for backend {}: {}", name, e)
        if results:
            return results
        mem_preview = (data[:200] if isinstance(data, str) else (str(data[0].get("content", ""))[:200] if isinstance(data, list) and data and isinstance(data[0], dict) else ""))
        return [{"id": str(uuid.uuid4()), "memory": mem_preview}]

    async def search(
        self,
        query: str,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
        filters: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        if not self._backends:
            return []

        # When merge_by_score is False (primary_only), search only the first backend
        backends_to_search = self._backends if self._merge_by_score else self._backends[:1]

        async def search_one(name: str, backend: MemoryBase) -> List[Dict[str, Any]]:
            try:
                if asyncio.iscoroutinefunction(backend.search):
                    return await backend.search(
                        query,
                        user_name=user_name,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                return backend.search(
                    query,
                    user_name=user_name,
                    user_id=user_id,
                    agent_id=agent_id,
                    run_id=run_id,
                    limit=limit,
                    filters=filters,
                )
            except Exception as e:
                logger.warning("composite search failed for backend {}: {}", name, e)
                return []

        tasks = [search_one(n, b) for n, b in backends_to_search]
        all_results = await asyncio.gather(*tasks, return_exceptions=False)

        combined: List[Dict[str, Any]] = []
        for lst in all_results:
            if isinstance(lst, list):
                combined.extend(lst)

        if not self._merge_by_score or not combined:
            return combined[: limit or 100]

        # Dedupe by content (memory text), then sort by score desc, then take top limit
        deduped = _dedupe_by_content(combined, "memory")
        deduped.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
        return deduped[: limit or 100]

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        for _name, backend in self._backends:
            try:
                v = backend.get(memory_id)
                if v is not None:
                    return v
            except Exception:
                pass
        return None

    def get_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for _name, backend in self._backends:
            try:
                if asyncio.iscoroutinefunction(backend.get_all):
                    # Sync get_all in our interface; backend may have async get_all_async
                    lst = backend.get_all(
                        user_name=user_name,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        limit=limit,
                    )
                else:
                    lst = backend.get_all(
                        user_name=user_name,
                        user_id=user_id,
                        agent_id=agent_id,
                        run_id=run_id,
                        limit=limit,
                    )
                if isinstance(lst, list):
                    out.extend(lst)
            except Exception:
                pass
        return out[: limit or 100]

    def update(self, memory_id: str, data: Any) -> Dict[str, Any]:
        for name, backend in self._backends:
            try:
                return backend.update(memory_id, data)
            except Exception as e:
                logger.debug("composite update failed for {}: {}", name, e)
        return {"message": "composite: update not supported or failed on all backends"}

    def delete(self, memory_id: str) -> None:
        for _name, backend in self._backends:
            try:
                backend.delete(memory_id)
            except Exception:
                pass

    def delete_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        for _name, backend in self._backends:
            try:
                backend.delete_all(
                    user_name=user_name,
                    user_id=user_id,
                    agent_id=agent_id,
                    run_id=run_id,
                )
            except Exception:
                pass
        return {"message": "composite: delete_all called on all backends"}

    def history(self, memory_id: str) -> List[Any]:
        for _name, backend in self._backends:
            try:
                h = backend.history(memory_id)
                if h:
                    return h
            except Exception:
                pass
        return []

    def supports_summarization(self) -> bool:
        return False

    def reset(self) -> None:
        for name, backend in self._backends:
            try:
                backend.reset()
            except Exception as e:
                logger.warning("composite reset failed for backend {}: {}", name, e)

    def chat(self, query: str) -> Any:
        raise NotImplementedError("composite: chat not implemented")
