"""
Cognee memory adapter: implements MemoryBase using Cognee (add -> cognify -> search).
Use when memory_backend=cognee. Requires: pip install cognee and Cognee env config (.env)
or cognee section in core.yml (we convert it to env vars before Cognee loads).
Dataset scope: (user_id, agent_id) -> dataset name for add/search.
Summarization: get_all_async / delete_async use datasets list + get_data + delete_data when available.
"""
import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from memory.base import MemoryBase

# Composite id for summarization: "dataset_id:data_id" so delete_async can resolve both
COGNEE_ID_SEP = ":"


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
        # Set HUGGINGFACE_TOKENIZER first so Cognee/litellm see it before trying tiktoken mapping from EMBEDDING_MODEL (avoids "Could not automatically map ... to a tokeniser").
        for key, env_key in (("tokenizer", "HUGGINGFACE_TOKENIZER"), ("huggingface_tokenizer", "HUGGINGFACE_TOKENIZER")):
            val = emb.get(key)
            if val is not None and str(val).strip() != "":
                s = str(val).strip()
                if s.startswith(".") or s.startswith("/") or "\\" in s:
                    try:
                        from base.util import Util
                        root = Path(Util().root_path()).resolve()
                        p = (root / s).resolve() if not Path(s).is_absolute() else Path(s).resolve()
                        s = str(p)
                    except Exception:
                        pass
                os.environ[env_key] = s
                logger.debug("Cognee embedding tokenizer set: {} -> {}", key, s)
                break
        for key, env_key in (
            ("provider", "EMBEDDING_PROVIDER"), ("model", "EMBEDDING_MODEL"), ("endpoint", "EMBEDDING_ENDPOINT"), ("api_key", "EMBEDDING_API_KEY"),
            ("max_tokens", "EMBEDDING_MAX_TOKENS"), ("dimensions", "EMBEDDING_DIMENSIONS"),
        ):
            val = emb.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
        if "EMBEDDING_API_KEY" not in os.environ and emb.get("endpoint"):
            os.environ["EMBEDDING_API_KEY"] = "local"
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


def _parse_memory_dataset_name(name: str) -> Tuple[str, str]:
    """Parse 'memory_user_agent' -> (user_id, agent_id). Handles default and underscores in ids."""
    if not name or not name.startswith("memory_"):
        return "default", "default"
    rest = name[7:]  # after "memory_"
    parts = rest.split("_", 1)  # first _ separates user from agent
    u = (parts[0] or "default").strip()
    a = (parts[1] or "default").strip() if len(parts) > 1 else "default"
    return u or "default", a or "default"


