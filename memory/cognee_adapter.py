"""
Cognee memory adapter: implements MemoryBase using Cognee (add -> cognify -> search).
Use when memory_backend=cognee. Requires: pip install cognee and Cognee env config (.env)
or cognee section in core.yml (we convert it to env vars before Cognee loads).
Dataset scope: (user_id, agent_id) -> dataset name for add/search.
"""
import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.base import MemoryBase


def apply_cognee_config(config: Dict[str, Any]) -> None:
    """
    Apply cognee section from core.yml to os.environ so Cognee picks it up.
    Only sets env vars for non-empty string values. Optional 'env' dict sets raw Cognee env vars.
    When using Cognee as embedded memory (no Cognee API server), we disable backend access control
    so Cognee does not require a default user (default_user@example.com); scoping is via dataset_name only.
    """
    if not config:
        return
    # Disable Cognee's user system unless explicitly overridden (avoids UserNotFoundError: default_user@example.com)
    if "ENABLE_BACKEND_ACCESS_CONTROL" not in os.environ:
        os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
    # Relational -> DB_*
    rel = config.get("relational") or {}
    if isinstance(rel, dict):
        v = (rel.get("provider") or "").strip()
        if v:
            os.environ["DB_PROVIDER"] = v
        v = (rel.get("name") or "").strip()
        if v:
            os.environ["DB_NAME"] = v
        for key, env_key in (("host", "DB_HOST"), ("port", "DB_PORT"), ("username", "DB_USERNAME"), ("password", "DB_PASSWORD")):
            val = rel.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
    # Vector -> VECTOR_DB_* (Cognee vector store env)
    vec = config.get("vector") or {}
    if isinstance(vec, dict):
        v = (vec.get("provider") or "").strip()
        if v:
            os.environ["VECTOR_DB_PROVIDER"] = v
        for key, env_key in (("url", "VECTOR_DB_URL"), ("port", "VECTOR_DB_PORT"), ("key", "VECTOR_DB_KEY")):
            val = vec.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
    # Graph -> GRAPH_DATABASE_*
    gr = config.get("graph") or {}
    if isinstance(gr, dict):
        v = (gr.get("provider") or "").strip()
        if v:
            os.environ["GRAPH_DATABASE_PROVIDER"] = v
        for key, env_key in (("url", "GRAPH_DATABASE_URL"), ("username", "GRAPH_DATABASE_USERNAME"), ("password", "GRAPH_DATABASE_PASSWORD")):
            val = gr.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
    # LLM -> LLM_*
    llm = config.get("llm") or {}
    if isinstance(llm, dict):
        for key, env_key in (
            ("provider", "LLM_PROVIDER"), ("model", "LLM_MODEL"), ("endpoint", "LLM_ENDPOINT"), ("api_key", "LLM_API_KEY"),
        ):
            val = llm.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
        # Cognee requires LLM_API_KEY; use "local" for local endpoints when not set (avoids 422)
        if "LLM_API_KEY" not in os.environ and llm.get("endpoint"):
            os.environ["LLM_API_KEY"] = "local"
    # Embedding -> EMBEDDING_*
    emb = config.get("embedding") or {}
    if isinstance(emb, dict):
        for key, env_key in (
            ("provider", "EMBEDDING_PROVIDER"), ("model", "EMBEDDING_MODEL"), ("endpoint", "EMBEDDING_ENDPOINT"), ("api_key", "EMBEDDING_API_KEY"),
            ("max_tokens", "EMBEDDING_MAX_TOKENS"), ("dimensions", "EMBEDDING_DIMENSIONS"),
        ):
            val = emb.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
        if "EMBEDDING_API_KEY" not in os.environ and emb.get("endpoint"):
            os.environ["EMBEDDING_API_KEY"] = "local"
        # Tokenizer for token counting: Cognee maps embedding model to tiktoken; for custom/Ollama/HF models set HUGGINGFACE_TOKENIZER to silence "Could not automatically map embedding_text_model to a tokeniser" and get proper chunking (see docs.cognee.ai embedding providers).
        # If value looks like a path (starts with . or / or contains \), resolve relative to project root so relative paths work regardless of cwd.
        for key, env_key in (("tokenizer", "HUGGINGFACE_TOKENIZER"), ("huggingface_tokenizer", "HUGGINGFACE_TOKENIZER")):
            val = emb.get(key)
            if val is not None and str(val).strip() != "":
                s = str(val).strip()
                if s.startswith(".") or s.startswith("/") or "\\" in s:
                    try:
                        from base.util import Util
                        root = Path(Util().root_path()).resolve()
                        resolved = (root / s).resolve()
                        s = str(resolved)
                    except Exception:
                        pass
                os.environ[env_key] = s
                break
    # Raw env passthrough
    env = config.get("env")
    if isinstance(env, dict):
        for k, v in env.items():
            if k and v is not None:
                os.environ[str(k)] = str(v)


