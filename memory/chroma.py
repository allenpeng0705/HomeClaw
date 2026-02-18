from typing import Optional, List, Dict

from pydantic import BaseModel
from loguru import logger

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    raise ImportError(
        "Chromadb requires extra dependencies. Install with `pip install chromadb`"
    ) from None

from memory.base import VectorStoreBase


class OutputData(BaseModel):
    id: Optional[str]  # memory id
    score: Optional[float]  # distance
    payload: Optional[Dict]  # metadata


class ChromaDB(VectorStoreBase):
    def __init__(
        self,
        collection_name: str,
        client: Optional[chromadb.Client] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
    ):
        """
        Initialize the Chromadb vector store.

        Args:
            collection_name (str): Name of the collection.
            client (chromadb.Client, optional): Existing chromadb client instance. Defaults to None.
            host (str, optional): Host address for chromadb server. Defaults to None.
            port (int, optional): Port for chromadb server. Defaults to None.
            path (str, optional): Path for local chromadb database. Defaults to None.
        """
        super().__init__(collection_name=collection_name)
        if client:
            self.client = client
        else:
            self.settings = Settings(anonymized_telemetry=False)

            if host and port:
                self.settings.chroma_server_host = host
                self.settings.chroma_server_http_port = port
                self.settings.chroma_api_impl = "chromadb.api.fastapi.FastAPI"
            else:
                if path is None:
                    path = "db"

            self.settings.persist_directory = path
            self.settings.is_persistent = True
            logger.debug(f"ChromaDB client created")

            self.client = chromadb.Client(self.settings)

        #col_name = self.create_col(name=collection_name)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def _parse_output(self, data: Dict) -> List[OutputData]:
        """
        Parse the output data.

        Args:
            data (Dict): Output data.

        Returns:
            List[OutputData]: Parsed output data.
        """
        keys = ["ids", "distances", "metadatas"]
        values = []

        for key in keys:
            value = data.get(key, [])
            if isinstance(value, list) and value and isinstance(value[0], list):
                value = value[0]
            values.append(value)

        ids, distances, metadatas = values
        max_length = max(
            len(v) for v in values if isinstance(v, list) and v is not None
        )

        result = []
        for i in range(max_length):
            entry = OutputData(
                id=ids[i] if isinstance(ids, list) and ids and i < len(ids) else None,
                score=(
                    distances[i]
                    if isinstance(distances, list) and distances and i < len(distances)
                    else None
                ),
                payload=(
                    metadatas[i]
                    if isinstance(metadatas, list) and metadatas and i < len(metadatas)
                    else None
                ),
            )
            result.append(entry)

        return result

    def create_col(self, name: str, embedding_fn: Optional[callable] = None):
        """
        Create a new collection.

        Args:
            name (str): Name of the collection.
            embedding_fn (Optional[callable]): Embedding function to use. Defaults to None.

        Returns:
            chromadb.Collection: The created or retrieved collection.
        """
        # Skip creating collection if already exists
        collections = self.list_cols()
        for collection in collections:
            if collection == name:
                logger.debug(f"Collection {name} already exists. Skipping creation.")
                return self.client.get_collection(name=name)

        collection = self.client.get_or_create_collection(
            name=name,
            embedding_function=embedding_fn,
            # defult is L2 distance function, I change to cosine and see the result
            metadata={"hnsw:space": "cosine"},
        )
        return collection

    def insert(
        self,
        vectors: List[list],
        payloads: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ):
        """
        Insert vectors into a collection.

        Args:
            vectors (List[list]): List of vectors to insert.
            payloads (Optional[List[Dict]], optional): List of payloads corresponding to vectors. Defaults to None.
            ids (Optional[List[str]], optional): List of IDs corresponding to vectors. Defaults to None.
        """
        self.collection.add(ids=ids, embeddings=vectors, metadatas=payloads)

    def search(
        self, query: List[list], limit: int = 5, filters: Optional[Dict] = None
    ) -> List[OutputData]:
        """
        Search for similar vectors.

        Args:
            query (List[list]): Query vector.
            limit (int, optional): Number of results to return. Defaults to 5.
            filters (Optional[Dict], optional): Filters to apply to the search. Defaults to None.

        Returns:
            List[OutputData]: Search results.
        """
        kwargs = {"query_embeddings": query, "n_results": limit}
        if filters and len(filters) > 0:
            kwargs["where"] = {"$and": [{k: v} for k, v in filters.items()]}
        results = self.collection.query(**kwargs)
        final_results = self._parse_output(results)
        return final_results

    def delete(self, vector_id: str):
        """
        Delete a vector by ID.

        Args:
            vector_id (str): ID of the vector to delete.
        """
        self.collection.delete(ids=vector_id)

    def delete_where(self, where: Dict):
        """
        Delete all vectors matching the metadata where clause (e.g. {"source_id": "x", "user_id": "y"}).
        Uses Chroma's native where filter so no need to fetch ids first.
        """
        self.collection.delete(where=where)

    def get_all_ids(self, limit: int = 10000) -> List[str]:
        """Get up to `limit` vector ids from the collection (for reset/clear-all)."""
        result = self.collection.get(limit=limit, include=[])
        ids = result.get("ids") or []
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        return list(ids) if ids else []

    def delete_ids(self, ids: List[str]) -> None:
        """Delete multiple vectors by id."""
        if ids:
            self.collection.delete(ids=ids)

    def get_where(self, where: Dict, limit: int = 10000, include_metadatas: bool = True):
        """
        Get ids and metadatas for all vectors matching the where clause.
        Returns list of (id, metadata_dict). Used e.g. for cleanup (find chunks by last_used_timestamp).
        """
        include = ["metadatas"] if include_metadatas else []
        result = self.collection.get(where=where, limit=limit, include=include or [])
        ids = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        if isinstance(metadatas, list) and metadatas and isinstance(metadatas[0], list):
            metadatas = metadatas[0]
        return list(zip(ids, metadatas)) if ids else []

    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict] = None,
    ):
        """
        Update a vector and its payload.

        Args:
            vector_id (str): ID of the vector to update.
            vector (Optional[List[float]], optional): Updated vector. Defaults to None.
            payload (Optional[Dict], optional): Updated payload. Defaults to None.
        """
        self.collection.update(ids=vector_id, embeddings=vector, metadatas=payload)

    def get(self, vector_id: str) -> OutputData | None:
        """
        Retrieve a vector by ID.

        Args:
            vector_id (str): ID of the vector to retrieve.

        Returns:
            OutputData: Retrieved vector.
        """
        result = self.collection.get(ids=[vector_id])
        if result.get('ids', []) == [] or result is None:
            return None
        return self._parse_output(result)[0]

    def list_cols(self) -> List[chromadb.Collection]:
        """
        List all collections.

        Returns:
            List[chromadb.Collection]: List of collections.
        """
        return self.client.list_collections()

    def delete_col(self):
        """
        Delete a collection.
        """
        self.client.delete_collection(name=self.collection_name)

    def col_info(self) -> Dict:
        """
        Get information about a collection.

        Returns:
            Dict: Collection information.
        """
        return self.client.get_collection(name=self.collection_name)

    def list(
        self, filters: Optional[Dict] = None, limit: int = 100
    ) -> List[OutputData]:
        """
        List all vectors in a collection.

        Args:
            filters (Optional[Dict], optional): Filters to apply to the list. Defaults to None.
            limit (int, optional): Number of vectors to return. Defaults to 100.

        Returns:
            List[OutputData]: List of vectors.
        """
        results = self.collection.get(where=filters, limit=limit)
        return [self._parse_output(results)]

    def list_ids(self, limit: int = 10000) -> List[str]:
        """
        Return all document ids in the collection (up to limit). Used e.g. to find stale test skill ids.
        """
        result = self.collection.get(limit=limit, include=[])
        ids = result.get("ids") or []
        if isinstance(ids, list) and ids and isinstance(ids[0], list):
            ids = ids[0]
        return [str(i) for i in ids] if ids else []
