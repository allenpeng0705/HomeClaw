"""
Qdrant vector store adapter implementing VectorStoreBase.
Requires: pip install qdrant-client
"""
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.base import VectorStoreBase
from memory.chroma import OutputData


def _chroma_filters_to_qdrant(filters: Optional[Dict]):
    """Convert Chroma-style where ($and: [{k: v}]) to Qdrant Filter."""
    if not filters:
        return None
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        must = [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()]
        return Filter(must=must) if must else None
    except ImportError:
        return None


class QdrantStore(VectorStoreBase):
    def __init__(
        self,
        collection_name: str,
        url: str = "http://localhost:6333",
        api_key: Optional[str] = None,
    ):
        super().__init__(collection_name=collection_name)
        self.url = url.rstrip("/")
        self.api_key = api_key
        self._client = None
        self._vector_size: Optional[int] = None

    @property
    def client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(url=self.url, api_key=self.api_key)
            except ImportError as e:
                raise ImportError("Qdrant requires: pip install qdrant-client") from e
        return self._client

    def _ensure_collection(self, vector_size: int):
        from qdrant_client.models import Distance, VectorParams
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            logger.debug(f"Qdrant collection {self.collection_name} created with size={vector_size}")
        self._vector_size = vector_size

    def create_col(self, name: str, vector_size: int = 1024, distance: str = "cosine"):
        from qdrant_client.models import Distance, VectorParams
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        return name

    def insert(
        self,
        vectors: List[list],
        payloads: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ):
        from qdrant_client.models import PointStruct
        if not vectors:
            return
        payloads = payloads or [{}] * len(vectors)
        ids = ids or [str(i) for i in range(len(vectors))]
        self._ensure_collection(len(vectors[0]))
        points = [
            PointStruct(id=id_, vector=vec, payload=payload or {})
            for id_, vec, payload in zip(ids, vectors, payloads)
        ]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def search(
        self,
        query: List[list],
        limit: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[OutputData]:
        q_filter = _chroma_filters_to_qdrant(filters)
        query_vec = query[0] if (query and isinstance(query[0], list)) else query
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vec,
            limit=limit,
            query_filter=q_filter,
        )
        return [
            OutputData(id=str(r.id), score=float(r.score), payload=r.payload or {})
            for r in results
        ]

    def get(self, vector_id: str) -> Optional[OutputData]:
        try:
            records = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[vector_id],
                with_payload=True,
                with_vectors=False,
            )
            if not records:
                return None
            r = records[0]
            return OutputData(id=str(r.id), score=None, payload=r.payload or {})
        except Exception:
            return None

    def list(
        self,
        filters: Optional[Dict] = None,
        limit: int = 100,
    ) -> List[List[OutputData]]:
        """Return [list_of_output_data] to match Chroma interface (Memory uses .list(...)[0])."""
        q_filter = _chroma_filters_to_qdrant(filters)
        results, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=q_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        out = [OutputData(id=str(r.id), score=None, payload=r.payload or {}) for r in results]
        return [out]

    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict] = None,
    ):
        from qdrant_client.models import PointStruct
        if vector is not None and payload is not None:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(id=vector_id, vector=vector, payload=payload)],
            )
        elif payload is not None:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[vector_id],
            )

    def delete(self, vector_id: str):
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=[vector_id],
        )

    def delete_col(self):
        self.client.delete_collection(collection_name=self.collection_name)

    def list_cols(self):
        return [c.name for c in self.client.get_collections().collections]

    def col_info(self, name: str) -> Dict:
        info = self.client.get_collection(name)
        return {"name": info.name, "vectors_count": info.vectors_count}
