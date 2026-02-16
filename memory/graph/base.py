"""
Graph store abstraction for memory upgrade (Cognee-like layer).
Default: Kuzu (file-based). Optional: Neo4j.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class GraphStoreBase(ABC):
    """Abstract graph store: nodes (e.g. entities) and edges (relationships)."""

    @abstractmethod
    def init_schema(self) -> None:
        """Create node/edge types if needed. Idempotent."""
        pass

    @abstractmethod
    def add_node(self, node_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Add or merge a node. label e.g. 'Entity'; properties e.g. {name, type}."""
        pass

    @abstractmethod
    def add_edge(self, from_id: str, to_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        """Add an edge between two nodes. label e.g. 'RELATES_TO'."""
        pass

    @abstractmethod
    def get_neighbors(self, node_id: str, edge_label: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Return neighbor nodes (and edge props) for a node. Used for graph-aware search."""
        pass

    @abstractmethod
    def get_nodes_by_memory_id(self, memory_id: str) -> List[str]:
        """Return entity node ids that reference this memory_id (for graph-aware search expansion)."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Drop all data (for tests or full reset)."""
        pass

    def close(self) -> None:
        """Release resources. Override if needed."""
        pass
