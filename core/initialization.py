"""
Core initialization: vector stores, embedder, knowledge base, and memory backend.
Extracted from core/core.py (Phase 3 refactor). All functions take core as first argument; no import of core.core.
"""

from typing import Any, Dict

from loguru import logger

from base.util import Util
from memory.embedding import LlamaCppEmbedding
from memory.llm import LlamaCppLLM
from memory.mem import Memory


def _create_skills_vector_store(core: Any) -> None:
    """Create a dedicated vector store for skills (separate collection from memory). Used when skills_use_vector_search."""
    from memory.vector_store_factory import create_vector_store

    meta = Util().get_core_metadata()
    if not getattr(meta, "skills_use_vector_search", False):
        return
    vdb = meta.vectorDB
    backend = getattr(vdb, "backend", "chroma") or "chroma"
    config = {
        "backend": backend,
        "Chroma": vars(vdb.Chroma),
        "Qdrant": vars(vdb.Qdrant),
        "Milvus": vars(vdb.Milvus),
        "Pinecone": vars(vdb.Pinecone),
        "Weaviate": vars(vdb.Weaviate),
    }
    chroma_client = getattr(core, "chromra_memory_client", None) if backend == "chroma" else None
    core.skills_vector_store = create_vector_store(
        backend=backend,
        config=config,
        collection_name=getattr(meta, "skills_vector_collection", "homeclaw_skills") or "homeclaw_skills",
        chroma_client=chroma_client,
    )


def _create_plugins_vector_store(core: Any) -> None:
    """Create a dedicated vector store for plugins (separate collection). Used when plugins_use_vector_search."""
    from memory.vector_store_factory import create_vector_store

    meta = Util().get_core_metadata()
    if not getattr(meta, "plugins_use_vector_search", False):
        return
    vdb = meta.vectorDB
    backend = getattr(vdb, "backend", "chroma") or "chroma"
    config = {
        "backend": backend,
        "Chroma": vars(vdb.Chroma),
        "Qdrant": vars(vdb.Qdrant),
        "Milvus": vars(vdb.Milvus),
        "Pinecone": vars(vdb.Pinecone),
        "Weaviate": vars(vdb.Weaviate),
    }
    chroma_client = getattr(core, "chromra_memory_client", None) if backend == "chroma" else None
    core.plugins_vector_store = create_vector_store(
        backend=backend,
        config=config,
        collection_name=getattr(meta, "plugins_vector_collection", "homeclaw_plugins") or "homeclaw_plugins",
        chroma_client=chroma_client,
    )


def _create_agent_memory_vector_store(core: Any) -> None:
    """Create vector store for AGENT_MEMORY + daily memory when use_agent_memory_search. Never raises; on failure sets agent_memory_vector_store to None."""
    meta = Util().get_core_metadata()
    if not getattr(meta, "use_agent_memory_search", True):
        return
    try:
        from memory.vector_store_factory import create_vector_store

        vdb = getattr(meta, "vectorDB", None)
        if vdb is None:
            logger.warning("Agent memory vector store: vectorDB not configured; skipping.")
            return
        backend = getattr(vdb, "backend", "chroma") or "chroma"
        config = {
            "backend": backend,
            "Chroma": vars(getattr(vdb, "Chroma", None) or {}),
            "Qdrant": vars(getattr(vdb, "Qdrant", None) or {}),
            "Milvus": vars(getattr(vdb, "Milvus", None) or {}),
            "Pinecone": vars(getattr(vdb, "Pinecone", None) or {}),
            "Weaviate": vars(getattr(vdb, "Weaviate", None) or {}),
        }
        chroma_client = getattr(core, "chromra_memory_client", None) if backend == "chroma" else None
        core.agent_memory_vector_store = create_vector_store(
            backend=backend,
            config=config,
            collection_name=getattr(meta, "agent_memory_vector_collection", "homeclaw_agent_memory")
            or "homeclaw_agent_memory",
            chroma_client=chroma_client,
        )
    except Exception as e:
        logger.warning("Agent memory vector store not created: {}", e, exc_info=False)
        core.agent_memory_vector_store = None


