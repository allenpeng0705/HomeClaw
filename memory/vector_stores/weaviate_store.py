"""
Weaviate vector store adapter (stub).
Implement VectorStoreBase when ready.
Requires: pip install weaviate-client
Config: vectorDB.backend: weaviate, vectorDB.Weaviate: { url, api_key }
"""
from typing import Dict, List, Optional

from memory.base import VectorStoreBase
from memory.chroma import OutputData

_NOT_IMPL = (
    "Weaviate backend is not implemented yet. "
    "Set vectorDB.backend to 'chroma' or 'qdrant' in core.yml, "
    "or implement memory/vector_stores/weaviate_store.py (see qdrant_store.py)."
)


class WeaviateStore(VectorStoreBase):
    def __init__(self, collection_name: str, url: str = "http://localhost:8080", api_key: Optional[str] = None):
        super().__init__(collection_name=collection_name)
        self.url = url
        self.api_key = api_key

    def create_col(self, name: str, vector_size: int = 1024, distance: str = "cosine"):
        raise NotImplementedError(_NOT_IMPL)

    def insert(self, vectors, payloads=None, ids=None):
        raise NotImplementedError(_NOT_IMPL)

    def search(self, query, limit=5, filters=None):
        raise NotImplementedError(_NOT_IMPL)

    def delete(self, vector_id: str):
        raise NotImplementedError(_NOT_IMPL)

    def update(self, vector_id: str, vector=None, payload=None):
        raise NotImplementedError(_NOT_IMPL)

    def get(self, vector_id: str):
        raise NotImplementedError(_NOT_IMPL)

    def list(self, filters=None, limit=100):
        raise NotImplementedError(_NOT_IMPL)

    def list_cols(self):
        raise NotImplementedError(_NOT_IMPL)

    def delete_col(self):
        raise NotImplementedError(_NOT_IMPL)

    def col_info(self, name):
        raise NotImplementedError(_NOT_IMPL)
