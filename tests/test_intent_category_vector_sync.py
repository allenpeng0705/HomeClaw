"""Incremental sync for intent category docs into the vector store (state file + skip unchanged)."""

from pathlib import Path

import pytest

from base.intent_category_router import (
    clear_intent_category_manifest_cache,
    load_intent_category_docs,
    sync_intent_categories_to_vector_store,
)


class _FakeEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, text: str):
        self.calls += 1
        return [0.01] * 8


class _FakeVectorStore:
    """Non-Chroma: batch insert overwrites like Qdrant."""

    def __init__(self) -> None:
        self.by_id: dict = {}

    def insert(self, vectors=None, ids=None, payloads=None):
        for i, vid in enumerate(ids or []):
            self.by_id[vid] = {"v": vectors[i], "p": payloads[i]}

    def get(self, vector_id: str):
        return self.by_id.get(vector_id)

    def update(self, vector_id: str, vector=None, payload=None):
        self.by_id[vector_id] = {"v": vector, "p": payload}

    def delete(self, vector_id: str):
        self.by_id.pop(vector_id, None)


@pytest.mark.asyncio
async def test_incremental_sync_skips_second_run_when_unchanged(tmp_path: Path):
    clear_intent_category_manifest_cache()
    cat_dir = tmp_path / "intent_category"
    cat_dir.mkdir()
    (cat_dir / "alpha.md").write_text(
        "---\nid: alpha\npriority: 50\n---\n\n## Description\nOne.\n",
        encoding="utf-8",
    )
    state = tmp_path / "intent_category_vector_sync.json"
    emb = _FakeEmbedder()
    vs = _FakeVectorStore()

    docs = load_intent_category_docs(cat_dir)
    assert len(docs) == 1

    n1 = await sync_intent_categories_to_vector_store(
        cat_dir,
        vs,
        emb,
        incremental=True,
        state_path=state,
    )
    assert n1 == 1
    assert emb.calls == 1
    assert "alpha" in vs.by_id

    n2 = await sync_intent_categories_to_vector_store(
        cat_dir,
        vs,
        emb,
        incremental=True,
        state_path=state,
    )
    assert n2 == 0
    assert emb.calls == 1


@pytest.mark.asyncio
async def test_incremental_sync_reembeds_after_file_touch(tmp_path: Path):
    clear_intent_category_manifest_cache()
    cat_dir = tmp_path / "intent_category"
    cat_dir.mkdir()
    p = cat_dir / "beta.md"
    p.write_text(
        "---\nid: beta\npriority: 50\n---\n\n## Description\nFirst.\n",
        encoding="utf-8",
    )
    state = tmp_path / "intent_category_vector_sync.json"
    emb = _FakeEmbedder()
    vs = _FakeVectorStore()

    await sync_intent_categories_to_vector_store(cat_dir, vs, emb, incremental=True, state_path=state)
    assert emb.calls == 1

    p.write_text(
        "---\nid: beta\npriority: 50\n---\n\n## Description\nSecond.\n",
        encoding="utf-8",
    )
    n = await sync_intent_categories_to_vector_store(cat_dir, vs, emb, incremental=True, state_path=state)
    assert n == 1
    assert emb.calls == 2


@pytest.mark.asyncio
async def test_incremental_removes_deleted_category_from_store(tmp_path: Path):
    clear_intent_category_manifest_cache()
    cat_dir = tmp_path / "intent_category"
    cat_dir.mkdir()
    (cat_dir / "gone.md").write_text(
        "---\nid: gone\npriority: 50\n---\n\n## Description\nX.\n",
        encoding="utf-8",
    )
    state = tmp_path / "intent_category_vector_sync.json"
    emb = _FakeEmbedder()
    vs = _FakeVectorStore()

    await sync_intent_categories_to_vector_store(cat_dir, vs, emb, incremental=True, state_path=state)
    assert "gone" in vs.by_id

    (cat_dir / "gone.md").unlink()
    n = await sync_intent_categories_to_vector_store(cat_dir, vs, emb, incremental=True, state_path=state)
    assert n == 0
    assert "gone" not in vs.by_id