def _create_knowledge_base_cognee(core: Any, meta: Any, kb_cfg: Dict[str, Any]) -> None:
    """Create knowledge base using Cognee (same DB/vector as memory when memory_backend is cognee). Never raises."""
    try:
        from memory.cognee_knowledge_base import CogneeKnowledgeBase

        cognee_config = dict(getattr(meta, "cognee", None) or {})
        if not (cognee_config.get("llm") or {}).get("endpoint"):
            resolved = Util().main_llm()
            if resolved:
                _path, _model_id, mtype, host, port = resolved
                if mtype == "litellm":
                    model = _path
                    provider = "openai"
                else:
                    model_id = (_model_id or "local").strip() or "local"
                    model = f"openai/{model_id}"
                    provider = "openai"
                cognee_config.setdefault("llm", {})
                cognee_config["llm"].update(
                    {
                        "provider": (cognee_config["llm"].get("provider") or provider).strip() or provider,
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (cognee_config["llm"].get("model") or model).strip() or model,
                        "api_key": (getattr(meta, "main_llm_api_key", "") or "").strip() or "local",
                    }
                )
        if not (cognee_config.get("embedding") or {}).get("endpoint"):
            resolved = Util().embedding_llm()
            if resolved:
                _path, _model_id, mtype, host, port = resolved
                if mtype == "litellm":
                    model = _path
                    provider = "openai"
                else:
                    model_id = (_model_id or "local").strip() or "local"
                    model = f"openai/{model_id}"
                    provider = "openai"
                cognee_config.setdefault("embedding", {})
                cognee_config["embedding"].update(
                    {
                        "provider": (cognee_config["embedding"].get("provider") or provider).strip() or provider,
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (cognee_config["embedding"].get("model") or model).strip() or model,
                        "api_key": (getattr(meta, "main_llm_api_key", "") or "").strip() or "local",
                    }
                )
        core.knowledge_base = CogneeKnowledgeBase(
            config=cognee_config if cognee_config else None,
            kb_config={
                "unused_ttl_days": float(kb_cfg.get("unused_ttl_days", 30) or 30),
                "max_sources_per_user": int(kb_cfg.get("max_sources_per_user", 0) or 0),
            },
        )
        logger.debug("Knowledge base initialized (Cognee backend)")
    except Exception as e:
        logger.exception("Knowledge base (Cognee) not initialized: {}", e)
        core.knowledge_base = None