def _dataset_name(user_id: Optional[str] = None, agent_id: Optional[str] = None) -> str:
    u = (user_id or "").strip() or "default"
    a = (agent_id or "").strip() or "default"
    return f"memory_{u}_{a}".replace(" ", "_")[:128]


class CogneeMemory(MemoryBase):
    """
    Memory backend using Cognee (add -> cognify -> search).
    Config: Cognee .env and/or core.yml cognee section (we apply cognee section to os.environ before loading Cognee).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config:
            apply_cognee_config(config)
        try:
            import cognee  # noqa: F401
            self._cognee = cognee
        except ImportError as e:
            raise ImportError(
                "Cognee memory backend requires: pip install cognee. "
                "Configure via .env (LLM_*, EMBEDDING_*, DB_*, etc.). See docs.cognee.ai."
            ) from e

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
        memory_id = str(uuid.uuid4())
        dataset = _dataset_name(user_id=user_id, agent_id=agent_id)
        try:
            await self._cognee.add(data, dataset_name=dataset)
            await self._cognee.cognify(datasets=[dataset])
        except Exception as e:
            logger.debug("Cognee add/cognify: {}", e)
        return [{"id": memory_id, "event": "add", "data": data}]

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
        dataset = _dataset_name(user_id=user_id, agent_id=agent_id)
        # Avoid calling Cognee search on a non-existent dataset (prevents DatasetNotFoundError 404 and its error log)
        if hasattr(self._cognee, "datasets") and hasattr(self._cognee.datasets, "list_datasets"):
            try:
                datasets_list = await asyncio.wait_for(
                    self._cognee.datasets.list_datasets(),
                    timeout=15,
                )
                names = []
                for d in (datasets_list or []):
                    n = getattr(d, "name", None) or (d.get("name") if isinstance(d, dict) else None)
                    if n:
                        names.append(n)
                if dataset not in names:
                    return []
            except (asyncio.TimeoutError, Exception):
                pass  # fall back to search (may 404 and log; we catch below)
        try:
            results = await self._cognee.search(query, datasets=[dataset], top_k=limit or 10)
        except Exception as e:
            # Empty graph can cause Cognee to log "No nodes found" / EntityNotFoundError; we return [] and continue
            logger.debug("Cognee search: {}", e)
            return []
        out = []
        for i, r in enumerate(results if isinstance(results, list) else [results]):
            if isinstance(r, str):
                out.append({"id": str(uuid.uuid4()), "memory": r, "score": 0.8 - i * 0.05})
            elif isinstance(r, dict):
                text = r.get("text") or r.get("content") or r.get("memory") or str(r)
                out.append({
                    "id": r.get("id", str(uuid.uuid4())),
                    "memory": text,
                    "score": float(r.get("score", 0.8 - i * 0.05)),
                    **{k: v for k, v in r.items() if k not in ("id", "memory", "score", "text", "content")},
                })
            else:
                out.append({"id": str(uuid.uuid4()), "memory": str(r), "score": 0.8})
        return out[: limit or 100]

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
        return {"message": "Cognee backend: update not supported"}

    def delete(self, memory_id: str) -> None:
        pass

    def delete_all(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {"message": "Cognee backend: delete_all not supported"}

    def history(self, memory_id: str) -> List[Any]:
        return []

    def reset(self) -> None:
        try:
            import cognee
            asyncio.get_event_loop().run_until_complete(cognee.delete(all=True))
        except Exception as e:
            logger.debug("Cognee reset: {}", e)

    def chat(self, query: str) -> Any:
        raise NotImplementedError("Cognee backend: chat not implemented")