class CogneeMemory(MemoryBase):
    """
    Memory backend using Cognee (add -> cognify -> search).
    Config: Cognee .env and/or core.yml cognee section (we apply cognee section to os.environ before loading Cognee).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._huggingface_tokenizer = None  # re-apply before add() so Cognee sees it at call time
        if config:
            apply_cognee_config(config)
            emb = config.get("embedding") or {}
            if isinstance(emb, dict):
                for key in ("tokenizer", "huggingface_tokenizer"):
                    val = (emb.get(key) or "").strip()
                    if val:
                        if val.startswith(".") or val.startswith("/") or "\\" in val:
                            try:
                                from base.util import Util
                                root = Path(Util().root_path()).resolve()
                                p = (root / val).resolve() if not Path(val).is_absolute() else Path(val).resolve()
                                val = str(p)
                            except Exception:
                                pass
                        self._huggingface_tokenizer = val
                        break
        try:
            import cognee  # noqa: F401
            self._cognee = cognee
        except ImportError as e:
            raise ImportError(
                "Cognee memory backend requires: pip install cognee. "
                "Configure via .env (LLM_*, EMBEDDING_*, DB_*, etc.). See docs.cognee.ai."
            ) from e
        # When using a custom embedding model (tokenizer set), Cognee/litellm may call tiktoken.encoding_for_model(embedding_model) which throws for unknown models. Fall back to cl100k_base so add/cognify does not fail.
        if self._huggingface_tokenizer:
            try:
                import tiktoken
                _orig_encoding_for_model = getattr(tiktoken, "encoding_for_model", None)
                if _orig_encoding_for_model and not getattr(tiktoken, "_homeclaw_patched", False):
                    def _encoding_for_model_fallback(model: str):
                        try:
                            return _orig_encoding_for_model(model)
                        except Exception:
                            return tiktoken.get_encoding("cl100k_base")
                    tiktoken.encoding_for_model = _encoding_for_model_fallback
                    tiktoken._homeclaw_patched = True
                    logger.debug("Cognee: tiktoken.encoding_for_model fallback to cl100k_base for unknown models")
            except Exception as e:
                logger.debug("Cognee tiktoken fallback not applied: {}", e)

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
        if self._huggingface_tokenizer:
            os.environ["HUGGINGFACE_TOKENIZER"] = self._huggingface_tokenizer
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
        """Sync get_all: returns [] for Cognee; use get_all_async from summarization job."""
        return []

    async def get_all_async(
        self,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List all memory items across memory_* datasets for summarization. Returns id as dataset_id:data_id, memory, created_at, user_id, agent_id. Never raises; returns [] on any failure."""
        out: List[Dict[str, Any]] = []
        try:
            ds = getattr(self._cognee, "datasets", None)
            if not ds or not hasattr(ds, "list_datasets"):
                return out
            try:
                datasets_list = await asyncio.wait_for(self._cognee.datasets.list_datasets(), timeout=30)
            except Exception as e:
                logger.debug("Cognee list_datasets for summarization: {}", e)
                return out
            get_data_fn = getattr(ds, "get_data", None) or getattr(ds, "get_dataset_data", None)
            if not get_data_fn or not callable(get_data_fn):
                logger.debug("Cognee datasets has no get_data/get_dataset_data; summarization list unavailable")
                return out
            for d in datasets_list or []:
                name = getattr(d, "name", None) or (d.get("name") if isinstance(d, dict) else None)
                if not name or not name.startswith("memory_"):
                    continue
                did = getattr(d, "id", None) or (d.get("id") if isinstance(d, dict) else None)
                if not did:
                    continue
                did = str(did)
                u_id, a_id = _parse_memory_dataset_name(name)
                try:
                    result = get_data_fn(did)
                    if asyncio.iscoroutine(result):
                        data_list = await asyncio.wait_for(result, timeout=15)
                    else:
                        data_list = result
                except Exception as e:
                    logger.debug("Cognee get_data({}) failed: {}", did[:8], e)
                    continue
                if not isinstance(data_list, list):
                    data_list = [data_list] if data_list else []
                for item in data_list[: limit]:
                    data_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
                    if not data_id:
                        continue
                    data_id = str(data_id)
                    created = getattr(item, "created_at", None) or getattr(item, "createdAt", None) or (item.get("created_at") or item.get("createdAt") if isinstance(item, dict) else None)
                    if created and hasattr(created, "isoformat"):
                        created = created.isoformat()
                    elif created:
                        created = str(created)
                    text = getattr(item, "content", None) or getattr(item, "text", None) or getattr(item, "data", None)
                    if isinstance(item, dict):
                        text = text or item.get("content") or item.get("text") or item.get("data") or item.get("raw_data")
                    text = (text or "").strip() if text else ""
                    meta = getattr(item, "metadata", None) if not isinstance(item, dict) else item.get("metadata")
                    is_sum = (meta.get("is_summary") if isinstance(meta, dict) else None) or (getattr(meta, "is_summary", None) if meta else None)
                    out.append({
                        "id": f"{did}{COGNEE_ID_SEP}{data_id}",
                        "memory": text,
                        "created_at": created,
                        "user_id": u_id,
                        "agent_id": a_id,
                        "metadata": {"is_summary": is_sum} if is_sum is not None else {},
                    })
                    if len(out) >= limit:
                        return out
        except Exception as e:
            logger.debug("Cognee get_all_async: {}", e)
        return out

    def update(self, memory_id: str, data: Any) -> Dict[str, Any]:
        return {"message": "Cognee backend: update not supported"}

    def delete(self, memory_id: str) -> None:
        """Sync delete: no-op for Cognee; use delete_async from summarization job."""
        pass

    async def delete_async(self, memory_id: str) -> None:
        """Delete one memory by composite id (dataset_id:data_id)."""
        if COGNEE_ID_SEP not in memory_id:
            return
        parts = memory_id.split(COGNEE_ID_SEP, 1)
        if len(parts) != 2:
            return
        dataset_id, data_id = parts[0].strip(), parts[1].strip()
        if not dataset_id or not data_id:
            return
        ds = getattr(self._cognee, "datasets", None)
        delete_fn = getattr(ds, "delete_data", None) or getattr(ds, "delete", None)
        if not delete_fn or not callable(delete_fn):
            logger.debug("Cognee datasets has no delete_data/delete")
            return
        try:
            if getattr(delete_fn, "__code__", None) and delete_fn.__code__.co_argcount >= 3:
                result = delete_fn(dataset_id, data_id)
            else:
                result = delete_fn(data_id, dataset_id=dataset_id)
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=10)
        except Exception as e:
            logger.debug("Cognee delete_data({}, {}): {}", dataset_id[:8], data_id[:8], e)

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

    def supports_summarization(self) -> bool:
        """Cognee supports summarization when datasets expose list_datasets, get_data, delete_data. Never raises."""
        try:
            ds = getattr(self._cognee, "datasets", None)
            if not ds:
                return False
            has_list = hasattr(ds, "list_datasets") and callable(getattr(ds, "list_datasets"))
            has_get = (hasattr(ds, "get_data") and callable(getattr(ds, "get_data"))) or (hasattr(ds, "get_dataset_data") and callable(getattr(ds, "get_dataset_data")))
            has_del = (hasattr(ds, "delete_data") and callable(getattr(ds, "delete_data"))) or (hasattr(ds, "delete") and callable(getattr(ds, "delete")))
            return bool(has_list and has_get and has_del)
        except Exception:
            return False

    def reset(self) -> None:
        try:
            import cognee
            asyncio.get_event_loop().run_until_complete(cognee.delete(all=True))
        except Exception as e:
            logger.debug("Cognee reset: {}", e)

    def chat(self, query: str) -> Any:
        raise NotImplementedError("Cognee backend: chat not implemented")
