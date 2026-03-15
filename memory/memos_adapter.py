"""
MemOS memory adapter: implements MemoryBase by calling the MemOS standalone HTTP server.

Use when memory_backend=memos. MemOS is vendored in vendor/memos; run the standalone server
(cd vendor/memos && npm run standalone) then set memos.url in config (e.g. http://127.0.0.1:39201).

Config: memory_kb.yml under memos: url (required), timeout (optional).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from loguru import logger

from memory.base import MemoryBase


def _agent_id(user_id: Optional[str], agent_id: Optional[str]) -> str:
    """Map HomeClaw (user_id, agent_id) to MemOS owner/agentId."""
    u = (user_id or "").strip() or "default"
    a = (agent_id or "").strip() or "main"
    if a == "main" and u != "default":
        return f"{u}_main"
    return f"{u}_{a}" if u != "default" else a


class MemosMemoryAdapter(MemoryBase):
    """Memory backend that talks to the MemOS standalone HTTP server (vendor/memos)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self._base_url = (cfg.get("url") or "").strip().rstrip("/")
        self._timeout = float(cfg.get("timeout") or 30)
        if not self._base_url:
            raise ValueError("memos.url is required when memory_backend=memos")

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        import httpx
        url = self._base_url + path
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(url, json=body)
                r.raise_for_status()
                return r.json() if r.content else {}
        except Exception as e:
            logger.debug("Memos HTTP {} failed: {}", path, e)
            raise

    async def _get(self, path: str) -> Dict[str, Any]:
        import httpx
        url = self._base_url + path
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url)
                r.raise_for_status()
                return r.json() if r.content else {}
        except Exception as e:
            logger.debug("Memos HTTP {} failed: {}", path, e)
            raise

    async def _put(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        import httpx
        url = self._base_url + path
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.put(url, json=body)
                r.raise_for_status()
                return r.json() if r.content else {}
        except Exception as e:
            logger.debug("Memos HTTP {} failed: {}", path, e)
            raise

    async def add(
        self,
        data: Any,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        filters: Optional[Dict] = None,
        prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # data: str (user message only) or list of {role, content, toolName?} for full turn (user+assistant+tool)
        if isinstance(data, list):
            if not data:
                return []
            messages = []
            for m in data:
                if not isinstance(m, dict):
                    continue
                role = (str(m.get("role") or "user").strip() or "user")
                content = m.get("content")
                if isinstance(content, str) and content.strip():
                    if role == "assistant":
                        from base.util import strip_reasoning_from_assistant_text
                        content = strip_reasoning_from_assistant_text(content)
                    if content and content.strip():
                        msg = {"role": role, "content": content.strip()}
                        if role == "tool":
                            msg["toolName"] = str(m.get("toolName") or m.get("tool_name") or "tool")
                        messages.append(msg)
            if not messages:
                return []
        else:
            s = (data or "").strip() if isinstance(data, str) else ""
            if not s:
                return []
            messages = [{"role": "user", "content": s}]
        agent = _agent_id(user_id, agent_id)
        session_key = (user_id or "").strip() or "default"
        body = {"messages": messages, "sessionKey": session_key, "agentId": agent}
        try:
            await self._post("/memory/add", body)
            return [{"id": str(uuid.uuid4()), "memory": messages[0].get("content", "")[:200]}]
        except Exception as e:
            logger.warning("Memos add failed: {}", e)
            return []

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
        if not (query or "").strip():
            return []
        agent = _agent_id(user_id, agent_id)
        body = {
            "query": (query or "").strip(),
            "maxResults": min(limit or 100, 100),
            "minScore": 0.45,
            "agentId": agent,
        }
        try:
            out = await self._post("/memory/search", body)
            hits = out.get("hits") or []
            result = []
            for i, h in enumerate(hits):
                text = h.get("summary") or h.get("original_excerpt") or ""
                ref = h.get("ref") or {}
                chunk_id = ref.get("chunkId") or str(uuid.uuid4())
                score = float(h.get("score", 0.8) - i * 0.05)
                result.append({
                    "id": chunk_id,
                    "memory": text,
                    "score": max(0.0, score),
                })
            return result[: limit or 100]
        except Exception as e:
            logger.warning("Memos search failed: {}", e)
            return []

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        return None

    def get_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return []

    def update(self, memory_id: str, data: Any) -> Dict[str, Any]:
        return {"message": "Memos backend: update not supported"}

    def delete(self, memory_id: str) -> None:
        pass

    def delete_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {"message": "Memos backend: delete_all not supported"}

    def history(self, memory_id: str) -> List[Any]:
        return []

    def supports_summarization(self) -> bool:
        return False

    def reset(self) -> None:
        """Clear all MemOS memories by calling POST /memory/reset on the MemOS server. Used by HomeClaw /memory/reset. Never raises."""
        try:
            base = (self._base_url or "").strip().rstrip("/")
            if not base:
                return
            url = base + "/memory/reset"
            timeout = max(1.0, float(self._timeout)) if self._timeout is not None else 30.0
            req = Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=timeout) as _:
                pass  # 200 = success
        except HTTPError as e:
            if e.code == 501:
                logger.debug("MemOS store does not support reset (update SqliteStore to implement reset())")
            else:
                logger.warning("Memos reset failed: HTTP {} {}", e.code, e.reason)
        except (URLError, OSError, TimeoutError) as e:
            logger.debug("Memos reset request failed: {}", e)
        except Exception as e:
            logger.debug("Memos reset failed: {}", e)

    def chat(self, query: str) -> Any:
        raise NotImplementedError("Memos backend: chat not implemented")

    # ─── MemOS task/skill APIs (for memory_task_summary, memory_skill_search, memory_skill_get tools) ───

    async def get_task_summary_async(
        self,
        task_id: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """GET /memory/task/:id/summary. Returns task title, summary (Goal, Key Steps, Result, Key Details), status, etc."""
        tid = (task_id or "").strip()
        if not tid or "/" in tid or "\\" in tid:
            return None
        try:
            out = await self._get(f"/memory/task/{tid}/summary")
            if isinstance(out, dict) and "error" not in out:
                return out
            return None
        except Exception as e:
            logger.debug("Memos get_task_summary failed: {}", e)
            return None

    async def skill_search_async(
        self,
        query: str,
        scope: str = "mix",
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """POST /memory/skill_search. Returns list of { skillId, name, description, score, ... }."""
        if not (query or "").strip():
            return []
        agent = _agent_id(user_id, agent_id)
        body: Dict[str, Any] = {
            "query": (query or "").strip(),
            "scope": scope if scope in ("self", "public", "mix") else "mix",
            "agentId": agent,
        }
        try:
            out = await self._post("/memory/skill_search", body)
            hits = out.get("hits") or []
            return list(hits) if isinstance(hits, list) else []
        except Exception as e:
            logger.debug("Memos skill_search failed: {}", e)
            return []

    async def skill_get_async(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """GET /memory/skill/:id. Returns skill metadata and content (SKILL.md body)."""
        sid = (skill_id or "").strip()
        if not sid or "/" in sid or "\\" in sid:
            return None
        try:
            out = await self._get(f"/memory/skill/{sid}")
            if isinstance(out, dict) and "error" not in out:
                return out
            return None
        except Exception as e:
            logger.debug("Memos skill_get failed: {}", e)
            return None

    async def list_tasks_async(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """GET /memory/tasks. Returns { tasks, total } for the owner. Never raises."""
        try:
            limit = max(1, min(100, int(limit))) if isinstance(limit, (int, float)) else 50
        except (TypeError, ValueError):
            limit = 50
        try:
            offset = max(0, int(offset)) if isinstance(offset, (int, float)) else 0
        except (TypeError, ValueError):
            offset = 0
        if status is not None and str(status).strip() not in ("active", "completed", "skipped"):
            status = None
        agent = _agent_id(user_id, agent_id)
        params: Dict[str, Any] = {"agentId": agent, "limit": limit, "offset": offset}
        if status:
            params["status"] = status
        try:
            path = "/memory/tasks?" + urlencode(params)
            out = await self._get(path)
            if not isinstance(out, dict) or "error" in out:
                return {"tasks": [], "total": 0}
            tasks = out.get("tasks")
            total = out.get("total")
            return {
                "tasks": list(tasks) if isinstance(tasks, list) else [],
                "total": int(total) if isinstance(total, (int, float)) else 0,
            }
        except Exception as e:
            logger.debug("Memos list_tasks failed: {}", e)
            return {"tasks": [], "total": 0}

    async def write_public_async(self, content: str, summary: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """POST /memory/write_public. Write a chunk with owner 'public' (visible to all agents)."""
        content_str = (content or "").strip()
        if not content_str:
            return None
        body: Dict[str, Any] = {"content": content_str}
        if summary is not None and (summary or "").strip():
            body["summary"] = (summary or "").strip()
        try:
            out = await self._post("/memory/write_public", body)
            if isinstance(out, dict) and out.get("ok") and "error" not in out:
                return out
            return None
        except Exception as e:
            logger.debug("Memos write_public failed: {}", e)
            return None

    async def skill_set_visibility_async(self, skill_id: str, visibility: str) -> Optional[Dict[str, Any]]:
        """PUT /memory/skill/:id/visibility. Set skill visibility to 'public' or 'private' (publish/unpublish)."""
        sid = (skill_id or "").strip()
        if not sid:
            return None
        if visibility not in ("public", "private"):
            return None
        if "/" in sid or "\\" in sid or "?" in sid or "#" in sid:
            logger.debug("Memos skill_set_visibility: invalid skill_id (contains path chars)")
            return None
        try:
            out = await self._put(f"/memory/skill/{sid}/visibility", {"visibility": visibility})
            if isinstance(out, dict) and "error" not in out:
                return out
            return None
        except Exception as e:
            logger.debug("Memos skill_set_visibility failed: {}", e)
            return None
