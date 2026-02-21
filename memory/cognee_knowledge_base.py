"""
Knowledge base backend using Cognee: add -> cognify -> search.
Use when knowledge_base.backend is cognee (or memory_backend is cognee and backend is auto).
One Cognee dataset per (user_id, source_id) so we can remove by source via delete_dataset.

We keep a small sidecar DB (added_at per source) so we can run age-based cleanup and avoid
Cognee growing without bound. cleanup_unused removes sources older than unused_ttl_days.
"""

# Cognee uses starlette.status.HTTP_422_UNPROCESSABLE_CONTENT; Starlette only has HTTP_422_UNPROCESSABLE_ENTITY.
# Patch so Cognee import succeeds with current Starlette.
try:
    import starlette.status as _starlette_status
    if not hasattr(_starlette_status, "HTTP_422_UNPROCESSABLE_CONTENT") and hasattr(_starlette_status, "HTTP_422_UNPROCESSABLE_ENTITY"):
        _starlette_status.HTTP_422_UNPROCESSABLE_CONTENT = _starlette_status.HTTP_422_UNPROCESSABLE_ENTITY
except Exception:
    pass

import asyncio
import hashlib
import os
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from loguru import logger

from memory.cognee_adapter import apply_cognee_config
from memory.knowledge_base import prepare_content_for_kb

