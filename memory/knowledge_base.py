"""
User knowledge base: multi-source (documents, web search, URLs, manual) with chunk, embed, search, and eviction.

- One dedicated collection per deployment (or per user via metadata filter).
- Metadata: user_id, source_type, source_id, added_at, last_used_timestamp, content (chunk text).
- Eviction: last_used_timestamp + configurable unused TTL (delete when not used for X days).
- All operations are wrapped with timeouts and try/except so a broken step never hangs the system.
"""

import asyncio
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger


# Default timeouts (seconds) so no step hangs the system
DEFAULT_EMBED_TIMEOUT = 30
DEFAULT_STORE_TIMEOUT = 15
DEFAULT_CLEANUP_TIMEOUT = 60

# Chroma metadata values must be str, int, float, bool
METADATA_LAST_USED = "last_used_timestamp"
METADATA_ADDED_AT = "added_at"
METADATA_USER_ID = "user_id"
METADATA_SOURCE_TYPE = "source_type"
METADATA_SOURCE_ID = "source_id"
METADATA_CONTENT = "content"


def prepare_content_for_kb(content: str, max_chars: int = 500_000) -> str:
    """
    First-step cleanup before chunking/embedding: strip HTML and reduce noise.
    Use for both document and web content so tags, script/style, and boilerplate
    don't get chunked and embedded.
    """
    if not content or not isinstance(content, str):
        return ""
    text = content.strip()
    if not text:
        return ""
    # Strip HTML: script/style blocks then all tags
    if "<" in text and ">" in text:
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace and normalize line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = text.strip()
    # Drop lines that are only punctuation, numbers, or very short boilerplate
    lines = text.split("\n")
    kept = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if len(s) <= 1:
            continue
        # Skip lines that are mostly non-letter (e.g. "---", "•••", "1.2.3")
        letters = sum(1 for c in s if c.isalpha())
        if letters < len(s) // 2 and len(s) < 30:
            continue
        kept.append(s)
    text = "\n".join(kept).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text


