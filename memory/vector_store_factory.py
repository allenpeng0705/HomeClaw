"""
Vector store factory: create VectorStoreBase from core.yml vectorDB.backend and config.
Supports: chroma (default), qdrant, milvus, pinecone, weaviate.
"""
from typing import Any, Dict, Optional

from memory.base import VectorStoreBase
from loguru import logger


def create_vector_store(
    backend: str,
    config: Dict[str, Any],
    collection_name: str,
    chroma_client=None,
) -> VectorStoreBase:
    """
    Create a vector store from config.
    :param backend: chroma | qdrant | milvus | pinecone | weaviate
    :param config: full vectorDB section (with Chroma, Qdrant, etc.)
    :param collection_name: collection name (e.g. "memory")
    :param chroma_client: optional existing Chroma client (only for backend=chroma)
    """
    backend = (backend or "chroma").lower()
    if backend == "chroma":
        return _create_chroma(config.get("Chroma") or {}, collection_name, chroma_client)
    if backend == "qdrant":
        return _create_qdrant(config.get("Qdrant") or {}, collection_name)
    if backend == "milvus":
        return _create_milvus(config.get("Milvus") or {}, collection_name)
    if backend == "pinecone":
        return _create_pinecone(config.get("Pinecone") or {}, collection_name)
    if backend == "weaviate":
        return _create_weaviate(config.get("Weaviate") or {}, collection_name)
    logger.warning(f"Unknown vectorDB backend '{backend}', falling back to chroma")
    return _create_chroma(config.get("Chroma") or {}, collection_name, chroma_client)


def _create_chroma(
    cfg: Dict[str, Any],
    collection_name: str,
    client=None,
) -> VectorStoreBase:
    from memory import chroma
    from base.util import Util

    host = cfg.get("host") or None
    port = cfg.get("port") or None
    path = (cfg.get("path") or "").strip()
    if not path:
        path = Util().data_path()
    if client is not None:
        return chroma.ChromaDB(
            collection_name=collection_name,
            client=client,
            host=None,
            port=None,
            path=None,
        )
    return chroma.ChromaDB(
        collection_name=collection_name,
        client=None,
        host=host,
        port=port,
        path=path,
    )


def _create_qdrant(cfg: Dict[str, Any], collection_name: str) -> VectorStoreBase:
    try:
        from memory.vector_stores.qdrant_store import QdrantStore
    except ImportError as e:
        logger.error("Qdrant store not available: %s. Install: pip install qdrant-client", e)
        raise
    url = (cfg.get("url") or "").strip()
    if not url:
        host = (cfg.get("host") or "localhost").strip()
        port = int(cfg.get("port") or 6333)
        url = f"http://{host}:{port}"
    api_key = (cfg.get("api_key") or "").strip() or None
    return QdrantStore(collection_name=collection_name, url=url, api_key=api_key)


def _create_milvus(cfg: Dict[str, Any], collection_name: str) -> VectorStoreBase:
    try:
        from memory.vector_stores.milvus_store import MilvusStore
    except ImportError as e:
        logger.error("Milvus store not available: %s. Install: pip install pymilvus", e)
        raise
    uri = (cfg.get("uri") or "").strip()
    if not uri:
        host = (cfg.get("host") or "localhost").strip()
        port = int(cfg.get("port") or 19530)
        uri = f"http://{host}:{port}"
    return MilvusStore(collection_name=collection_name, uri=uri)


def _create_pinecone(cfg: Dict[str, Any], collection_name: str) -> VectorStoreBase:
    try:
        from memory.vector_stores.pinecone_store import PineconeStore
    except ImportError as e:
        logger.error("Pinecone store not available: %s. Install: pip install pinecone-client", e)
        raise
    api_key = (cfg.get("api_key") or "").strip()
    environment = (cfg.get("environment") or "").strip()
    index_name = (cfg.get("index_name") or collection_name).strip()
    return PineconeStore(
        collection_name=collection_name,
        api_key=api_key,
        environment=environment,
        index_name=index_name,
    )


def _create_weaviate(cfg: Dict[str, Any], collection_name: str) -> VectorStoreBase:
    try:
        from memory.vector_stores.weaviate_store import WeaviateStore
    except ImportError as e:
        logger.error("Weaviate store not available: %s. Install: pip install weaviate-client", e)
        raise
    url = (cfg.get("url") or "http://localhost:8080").strip()
    api_key = (cfg.get("api_key") or "").strip() or None
    return WeaviateStore(collection_name=collection_name, url=url, api_key=api_key)
