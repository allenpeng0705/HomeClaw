"""
Cognee memory adapter: implements MemoryBase using Cognee (add -> cognify -> search).
Use when memory_backend=cognee. Cognee is part of this repo (customized); install only its
dependencies (pip install -r requirements-cognee-deps.txt), not the cognee package.
Config: Cognee .env and/or cognee section in core.yml (we convert to env vars before Cognee loads).
Dataset scope: (user_id, agent_id) -> dataset name for add/search.
Summarization: get_all_async / delete_async use datasets list + get_data + delete_data when available.

How Cognee works now (system message at the top):
- At init we apply memory/instructor_patch.py: (1) litellm completion/acompletion are wrapped so
  every request's messages are normalized to have a system message first (reorder existing system
  messages to the top, or prepend a minimal system message if none); (2) Instructor Jinja
  templating is disabled (no-op) so strict "system first" validation never raises; (3) Instructor
  parse_tools accepts 0 or multiple tool_calls for local LLMs. Cognee/Instructor then call litellm
  with messages that always start with system, so local backends and Instructor stay happy.
- add(): we call cognee.add() then cognee.cognify(). All exceptions are caught; we never raise.
  On cognify template/local failure we optionally retry once with cognee.llm_fallback and restore
  primary LLM. Memory add is skipped on failure; chat and tools are unaffected.
- Local LLM "coroutine is not callable" fix: we patch Instructor so our wrapped litellm.acompletion
  is always treated as async (__homeclaw_force_async__) and instructor.utils.is_async returns True
  for it; thus cognify uses retry_async and await func(), never retry_sync which would call
  func() without await. This makes Cognee + local model work without vendoring Cognee.
"""
import asyncio
import logging
import os
import re
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from memory.base import MemoryBase

# Composite id for summarization: "dataset_id:data_id" so delete_async can resolve both
COGNEE_ID_SEP = ":"
COGNEE_GRAPH_DATASETS_FILE = "cognee_datasets_with_graph.txt"


def _load_cognee_graph_datasets() -> set[str]:
    """Load set of dataset names that have had at least one successful cognify (persisted so we skip search on empty graph after restart)."""
    out: set[str] = set()
    try:
        from base.util import Util
        path = os.path.join(Util().data_path(), COGNEE_GRAPH_DATASETS_FILE)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    name = (line or "").strip()
                    if name and name.startswith("memory_"):
                        out.add(name)
    except Exception:
        pass
    return out


def _save_cognee_graph_dataset(dataset: str) -> None:
    """Append a dataset name to the persisted list (called after successful cognify)."""
    try:
        from base.util import Util
        path = os.path.join(Util().data_path(), COGNEE_GRAPH_DATASETS_FILE)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(dataset + "\n")
    except Exception:
        pass


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
    # Vector -> VECTOR_DB_* (Cognee vector store env). Cognee expects exact names: ChromaDB, LanceDB, PGVector, neptune_analytics.
    _vector_provider_map = {
        "chroma": "ChromaDB", "chromadb": "ChromaDB",
        "lancedb": "LanceDB", "pgvector": "PGVector",
        "neptune_analytics": "neptune_analytics",
    }
    vec = config.get("vector") or {}
    if isinstance(vec, dict):
        v = (vec.get("provider") or "").strip()
        if v:
            os.environ["VECTOR_DB_PROVIDER"] = _vector_provider_map.get(v.lower(), v)
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
        # LiteLLM: drop unsupported params (e.g. dimensions) so local/custom embedding models don't get 422. Set before any Cognee/LiteLLM embedding call (KB and Memory both call apply_cognee_config).
        try:
            import litellm
            litellm.drop_params = True
            logger.debug("Cognee: litellm.drop_params = True")
        except Exception:
            pass
        # Local/custom models (Qwen, Ollama, etc.) often don't support dimensions; avoid sending EMBEDDING_DIMENSIONS so Cognee/litellm don't get 422. Local-first safe.
        emb_endpoint = (emb.get("endpoint") or "").strip().lower()
        emb_model = (emb.get("model") or "").strip().lower()
        emb_provider = (emb.get("provider") or "").strip().lower()
        is_local_embedding = (
            "127.0.0.1" in emb_endpoint or "localhost" in emb_endpoint
            or any(x in emb_model for x in ("qwen", "embedding_text_model", "0.6b", "nomic", "ollama", "openai/"))
            or any(x in emb_provider for x in ("ollama", "local", "openai/"))
        )
        if is_local_embedding and "EMBEDDING_DIMENSIONS" in os.environ:
            del os.environ["EMBEDDING_DIMENSIONS"]
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
            ("max_tokens", "EMBEDDING_MAX_TOKENS"),
        ):
            val = emb.get(key)
            if val is not None and str(val).strip() != "":
                os.environ[env_key] = str(val)
        if not is_local_embedding:
            val = emb.get("dimensions")
            if val is not None and str(val).strip() != "":
                os.environ["EMBEDDING_DIMENSIONS"] = str(val)
        if "EMBEDDING_API_KEY" not in os.environ and emb.get("endpoint"):
            os.environ["EMBEDDING_API_KEY"] = "local"
    # Raw env passthrough
    env = config.get("env")
    if isinstance(env, dict):
        for k, v in env.items():
            if k and v is not None:
                os.environ[str(k)] = str(v)