def _create_knowledge_base(core: Any) -> None:
    """Create user knowledge base. Backend follows knowledge_base.backend (auto = memory_backend): cognee or chroma (built-in RAG). Never raises."""
    try:
        meta = Util().get_core_metadata()
        kb_cfg = getattr(meta, "knowledge_base", None) or {}
        if not kb_cfg.get("enabled"):
            return
        kb_backend = (kb_cfg.get("backend") or "auto").strip().lower()
        if kb_backend == "auto":
            kb_backend = (getattr(meta, "memory_backend", None) or "cognee").strip().lower()
        if kb_backend == "cognee":
            _create_knowledge_base_cognee(core, meta, kb_cfg)
            return
        from memory.vector_store_factory import create_vector_store
        from memory.knowledge_base import KnowledgeBase

        vdb = getattr(meta, "vectorDB", None)
        if not vdb:
            logger.warning("Knowledge base (chroma) enabled but vectorDB not configured; skipping.")
            return
        backend = getattr(vdb, "backend", "chroma") or "chroma"
        config = {
            "backend": backend,
            "Chroma": vars(getattr(vdb, "Chroma", {})),
            "Qdrant": vars(getattr(vdb, "Qdrant", {})),
            "Milvus": vars(getattr(vdb, "Milvus", {})),
            "Pinecone": vars(getattr(vdb, "Pinecone", {})),
            "Weaviate": vars(getattr(vdb, "Weaviate", {})),
        }
        chroma_client = getattr(core, "chromra_memory_client", None) if backend == "chroma" else None
        kb_store = create_vector_store(
            backend=backend,
            config=config,
            collection_name=(kb_cfg.get("collection_name") or "homeclaw_kb").strip(),
            chroma_client=chroma_client,
        )
        core.knowledge_base = KnowledgeBase(
            vector_store=kb_store,
            embed_fn=core.embedder,
            config={
                "chunk_size": int(kb_cfg.get("chunk_size", 800) or 800),
                "chunk_overlap": int(kb_cfg.get("chunk_overlap", 100) or 100),
                "unused_ttl_days": float(kb_cfg.get("unused_ttl_days", 30) or 30),
                "embed_timeout": float(kb_cfg.get("embed_timeout", 30) or 30),
                "store_timeout": float(kb_cfg.get("store_timeout", 15) or 15),
                "score_is_distance": True,
            },
        )
        logger.debug(
            "Knowledge base initialized (built-in RAG, collection={})",
            kb_cfg.get("collection_name") or "homeclaw_kb",
        )
    except Exception as e:
        logger.warning("Knowledge base not initialized: {}", e)
        core.knowledge_base = None


