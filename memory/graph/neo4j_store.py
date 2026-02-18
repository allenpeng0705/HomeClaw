"""
Neo4j graph store: enterprise / multi-process. Optional dependency.
"""
import json
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.graph.base import GraphStoreBase

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None  # type: ignore


class Neo4jStore(GraphStoreBase):
    """Neo4j-backed graph store. Uses Entity nodes and RELATES_TO relationships."""

    def __init__(self, url: str = "bolt://localhost:7687", username: str = "neo4j", password: str = ""):
        if GraphDatabase is None:
            raise ImportError("Neo4j graph store requires the 'neo4j' package. Install with: pip install neo4j")
        self._url = (url or "bolt://localhost:7687").strip()
        self._username = (username or "neo4j").strip()
        self._password = (password or "").strip()
        self._driver = None

    def _driver_session(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._url,
                auth=(self._username, self._password),
            )
        return self._driver

    def init_schema(self) -> None:
        try:
            driver = self._driver_session()
            with driver.session() as session:
                session.run(
                    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE"
                )
        except Exception as e:
            if "equivalent" not in str(e).lower() and "already exists" not in str(e).lower():
                logger.debug("Neo4j init_schema: {}", e)

    def add_node(self, node_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        props = properties or {}
        name = props.get("name", node_id)
        typ = props.get("type", "")
        memory_id = props.get("memory_id", "")
        try:
            driver = self._driver_session()
            with driver.session() as session:
                session.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name, e.type = $type, e.memory_id = $memory_id
                    """,
                    id=node_id,
                    name=name,
                    type=typ,
                    memory_id=memory_id,
                )
        except Exception as e:
            logger.debug("Neo4j add_node: {}", e)

    def add_edge(self, from_id: str, to_id: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
        props_str = json.dumps(properties or {})
        try:
            driver = self._driver_session()
            with driver.session() as session:
                session.run(
                    """
                    MATCH (a:Entity {id: $from_id})
                    MATCH (b:Entity {id: $to_id})
                    MERGE (a)-[r:RELATES_TO]->(b)
                    SET r.label = $label, r.properties = $props
                    """,
                    from_id=from_id,
                    to_id=to_id,
                    label=label,
                    props=props_str,
                )
        except Exception as e:
            logger.debug("Neo4j add_edge: {}", e)

    def get_neighbors(self, node_id: str, edge_label: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            driver = self._driver_session()
            with driver.session() as session:
                if edge_label:
                    result = session.run(
                        """
                        MATCH (a:Entity {id: $id})-[r:RELATES_TO]->(b:Entity)
                        WHERE r.label = $label
                        RETURN b.id AS id, b.name AS name, b.type AS type, b.memory_id AS memory_id
                        LIMIT $limit
                        """,
                        id=node_id,
                        label=edge_label,
                        limit=limit,
                    )
                else:
                    result = session.run(
                        """
                        MATCH (a:Entity {id: $id})-[r:RELATES_TO]->(b:Entity)
                        RETURN b.id AS id, b.name AS name, b.type AS type, b.memory_id AS memory_id
                        LIMIT $limit
                        """,
                        id=node_id,
                        limit=limit,
                    )
                return [dict(record) for record in result]
        except Exception as e:
            logger.debug("Neo4j get_neighbors: {}", e)
            return []

    def get_nodes_by_memory_id(self, memory_id: str) -> List[str]:
        if not (memory_id or "").strip():
            return []
        try:
            driver = self._driver_session()
            with driver.session() as session:
                result = session.run(
                    "MATCH (e:Entity {memory_id: $mid}) RETURN e.id AS id",
                    mid=memory_id.strip(),
                )
                return [str(record["id"]) for record in result if record.get("id")]
        except Exception as e:
            logger.debug("Neo4j get_nodes_by_memory_id: {}", e)
            return []

    def reset(self) -> None:
        try:
            if self._driver:
                with self._driver.session() as session:
                    session.run("MATCH (a)-[r:RELATES_TO]->() DELETE r")
                    session.run("MATCH (e:Entity) DELETE e")
        except Exception as e:
            logger.debug("Neo4j reset: {}", e)
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
        self._driver = None

    def close(self) -> None:
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
        self._driver = None