def chunk_text(
    text: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> List[str]:
    """Split text into overlapping chunks (by character). Simple and stable."""
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        # Try to break at paragraph or sentence
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                idx = chunk.rfind(sep)
                if idx > chunk_size // 2:
                    chunk = chunk[: idx + len(sep)]
                    end = start + len(chunk)
                    break
        chunks.append(chunk.strip())
        start = end - overlap
        if start >= len(text):
            break
    return [c for c in chunks if c]


class KnowledgeBase:
    """
    Local knowledge base for a user: add chunks (from document, web search, URL, manual),
    search by query (returns relevant chunks, updates last_used_timestamp), and cleanup
    items unused for longer than configured days.
    """

    def __init__(
        self,
        vector_store: Any,
        embed_fn: Any,
        config: Optional[Dict[str, Any]] = None,
        embed_timeout: float = DEFAULT_EMBED_TIMEOUT,
        store_timeout: float = DEFAULT_STORE_TIMEOUT,
    ):
        self.store = vector_store
        self.embed_fn = embed_fn
        self.config = config or {}
        self.embed_timeout = float(self.config.get("embed_timeout", embed_timeout))
        self.store_timeout = float(self.config.get("store_timeout", store_timeout))
        self.chunk_size = int(self.config.get("chunk_size", 800))
        self.chunk_overlap = int(self.config.get("chunk_overlap", 100))
        self.unused_ttl_days = float(self.config.get("unused_ttl_days", 30))

    async def _embed(self, text: str) -> Optional[List[float]]:
        """Embed one text with timeout. Returns None on failure."""
        try:
            if asyncio.iscoroutinefunction(self.embed_fn.embed):
                vec = await asyncio.wait_for(
                    self.embed_fn.embed(text),
                    timeout=self.embed_timeout,
                )
            else:
                vec = self.embed_fn.embed(text)
            return vec
        except asyncio.TimeoutError:
            logger.warning("Knowledge base embed timed out")
            return None
        except Exception as e:
            logger.warning("Knowledge base embed failed: %s", e)
            return None

    async def add(
        self,
        user_id: str,
        content: str,
        source_type: str,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add content to the knowledge base: chunk, embed, insert with metadata.
        Returns a short status message. Never raises; on failure returns error message.
        """
        if not user_id or not content or not source_type or not source_id:
            return "Error: user_id, content, source_type, and source_id are required."
        content = prepare_content_for_kb(content)
        if not content:
            return "Error: no content to add after filtering (e.g. HTML stripped, empty or only boilerplate)."
        chunks = chunk_text(content, chunk_size=self.chunk_size, overlap=self.chunk_overlap)
        if not chunks:
            return "Error: no content to add after chunking."
        now = time.time()
        ids = []
        vectors = []
        payloads = []
        for i, chunk in enumerate(chunks):
            vec = await self._embed(chunk)
            if vec is None:
                return f"Error: embedding failed for chunk {i + 1}/{len(chunks)}. Knowledge base add aborted; no data was written."
            chunk_id = f"kb_{uuid.uuid4().hex[:16]}"
            ids.append(chunk_id)
            vectors.append(vec)
            meta = {
                METADATA_USER_ID: str(user_id),
                METADATA_SOURCE_TYPE: str(source_type),
                METADATA_SOURCE_ID: str(source_id),
                METADATA_ADDED_AT: now,
                METADATA_LAST_USED: now,
                METADATA_CONTENT: (chunk[:50000] if len(chunk) > 50000 else chunk),
            }
            if metadata:
                for k, v in metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[str(k)] = v
            payloads.append(meta)
        try:
            if self.store_timeout > 0:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.store.insert(vectors=vectors, payloads=payloads, ids=ids),
                    ),
                    timeout=self.store_timeout,
                )
            else:
                self.store.insert(vectors=vectors, payloads=payloads, ids=ids)
        except asyncio.TimeoutError:
            logger.warning("Knowledge base insert timed out")
            return "Error: knowledge base insert timed out. No data was written."
        except Exception as e:
            logger.warning("Knowledge base insert failed: %s", e)
            return f"Error: knowledge base insert failed: {e!s}"
        return f"Added {len(chunks)} chunk(s) to knowledge base (source_type={source_type}, source_id={source_id})."

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge base: embed query, vector search with user_id filter, update last_used_timestamp for hits, return chunks.
        Returns list of {content, source_type, source_id, score}. On any failure returns [] so the system never hangs.
        """
        if not user_id or not query:
            return []
        vec = await self._embed(query)
        if vec is None:
            return []
        try:
            if hasattr(self.store, "search"):
                if self.store_timeout > 0:
                    results = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.store.search(
                                query=[vec],
                                limit=limit,
                                filters={METADATA_USER_ID: str(user_id)},
                            ),
                        ),
                        timeout=self.store_timeout,
                    )
                else:
                    results = self.store.search(
                        query=[vec],
                        limit=limit,
                        filters={METADATA_USER_ID: str(user_id)},
                    )
            else:
                return []
        except asyncio.TimeoutError:
            logger.warning("Knowledge base search timed out")
            return []
        except Exception as e:
            logger.warning("Knowledge base search failed: %s", e)
            return []
        out = []
        now = time.time()
        score_is_distance = self.config.get("score_is_distance", False)
        for item in (results or [])[:limit]:
            pid = getattr(item, "id", None)
            payload = getattr(item, "payload", None) or {}
            score = getattr(item, "score", None)
            # Normalize to similarity (0-1, higher = more relevant) for consistent thresholding
            if score is not None and score_is_distance:
                try:
                    d = float(score)
                    score = max(0.0, min(1.0, 1.0 - d / 2.0))  # cosine distance [0,2] -> similarity
                except (TypeError, ValueError):
                    pass
            content = payload.get(METADATA_CONTENT, "")
            source_type = payload.get(METADATA_SOURCE_TYPE, "")
            source_id = payload.get(METADATA_SOURCE_ID, "")
            out.append({
                "content": content,
                "source_type": source_type,
                "source_id": source_id,
                "score": score,
            })
            if pid and hasattr(self.store, "update"):
                try:
                    new_meta = {**payload, METADATA_LAST_USED: now}
                    if self.store_timeout > 0:
                        asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: self.store.update(vector_id=pid, payload=new_meta),
                            ),
                            timeout=5,
                        )
                    else:
                        self.store.update(vector_id=pid, payload=new_meta)
                except Exception:
                    pass
        return out

    async def remove_by_source_id(self, user_id: str, source_id: str) -> str:
        """Remove the whole document: all chunks with this (user_id, source_id). One add() = one source_id = many chunks; this deletes all of them. Never raises."""
        if not hasattr(self.store, "delete_where"):
            return "Error: this store does not support delete by source."
        try:
            if self.store_timeout > 0:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.store.delete_where({
                            METADATA_USER_ID: str(user_id),
                            METADATA_SOURCE_ID: str(source_id),
                        }),
                    ),
                    timeout=self.store_timeout,
                )
            else:
                self.store.delete_where({
                    METADATA_USER_ID: str(user_id),
                    METADATA_SOURCE_ID: str(source_id),
                })
        except asyncio.TimeoutError:
            logger.warning("Knowledge base delete_where timed out")
            return "Error: delete timed out."
        except Exception as e:
            logger.warning("Knowledge base delete_where failed: %s", e)
            return f"Error: delete failed: {e!s}"
        return f"Removed all knowledge base entries for source_id={source_id}."

    async def list_sources(self, user_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        """
        List saved sources (documents) for this user: unique (source_id, source_type) with optional added_at.
        Returns list of {source_id, source_type, added_at}. On failure returns [].
        """
        if not user_id:
            return []
        if not hasattr(self.store, "get_where"):
            return []
        try:
            where = {METADATA_USER_ID: str(user_id)}
            if self.store_timeout > 0:
                rows = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.store.get_where(where, limit=limit * 5),
                    ),
                    timeout=self.store_timeout,
                )
            else:
                rows = self.store.get_where(where, limit=limit * 5)
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug("Knowledge base list_sources get_where failed: %s", e)
            return []
        seen: Dict[str, Dict[str, Any]] = {}
        for _id, meta in (rows or []):
            sid = (meta or {}).get(METADATA_SOURCE_ID)
            stype = (meta or {}).get(METADATA_SOURCE_TYPE, "")
            added = (meta or {}).get(METADATA_ADDED_AT)
            if sid and sid not in seen:
                seen[sid] = {"source_id": sid, "source_type": stype, "added_at": added}
            if len(seen) >= limit:
                break
        return list(seen.values())

    async def cleanup_unused(self, user_id: str, unused_days: Optional[float] = None) -> str:
        """
        Delete items (by source_id) that have not been used for unused_days.
        Uses last_used_timestamp. Never hangs; on failure returns error message.
        """
        days = unused_days if unused_days is not None else self.unused_ttl_days
        cutoff = time.time() - (days * 24 * 3600)
        if not hasattr(self.store, "get_where") or not hasattr(self.store, "delete_where"):
            return "Error: this store does not support cleanup by last_used_timestamp."
        try:
            if self.store_timeout > 0:
                rows = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.store.get_where(
                            {"$and": [{METADATA_USER_ID: str(user_id)}, {METADATA_LAST_USED: {"$lt": cutoff}}]},
                            limit=50000,
                        ),
                    ),
                    timeout=self.store_timeout,
                )
            else:
                rows = self.store.get_where(
                    {"$and": [{METADATA_USER_ID: str(user_id)}, {METADATA_LAST_USED: {"$lt": cutoff}}]},
                    limit=50000,
                )
        except asyncio.TimeoutError:
            logger.warning("Knowledge base cleanup get_where timed out")
            return "Error: cleanup timed out."
        except Exception as e:
            logger.warning("Knowledge base cleanup get_where failed: %s", e)
            return f"Error: cleanup failed: {e!s}"
        source_ids = set()
        for _id, meta in (rows or []):
            sid = (meta or {}).get(METADATA_SOURCE_ID)
            if sid:
                source_ids.add(sid)
        removed = 0
        for sid in source_ids:
            try:
                if self.store_timeout > 0:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda s=sid: self.store.delete_where({
                                METADATA_USER_ID: str(user_id),
                                METADATA_SOURCE_ID: s,
                            }),
                        ),
                        timeout=self.store_timeout,
                    )
                else:
                    self.store.delete_where({
                        METADATA_USER_ID: str(user_id),
                        METADATA_SOURCE_ID: sid,
                    })
                removed += 1
            except Exception:
                pass
        return f"Cleanup: removed {removed} source(s) unused for more than {days} days."

    async def reset(self) -> str:
        """Clear the entire knowledge base (all users, all sources). Never raises; returns status message."""
        if not hasattr(self.store, "get_all_ids") or not hasattr(self.store, "delete_ids"):
            return "Error: this store does not support reset (missing get_all_ids/delete_ids)."
        total = 0
        try:
            while True:
                if self.store_timeout > 0:
                    ids = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.store.get_all_ids(10000),
                        ),
                        timeout=self.store_timeout,
                    )
                else:
                    ids = self.store.get_all_ids(10000)
                if not ids:
                    break
                if self.store_timeout > 0:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: self.store.delete_ids(ids),
                        ),
                        timeout=self.store_timeout,
                    )
                else:
                    self.store.delete_ids(ids)
                total += len(ids)
        except asyncio.TimeoutError:
            logger.warning("Knowledge base reset timed out")
            return f"Error: reset timed out (deleted {total} chunk(s) so far)."
        except Exception as e:
            logger.warning("Knowledge base reset failed: %s", e)
            return f"Error: reset failed: {e!s}"
        return f"Knowledge base reset: deleted {total} chunk(s)."