def _apply_llm_only(llm_dict: Optional[Dict[str, Any]]) -> None:
    """
    Apply only LLM settings to env and Cognee config (for cognify retry with fallback).
    Use when switching to fallback LLM or restoring primary. Empty value removes env var.
    """
    if llm_dict is None or not isinstance(llm_dict, dict):
        return
    for key, env_key in (
        ("provider", "LLM_PROVIDER"), ("model", "LLM_MODEL"), ("endpoint", "LLM_ENDPOINT"), ("api_key", "LLM_API_KEY"),
    ):
        val = llm_dict.get(key)
        if val is not None and str(val).strip() != "":
            os.environ[env_key] = str(val).strip()
        elif env_key in os.environ:
            os.environ.pop(env_key, None)
    if llm_dict.get("endpoint") and "LLM_API_KEY" not in os.environ:
        os.environ["LLM_API_KEY"] = "local"
    try:
        import cognee
        if hasattr(cognee, "config") and hasattr(cognee.config, "set_llm_config"):
            cognee.config.set_llm_config({k: v for k, v in llm_dict.items() if v is not None and str(v).strip() != ""})
    except Exception:
        pass


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
        self._config = config or {}
        self._huggingface_tokenizer = None  # re-apply before add() so Cognee sees it at call time
        self._datasets_with_graph = _load_cognee_graph_datasets()  # skip search when dataset never had successful cognify (avoids empty-graph warning)
        # Optional: use only when cognify fails with local LLM (template/Instructor). Enables local-first + reliable cognify.
        _fb = self._config.get("llm_fallback")
        self._cognify_llm_fallback = None
        if isinstance(_fb, dict) and (_fb.get("model") or _fb.get("endpoint")):
            self._cognify_llm_fallback = _fb
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
            # Patch Instructor so cognify works with local LLMs (0 or multiple tool_calls). Never crash if patch fails.
            try:
                from memory.instructor_patch import apply_instructor_patch_for_local_llm
                apply_instructor_patch_for_local_llm()
            except Exception:
                pass
            import cognee  # noqa: F401
            self._cognee = cognee
            # Reduce Cognee log noise: empty-graph warnings and large failed_attempts dumps
            for _log_name in ("cognee.shared.logging_utils", "cognee.shared", "GraphCompletionRetriever"):
                try:
                    logging.getLogger(_log_name).setLevel(logging.CRITICAL)
                except Exception:
                    pass
        except ImportError as e:
            raise ImportError(
                "Cognee memory backend requires the cognee package (part of this repo) and its dependencies (pip install -r requirements-cognee-deps.txt). Configure via .env or cognee section in config."
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
        logger.debug("Cognee memory add: step=start dataset={} data_len={}", dataset, len(data or ""))
        try:
            # Step 1: add raw data to Cognee dataset
            await self._cognee.add(data, dataset_name=dataset)
            logger.debug("Cognee memory add: step=add_ok dataset={}", dataset)
            # Step 2: cognify (LLM/graph pipeline) — try primary LLM first; on template/local failure retry with llm_fallback if set
            cognify_ok = False
            try:
                await self._cognee.cognify(datasets=[dataset])
                cognify_ok = True
            except Exception as e:
                exc_type = type(e).__name__
                msg = str(e).strip()
                if len(msg) > 400 or "<failed_attempts>" in msg:
                    if "<last_exception>" in msg:
                        m = re.search(r"<last_exception>\s*(.+?)\s*</last_exception>", msg, re.DOTALL)
                        summary = (m.group(1).strip()[:300] if m else None) or "Instructor/cognify error"
                    else:
                        first = msg.split("\n")[0].strip()
                        summary = first[:300] if first else "Cognify failed"
                    summary = summary or "Cognee add/cognify error"
                else:
                    summary = msg or "Cognee add/cognify error"
                # Always log full traceback at DEBUG for any cognify failure (local LLM debugging)
                try:
                    tb_str = "".join(traceback.format_exception(type(e), e, getattr(e, "__traceback__", None)))
                    _tb_msg = "Cognee cognify failure (full traceback):\n" + (tb_str or "(no traceback)")
                    logger.debug(_tb_msg)
                    try:
                        sys.stderr.write(_tb_msg)
                        if not _tb_msg.endswith("\n"):
                            sys.stderr.write("\n")
                        sys.stderr.flush()
                    except Exception:
                        pass
                except Exception:
                    pass
                msg_lower = msg.lower()
                summary_lower = summary.lower()
                step_failed = "cognify" if (
                    exc_type == "InstructorRetryException"
                    or "cognify" in msg_lower
                    or "instructor" in msg_lower
                    or "template" in msg_lower
                    or "litellm" in msg_lower
                    or "raise_exception" in msg_lower
                    or "jinja" in summary_lower
                    or "system me" in summary_lower
                ) else "add"
                is_template_error = step_failed == "cognify" and (
                    "Jinja" in summary or "System message" in summary or "raise_exception" in summary or "litellm" in msg or exc_type == "InstructorRetryException"
                )
                if step_failed == "cognify" and is_template_error and self._cognify_llm_fallback:
                    try:
                        _apply_llm_only(self._cognify_llm_fallback)
                        await self._cognee.cognify(datasets=[dataset])
                        cognify_ok = True
                        logger.info("Cognee memory add: cognify succeeded with fallback LLM dataset={}", dataset)
                    except Exception as e2:
                        logger.warning(
                            "Cognee memory add: cognify retry with fallback failed dataset={} exc={}",
                            dataset, type(e2).__name__,
                        )
                    finally:
                        _apply_llm_only(self._config.get("llm") or {})
                if not cognify_ok:
                    _summary_snippet_inner = (str(summary) if summary is not None else "")[:200]
                    # "'coroutine' object is not callable" = Instructor/Cognee call litellm.acompletion then something calls the result without await (known Instructor/litellm async mismatch).
                    if "coroutine" in (summary or "").lower() and "not callable" in (summary or "").lower():
                        logger.warning(
                            "Cognee memory add: step=cognify_failed dataset={} exc={} summary={}. "
                            "Async/coroutine bug in Instructor/Cognee with litellm (acompletion called without await). "
                            "Patch is applied at memory package load; if this persists, enable DEBUG and check traceback. "
                            "Optional: set cognee.llm_fallback in memory_kb.yml for cloud retry. Memory add skipped; chat and tools are unaffected.".format(
                                dataset, exc_type, _summary_snippet_inner
                            )
                        )
                    else:
                        logger.warning(
                            "Cognee memory add: step={}_failed dataset={} exc={} summary={}. Memory add skipped; chat and tools are unaffected.".format(
                                step_failed, dataset, exc_type, _summary_snippet_inner
                            )
                        )
                    if is_template_error and not self._cognify_llm_fallback:
                        logger.warning(
                            "Cognee: cognify failed (template/local LLM). Set cognee.llm_fallback in memory_kb.yml to a cloud endpoint to retry automatically, or set cognee.llm to cloud. See docs_design/MemorySystemSummary.md §9."
                        )
            if cognify_ok:
                self._datasets_with_graph.add(dataset)
                _save_cognee_graph_dataset(dataset)
                logger.info("Cognee memory add: success dataset={} (add + cognify completed)", dataset)
        except Exception as e:
            exc_type = type(e).__name__
            msg = str(e).strip()
            if len(msg) > 400 or "<failed_attempts>" in msg:
                if "<last_exception>" in msg:
                    m = re.search(r"<last_exception>\s*(.+?)\s*</last_exception>", msg, re.DOTALL)
                    summary = (m.group(1).strip()[:300] if m else None) or "Instructor/cognify error"
                else:
                    first = msg.split("\n")[0].strip()
                    summary = first[:300] if first else "Cognify failed"
                summary = summary or "Cognee add/cognify error"
            else:
                summary = msg or "Cognee add/cognify error"
            try:
                tb_str = "".join(traceback.format_exception(type(e), e, getattr(e, "__traceback__", None)))
                _tb_msg = "Cognee memory add failure (full traceback):\n" + (tb_str or "(no traceback)")
                logger.debug(_tb_msg)
                # Also write to stderr so traceback is visible even if log layer drops or mangles the message
                try:
                    sys.stderr.write(_tb_msg)
                    if not _tb_msg.endswith("\n"):
                        sys.stderr.write("\n")
                    sys.stderr.flush()
                except Exception:
                    pass
            except Exception:
                pass
            msg_lower = msg.lower()
            summary_lower = (summary or "").lower()
            # Exception may come from add() if Cognee runs LLM/template code inside add(); still treat as cognify when it's template/Instructor/litellm
            step_failed = "cognify" if (
                exc_type == "InstructorRetryException"
                or "cognify" in msg_lower
                or "instructor" in msg_lower
                or "template" in msg_lower
                or "litellm" in msg_lower
                or "raise_exception" in msg_lower
                or "jinja" in summary_lower
                or "system me" in summary_lower
                or "internalservererror" in msg_lower
            ) else "add"
            _summary_snippet = (str(summary) if summary is not None else "")[:200]
            if "coroutine" in (summary or "").lower() and "not callable" in (summary or "").lower():
                _warn_msg = (
                    "Cognee memory add: step=cognify_failed dataset={} exc={} summary={}. "
                    "Async/coroutine bug in Instructor/Cognee with litellm. Enable DEBUG for traceback. "
                    "Optional: set cognee.llm_fallback for cloud retry. Memory add skipped; chat and tools are unaffected."
                ).format(dataset, exc_type, _summary_snippet)
                logger.warning(_warn_msg)
            else:
                _warn_msg = (
                    "Cognee memory add: step={}_failed dataset={} exc={} summary={}. Memory add skipped; chat and tools are unaffected."
                ).format(step_failed, dataset, exc_type, _summary_snippet)
                logger.warning(_warn_msg)
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
        logger.debug("Cognee memory search: step=start dataset={} query_len={}", dataset, len(query or ""))
        # Avoid calling Cognee search when dataset doesn't exist or has never had a successful cognify (avoids "Search attempt on an empty knowledge graph"). Persisted set so we skip correctly after restart.
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
                    logger.debug("Cognee memory search: step=skip dataset not in list dataset={}", dataset)
                    return []
                if dataset not in self._datasets_with_graph:
                    logger.debug("Cognee memory search: step=skip no graph yet dataset={}", dataset)
                    return []
            except asyncio.TimeoutError:
                logger.debug("Cognee memory search: step=list_datasets timeout dataset={}", dataset)
            except Exception as e:
                logger.debug("Cognee memory search: step=list_datasets error dataset={} exc={}", dataset, type(e).__name__)
        try:
            results = await self._cognee.search(query, datasets=[dataset], top_k=limit or 10)
            logger.debug("Cognee memory search: step=search_ok dataset={} results={}", dataset, len(results) if isinstance(results, list) else 1)
        except Exception as e:
            # Empty graph can cause Cognee to log "No nodes found" / EntityNotFoundError; we return [] and continue
            logger.debug("Cognee memory search: step=search_failed dataset={} exc={} msg={}", dataset, type(e).__name__, str(e)[:150])
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