# Sidecar DB for (user_id, source_id, added_at) so we can evict by age
_SIDECAR_TABLE = "kb_cognee_meta"
_SIDECAR_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_cognee_meta (
  user_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  added_at REAL NOT NULL,
  PRIMARY KEY (user_id, source_id)
);
"""


def _sidecar_path() -> str:
    try:
        from base.util import Util
        return os.path.join(Util().data_path(), "kb_cognee_meta.db")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".gpt4all", "kb_cognee_meta.db")


def _sidecar_record_add(user_id: str, source_id: str) -> None:
    try:
        path = _sidecar_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute(_SIDECAR_SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO kb_cognee_meta (user_id, source_id, added_at) VALUES (?, ?, ?)",
                (str(user_id), str(source_id), time.time()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cognee KB sidecar record add failed: {}", e)


def _sidecar_record_remove(user_id: str, source_id: str) -> None:
    try:
        path = _sidecar_path()
        if not os.path.exists(path):
            return
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "DELETE FROM kb_cognee_meta WHERE user_id = ? AND source_id = ?",
                (str(user_id), str(source_id)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cognee KB sidecar record remove failed: {}", e)


def _sidecar_list_old(user_id: str, older_than_ts: float) -> List[str]:
    """Return source_ids for this user with added_at < older_than_ts (oldest first)."""
    try:
        path = _sidecar_path()
        if not os.path.exists(path):
            return []
        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(
                "SELECT source_id FROM kb_cognee_meta WHERE user_id = ? AND added_at < ? ORDER BY added_at ASC",
                (str(user_id), older_than_ts),
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cognee KB sidecar list old failed: {}", e)
        return []


def _sidecar_count_user(user_id: str) -> int:
    try:
        path = _sidecar_path()
        if not os.path.exists(path):
            return 0
        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM kb_cognee_meta WHERE user_id = ?",
                (str(user_id),),
            )
            return cur.fetchone()[0] or 0
        finally:
            conn.close()
    except Exception:
        return 0


def _sidecar_oldest_n(user_id: str, n: int) -> List[str]:
    """Return up to n oldest source_ids for this user (by added_at ASC)."""
    try:
        path = _sidecar_path()
        if not os.path.exists(path) or n <= 0:
            return []
        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(
                "SELECT source_id FROM kb_cognee_meta WHERE user_id = ? ORDER BY added_at ASC LIMIT ?",
                (str(user_id), n),
            )
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cognee KB sidecar oldest_n failed: {}", e)
        return []


def _sidecar_list_sources(user_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Return list of {source_id, added_at} for this user (for list_sources / has_source)."""
    try:
        path = _sidecar_path()
        if not os.path.exists(path):
            return []
        conn = sqlite3.connect(path)
        try:
            cur = conn.execute(
                "SELECT source_id, added_at FROM kb_cognee_meta WHERE user_id = ? ORDER BY added_at DESC LIMIT ?",
                (str(user_id), limit),
            )
            return [{"source_id": row[0], "added_at": row[1]} for row in cur.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cognee KB sidecar list_sources failed: {}", e)
        return []


def _sidecar_clear_all() -> None:
    """Remove all rows from the Cognee KB sidecar (for reset)."""
    try:
        path = _sidecar_path()
        if not os.path.exists(path):
            return
        conn = sqlite3.connect(path)
        try:
            conn.execute("DELETE FROM kb_cognee_meta")
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.debug("Cognee KB sidecar clear failed: {}", e)


def _safe(s: str, max_len: int = 100) -> str:
    """Safe for Cognee dataset name: alphanumeric, underscore, hyphen, dot."""
    s = (s or "").strip() or "default"
    s = re.sub(r"[^\w\-.]", "_", s)[:max_len]
    return s or "default"


def _kb_dataset_prefix(user_id: str) -> str:
    """Prefix for all KB datasets of this user (e.g. kb_alice)."""
    return f"kb_{_safe(user_id)}"


def _kb_dataset_name_for_source(user_id: str, source_id: str) -> str:
    """One dataset per (user_id, source_id) so we can delete by source. Stable, short name."""
    prefix = _kb_dataset_prefix(user_id)
    h = hashlib.sha256((source_id or "").strip().encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{h}"


class CogneeKnowledgeBase:
    """
    Knowledge base using Cognee: one dataset per (user_id, source_id).
    Sidecar DB tracks added_at so we can run age-based cleanup and cap; Cognee stays bounded.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, kb_config: Optional[Dict[str, Any]] = None):
        if config:
            apply_cognee_config(config)
        try:
            import cognee  # noqa: F401
            self._cognee = cognee
        except ImportError as e:
            raise ImportError(
                "Cognee knowledge base requires: pip install cognee. "
                "Configure via cognee section in core.yml or .env."
            ) from e
        kbc = kb_config or {}
        self._unused_ttl_days = float(kbc.get("unused_ttl_days", 30) or 30)
        self._max_sources_per_user = max(0, int(kbc.get("max_sources_per_user", 0) or 0))
        self._add_timeout = 90
        self._search_timeout = 30
        self._list_timeout = 15

    async def _list_user_kb_datasets_async(self, user_id: str) -> List[str]:
        """List Cognee dataset names for this user's KB (prefix kb_{user}_)."""
        prefix = _kb_dataset_prefix(user_id) + "_"
        try:
            if not hasattr(self._cognee, "datasets") or not hasattr(self._cognee.datasets, "list_datasets"):
                return []
            datasets_list = await asyncio.wait_for(
                self._cognee.datasets.list_datasets(),
                timeout=self._list_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Cognee KB list_datasets timed out")
            return []
        except Exception as e:
            logger.debug("Cognee KB list_datasets failed: {}", e)
            return []
        out = []
        for d in (datasets_list or []):
            name = getattr(d, "name", None) or (d.get("name") if isinstance(d, dict) else None)
            if name and name.startswith(prefix):
                out.append(name)
        return out

    async def add(
        self,
        user_id: str,
        content: str,
        source_type: str,
        source_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add content to the user's KB (one dataset per source_id). Evicts old/capped sources first so Cognee does not grow unbounded. Never raises."""
        if not (user_id or "").strip() or not (content or "").strip():
            return "Error: user_id and content are required."
        if not (source_id or "").strip():
            return "Error: source_id is required for Cognee KB (used to remove or replace later)."
        content = prepare_content_for_kb(content)
        if not content:
            return "Error: no content to add after filtering (e.g. HTML stripped, empty or only boilerplate)."
        uid, sid = str(user_id).strip(), str(source_id).strip()
        try:
            # Evict old entries first (age-based) so Cognee doesn't grow without bound
            if self._unused_ttl_days > 0:
                await self.cleanup_unused(uid, self._unused_ttl_days)
            # Enforce cap: remove oldest sources if over limit
            if self._max_sources_per_user > 0:
                count = _sidecar_count_user(uid)
                if count >= self._max_sources_per_user:
                    to_remove = count - self._max_sources_per_user + 1
                    for old_sid in _sidecar_oldest_n(uid, to_remove):
                        await self.remove_by_source_id(uid, old_sid)
            dataset_name = _kb_dataset_name_for_source(uid, sid)
            # Replace semantics: delete existing dataset with this name so re-add overwrites
            if hasattr(self._cognee, "datasets") and hasattr(self._cognee.datasets, "list_datasets") and hasattr(self._cognee.datasets, "delete_dataset"):
                try:
                    datasets_list = await asyncio.wait_for(self._cognee.datasets.list_datasets(), timeout=self._list_timeout)
                    for d in (datasets_list or []):
                        name = getattr(d, "name", None) or (isinstance(d, dict) and d.get("name"))
                        if name == dataset_name:
                            did = getattr(d, "id", None) or (isinstance(d, dict) and d.get("id"))
                            if did:
                                await asyncio.wait_for(self._cognee.datasets.delete_dataset(str(did)), timeout=self._list_timeout)
                            break
                except Exception:
                    pass
            await asyncio.wait_for(
                self._cognee.add(content, dataset_name=dataset_name),
                timeout=self._add_timeout,
            )
            await asyncio.wait_for(
                self._cognee.cognify(datasets=[dataset_name]),
                timeout=self._add_timeout,
            )
            _sidecar_record_add(uid, sid)
        except asyncio.TimeoutError:
            logger.warning("Cognee KB add/cognify timed out")
            return "Error: knowledge base add timed out."
        except Exception as e:
            logger.warning("Cognee KB add failed: {}", e)
            return f"Error: knowledge base add failed: {e!s}"
        return f"Added to knowledge base (source_id={source_id}). Use knowledge_base_remove(source_id={source_id!r}) to remove."

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search all KB datasets for this user. Returns list of {content, source_type, source_id, score}. Never raises."""
        if not (user_id or "").strip() or not (query or "").strip():
            return []
        dataset_names = await self._list_user_kb_datasets_async(user_id)
        if not dataset_names:
            return []
        try:
            results = await asyncio.wait_for(
                self._cognee.search(query, datasets=dataset_names, top_k=limit or 10),
                timeout=self._search_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Cognee KB search timed out")
            return []
        except Exception as e:
            logger.debug("Cognee KB search failed: {}", e)
            return []
        out = []
        for i, r in enumerate(results if isinstance(results, list) else [results]):
            if isinstance(r, str):
                out.append({"content": r, "source_type": "cognee", "source_id": "", "score": 0.8 - i * 0.05})
            elif isinstance(r, dict):
                text = r.get("text") or r.get("content") or r.get("memory") or str(r)
                out.append({
                    "content": text,
                    "source_type": r.get("source_type", "cognee"),
                    "source_id": r.get("source_id", ""),
                    "score": float(r.get("score", 0.8 - i * 0.05)),
                })
            else:
                out.append({"content": str(r), "source_type": "cognee", "source_id": "", "score": 0.8})
        return out[: limit or 10]

    async def list_sources(self, user_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        """List saved sources for this user from sidecar. Returns list of {source_id, added_at} (source_type not stored in sidecar)."""
        if not (user_id or "").strip():
            return []
        raw = _sidecar_list_sources(str(user_id).strip(), limit=limit)
        return [{"source_id": r["source_id"], "source_type": "", "added_at": r.get("added_at")} for r in raw]

    async def remove_by_source_id(self, user_id: str, source_id: str) -> str:
        """Remove the whole document: delete the Cognee dataset for this (user_id, source_id). Never raises."""
        if not (user_id or "").strip() or not (source_id or "").strip():
            return "Error: user_id and source_id are required."
        uid, sid = str(user_id).strip(), str(source_id).strip()
        dataset_name = _kb_dataset_name_for_source(uid, sid)
        try:
            if not hasattr(self._cognee, "datasets") or not hasattr(self._cognee.datasets, "list_datasets") or not hasattr(self._cognee.datasets, "delete_dataset"):
                return "Error: Cognee datasets API (list_datasets/delete_dataset) not available."
            datasets_list = await asyncio.wait_for(self._cognee.datasets.list_datasets(), timeout=self._list_timeout)
            for d in (datasets_list or []):
                name = getattr(d, "name", None) or (isinstance(d, dict) and d.get("name"))
                if name == dataset_name:
                    did = getattr(d, "id", None) or (isinstance(d, dict) and d.get("id"))
                    if did:
                        await asyncio.wait_for(self._cognee.datasets.delete_dataset(str(did)), timeout=self._list_timeout)
                        _sidecar_record_remove(uid, sid)
                        return f"Removed all knowledge base entries for source_id={source_id!r}."
                    break
            _sidecar_record_remove(uid, sid)
            return f"No knowledge base entry found for source_id={source_id!r}."
        except asyncio.TimeoutError:
            logger.warning("Cognee KB remove timed out")
            return "Error: remove timed out."
        except Exception as e:
            logger.warning("Cognee KB remove failed: {}", e)
            return f"Error: remove failed: {e!s}"

    async def cleanup_unused(self, user_id: str, unused_days: Optional[float] = None) -> str:
        """Remove sources added more than unused_days ago (age-based TTL). Keeps Cognee from growing without bound. Never raises."""
        if not (user_id or "").strip():
            return "Error: user_id is required."
        uid = str(user_id).strip()
        days = unused_days if unused_days is not None else self._unused_ttl_days
        if days <= 0:
            return "Cleanup skipped (unused_ttl_days not set or zero)."
        cutoff = time.time() - (days * 24 * 3600)
        old_sids = _sidecar_list_old(uid, cutoff)
        removed = 0
        for sid in old_sids:
            try:
                out = await self.remove_by_source_id(uid, sid)
                if "Removed" in out or "No knowledge base entry" in out:
                    removed += 1
            except Exception:
                pass
        return f"Cleanup: removed {removed} source(s) older than {days} days."

    async def reset(self) -> str:
        """Clear the entire knowledge base (all users, all sources): delete all kb_* datasets in Cognee and clear sidecar. Never raises."""
        removed = 0
        try:
            if not hasattr(self._cognee, "datasets") or not hasattr(self._cognee.datasets, "list_datasets") or not hasattr(self._cognee.datasets, "delete_dataset"):
                return "Error: Cognee datasets API not available."
            datasets_list = await asyncio.wait_for(self._cognee.datasets.list_datasets(), timeout=self._list_timeout)
            for d in (datasets_list or []):
                name = getattr(d, "name", None) or (isinstance(d, dict) and d.get("name"))
                if name and name.startswith("kb_"):
                    did = getattr(d, "id", None) or (isinstance(d, dict) and d.get("id"))
                    if did:
                        try:
                            await asyncio.wait_for(self._cognee.datasets.delete_dataset(str(did)), timeout=self._list_timeout)
                            removed += 1
                        except Exception:
                            pass
            _sidecar_clear_all()
        except asyncio.TimeoutError:
            logger.warning("Cognee KB reset timed out")
            return f"Error: reset timed out (deleted {removed} dataset(s) so far)."
        except Exception as e:
            logger.warning("Cognee KB reset failed: {}", e)
            return f"Error: reset failed: {e!s}"
        return f"Knowledge base reset: deleted {removed} dataset(s) and cleared sidecar."