def run_initialize(core: Any) -> None:
    """
    Perform full Core initialization: vector store, embedder, skills/plugins/agent_memory
    vector stores, knowledge base, and memory backend (Cognee or chroma). Sets attributes on core.
    """
    logger.debug("core initializing...")
    core.initialize_vector_store(collection_name="memory")
    logger.debug("core init: vector_store done")
    core.embedder = LlamaCppEmbedding()
    logger.debug("core init: embedder done")
    meta = Util().get_core_metadata()
    _create_skills_vector_store(core)
    _create_plugins_vector_store(core)
    _create_agent_memory_vector_store(core)
    logger.debug("core init: skills/plugins/agent_memory vector stores done")
    core.knowledge_base = None
    _create_knowledge_base(core)
    logger.debug("core init: knowledge_base done")
    memory_backend = (getattr(meta, "memory_backend", None) or "cognee").strip().lower()

    if memory_backend == "cognee" and Util().has_memory():
        try:
            logger.debug("core init: creating Cognee memory (LLM/embedding must be reachable)...")
            from memory.cognee_adapter import CogneeMemory

            cognee_config = dict(getattr(meta, "cognee", None) or {})
            llm_cfg = cognee_config.get("llm") or {}
            if not isinstance(llm_cfg, dict):
                llm_cfg = {}
            if not (llm_cfg.get("endpoint") or llm_cfg.get("model")):
                resolved = Util().main_llm()
                if resolved:
                    _path, _model_id, mtype, host, port = resolved
                    if mtype == "litellm":
                        model = _path
                        provider = (llm_cfg.get("provider") or "openai").strip() or "openai"
                    else:
                        model_id = (_model_id or "local").strip() or "local"
                        model = f"openai/{model_id}"
                        provider = "openai"
                    cognee_config["llm"] = {
                        **llm_cfg,
                        "provider": (llm_cfg.get("provider") or provider).strip() or provider,
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (llm_cfg.get("model") or model).strip() or model,
                    }
                    cognee_config["llm"]["api_key"] = (
                        (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    )
                else:
                    host = getattr(meta, "main_llm_host", "127.0.0.1") or "127.0.0.1"
                    port = getattr(meta, "main_llm_port", 5088) or 5088
                    main_llm_ref = (getattr(meta, "main_llm", "") or "").strip()
                    model_id = main_llm_ref.split("/")[-1] if "/" in main_llm_ref else (main_llm_ref or "local")
                    if not model_id:
                        model_id = "local"
                    model = f"openai/{model_id}"
                    cognee_config["llm"] = {
                        **llm_cfg,
                        "provider": (llm_cfg.get("provider") or "openai").strip() or "openai",
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (llm_cfg.get("model") or model).strip() or model,
                    }
                    cognee_config["llm"]["api_key"] = (
                        (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    )
            emb_cfg = cognee_config.get("embedding") or {}
            if not isinstance(emb_cfg, dict):
                emb_cfg = {}
            if not (emb_cfg.get("endpoint") or emb_cfg.get("model")):
                resolved = Util().embedding_llm()
                if resolved:
                    _path, _model_id, mtype, host, port = resolved
                    if mtype == "litellm":
                        model = _path
                        provider = (emb_cfg.get("provider") or "openai").strip() or "openai"
                    else:
                        model_id = (_model_id or "local").strip() or "local"
                        model = f"openai/{model_id}"
                        provider = "openai"
                    _emb = {
                        **emb_cfg,
                        "provider": (emb_cfg.get("provider") or provider).strip() or provider,
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (emb_cfg.get("model") or model).strip() or model,
                    }
                    for _tk in ("tokenizer", "huggingface_tokenizer"):
                        if (emb_cfg.get(_tk) or "").strip():
                            _emb[_tk] = (emb_cfg.get(_tk) or "").strip()
                    cognee_config["embedding"] = _emb
                    cognee_config["embedding"]["api_key"] = (
                        (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    )
                else:
                    host = getattr(meta, "embedding_host", "127.0.0.1") or "127.0.0.1"
                    port = getattr(meta, "embedding_port", 5066) or 5066
                    emb_ref = (getattr(meta, "embedding_llm", "") or "").strip()
                    model_id = emb_ref.split("/")[-1] if "/" in emb_ref else (emb_ref or "local")
                    if not model_id:
                        model_id = "local"
                    model = f"openai/{model_id}"
                    _emb = {
                        **emb_cfg,
                        "provider": (emb_cfg.get("provider") or "openai").strip() or "openai",
                        "endpoint": f"http://{host}:{port}/v1",
                        "model": (emb_cfg.get("model") or model).strip() or model,
                    }
                    for _tk in ("tokenizer", "huggingface_tokenizer"):
                        if (emb_cfg.get(_tk) or "").strip():
                            _emb[_tk] = (emb_cfg.get(_tk) or "").strip()
                    cognee_config["embedding"] = _emb
                    cognee_config["embedding"]["api_key"] = (
                        (getattr(meta, "main_llm_api_key", "") or "").strip() or "local"
                    )
            core.mem_instance = CogneeMemory(config=cognee_config if cognee_config else None)
            logger.debug("core init: Cognee memory done")
        except ImportError as e:
            logger.warning("Cognee backend requested but cognee not installed: {}. Using chroma.", e)
            memory_backend = "chroma"
        except Exception as e:
            logger.warning("Cognee backend failed: {}. Using chroma.", e)
            memory_backend = "chroma"

    if memory_backend != "cognee":
        graph_store = None
        if Util().has_memory():
            try:
                from memory.graph import get_graph_store

                gdb = getattr(meta, "graphDB", None)
                if gdb:
                    graph_store = get_graph_store(
                        backend=getattr(gdb, "backend", "kuzu"),
                        path=getattr(gdb.Kuzu, "path", "") or "",
                        neo4j_url=getattr(gdb.Neo4j, "url", "") or "",
                        neo4j_username=getattr(gdb.Neo4j, "username", "") or "",
                        neo4j_password=getattr(gdb.Neo4j, "password", "") or "",
                    )
            except Exception as e:
                logger.debug("Graph store not initialized: {}", e)
        if not getattr(core, "mem_instance", None):
            core.mem_instance = Memory(
                embedding_model=core.embedder,
                vector_store=core.vector_store,
                llm=LlamaCppLLM(),
                graph_store=graph_store,
            )
    logger.debug("core init: memory backend done")
