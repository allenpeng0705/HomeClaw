"""
Graph store layer for memory upgrade (Cognee-like). Default: Kuzu. Optional: Neo4j.
When graph is disabled or kuzu not installed, get_graph_store returns a no-op store.
"""
from typing import Any, Optional

from memory.graph.base import GraphStoreBase
from memory.graph.null_store import NullGraphStore


def get_graph_store(
    backend: str = "kuzu",
    path: str = "",
    neo4j_url: str = "",
    neo4j_username: str = "",
    neo4j_password: str = "",
) -> GraphStoreBase:
    """
    Return a graph store instance. backend in ('kuzu', 'neo4j').
    path: used for Kuzu (directory). neo4j_* used when backend is neo4j.
    Returns NullGraphStore if backend is disabled or implementation unavailable.
    """
    backend = (backend or "kuzu").strip().lower()
    if backend == "neo4j":
        try:
            from memory.graph.neo4j_store import Neo4jStore
            return Neo4jStore(
                url=neo4j_url or "bolt://localhost:7687",
                username=neo4j_username or "neo4j",
                password=neo4j_password or "",
            )
        except (ImportError, OSError):
            return NullGraphStore()
    if backend != "kuzu":
        return NullGraphStore()
    try:
        from memory.graph.kuzu_store import KuzuStore
        return KuzuStore(path=path)
    except (ImportError, OSError):
        return NullGraphStore()
