"""
No-op graph store when graph is disabled or Kuzu/Neo4j not available.
"""
from typing import Any, Dict, List, Optional

from memory.graph.base import GraphStoreBase


class NullGraphStore(GraphStoreBase):
    """Graph store that does nothing. Used when graphDB is disabled or backend unavailable."""

    def init_schema(self) -> None:
        pass

    def add_node(self, node_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        pass

    def add_edge(self, from_id: str, to_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        pass

    def get_neighbors(self, node_id: str, edge_label: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return []

    def get_nodes_by_memory_id(self, memory_id: str) -> List[str]:
        return []

    def reset(self) -> None:
        pass
