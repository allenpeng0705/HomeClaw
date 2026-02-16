"""
Kuzu graph store: file-based, no extra service. Optional dependency.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.graph.base import GraphStoreBase

try:
    import kuzu
except ImportError:
    kuzu = None  # type: ignore


class KuzuStore(GraphStoreBase):
    """Kuzu-backed graph store. Uses a single file directory."""

    def __init__(self, path: str = ""):
        if kuzu is None:
            raise ImportError("Kuzu graph store requires the 'kuzu' package. Install with: pip install kuzu")
        self._path = path
        self._db: Optional[Any] = None
        self._conn: Optional[Any] = None

    def _ensure_db(self) -> None:
        if self._db is not None:
            return
        p = (self._path or "").strip()
        if not p:
            from base.util import Util
            data_path = getattr(Util(), "data_path", lambda: "database")()
            if callable(data_path):
                data_path = data_path()
            p = str(Path(data_path) / "graph_kuzu")
        Path(p).mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(p)
        self._conn = kuzu.Connection(self._db)
        self.init_schema()

    def init_schema(self) -> None:
        self._ensure_db()
        # Minimal schema: Entity nodes, RELATES_TO edges. Extend as needed in Step 2.
        try:
            self._conn.execute(
                "CREATE NODE TABLE Entity(id STRING, name STRING, type STRING, memory_id STRING, PRIMARY KEY(id))"
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.debug("Kuzu create Entity: %s", e)
        try:
            self._conn.execute(
                "CREATE REL TABLE RELATES_TO(FROM Entity TO Entity, label STRING, properties STRING)"
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.debug("Kuzu create RELATES_TO: %s", e)

    def add_node(self, node_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        self._ensure_db()
        props = properties or {}
        name = props.get("name", node_id)
        typ = props.get("type", "")
        memory_id = props.get("memory_id", "")
        try:
            self._conn.execute(
                "MERGE (e:Entity {id: $id}) ON CREATE SET e.name = $name, e.type = $type, e.memory_id = $memory_id "
                "ON MATCH SET e.name = $name, e.type = $type, e.memory_id = $memory_id",
                parameters={"id": node_id, "name": name, "type": typ, "memory_id": memory_id},
            )
        except Exception as e:
            logger.debug("Kuzu add_node: %s", e)

    def add_edge(self, from_id: str, to_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        self._ensure_db()
        import json
        props_str = json.dumps(properties or {})
        try:
            self._conn.execute(
                "MATCH (a:Entity {id: $from_id}) MATCH (b:Entity {id: $to_id}) "
                "MERGE (a)-[r:RELATES_TO {label: $label, properties: $props}]->(b)",
                parameters={"from_id": from_id, "to_id": to_id, "label": label, "props": props_str},
            )
        except Exception as e:
            logger.debug("Kuzu add_edge: %s", e)

    def get_neighbors(self, node_id: str, edge_label: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_db()
        try:
            if edge_label:
                result = self._conn.execute(
                    "MATCH (a:Entity {id: $id})-[r:RELATES_TO]->(b:Entity) WHERE r.label = $label "
                    "RETURN b.id, b.name, b.type, b.memory_id LIMIT $limit",
                    parameters={"id": node_id, "label": edge_label, "limit": limit},
                )
            else:
                result = self._conn.execute(
                    "MATCH (a:Entity {id: $id})-[r:RELATES_TO]->(b:Entity) "
                    "RETURN b.id, b.name, b.type, b.memory_id LIMIT $limit",
                    parameters={"id": node_id, "limit": limit},
                )
            rows = result.get_as_df()
            out = []
            for _, row in rows.iterrows():
                out.append({
                    "id": row.get("b.id"),
                    "name": row.get("b.name"),
                    "type": row.get("b.type"),
                    "memory_id": row.get("b.memory_id"),
                })
            return out
        except Exception as e:
            logger.debug("Kuzu get_neighbors: %s", e)
            return []

    def get_nodes_by_memory_id(self, memory_id: str) -> List[str]:
        self._ensure_db()
        if not (memory_id or "").strip():
            return []
        try:
            result = self._conn.execute(
                "MATCH (e:Entity) WHERE e.memory_id = $mid RETURN e.id",
                parameters={"mid": memory_id.strip()},
            )
            rows = result.get_as_df()
            return [str(row.get("e.id")) for _, row in rows.iterrows() if row.get("e.id")]
        except Exception as e:
            logger.debug("Kuzu get_nodes_by_memory_id: %s", e)
            return []

    def reset(self) -> None:
        try:
            if self._conn:
                self._conn.execute("DROP TABLE IF EXISTS RELATES_TO")
                self._conn.execute("DROP TABLE IF EXISTS Entity")
            self._db = None
            self._conn = None
        except Exception as e:
            logger.debug("Kuzu reset: %s", e)
        self._db = None
        self._conn = None
