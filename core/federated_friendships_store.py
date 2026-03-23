"""
SQLite store for cross-instance friend relationships (pending / accepted / rejected / blocked).

Used when federation_enabled; see docs_design/FederatedCompanionUserMessaging.md P3.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from base.util import Util


def _db_path() -> Path:
    try:
        return Path(Util().data_path()) / "federated_friendships.sqlite"
    except Exception:
        return Path("federated_friendships.sqlite")


def _connect() -> sqlite3.Connection:
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS federated_friendships (
            id TEXT PRIMARY KEY,
            from_fid TEXT NOT NULL,
            to_local_user_id TEXT NOT NULL,
            state TEXT NOT NULL,
            message TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(from_fid, to_local_user_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ff_to_state ON federated_friendships(to_local_user_id, state)"
    )
    conn.commit()


def get_row(from_fid: str, to_local_user_id: str) -> Optional[Dict[str, Any]]:
    """Return one row as dict or None. Never raises."""
    try:
        ff = (from_fid or "").strip()
        to_u = (to_local_user_id or "").strip()
        if not ff or not to_u:
            return None
        with _connect() as c:
            _ensure_schema(c)
            cur = c.execute(
                "SELECT id, from_fid, to_local_user_id, state, message, created_at, updated_at "
                "FROM federated_friendships WHERE from_fid = ? AND to_local_user_id = ?",
                (ff, to_u),
            )
            r = cur.fetchone()
            if not r:
                return None
            return dict(r)
    except Exception as e:
        logger.debug("federated_friendships get_row failed: {}", e)
        return None


def get_state(from_fid: str, to_local_user_id: str) -> Optional[str]:
    row = get_row(from_fid, to_local_user_id)
    if not row:
        return None
    return (row.get("state") or "").strip().lower() or None


def is_accepted(from_fid: str, to_local_user_id: str) -> bool:
    return get_state(from_fid, to_local_user_id) == "accepted"


def create_or_refresh_pending(
    from_fid: str,
    to_local_user_id: str,
    message: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Create pending inbound request or refresh message if still pending rejected→pending.
    Returns (request_id, status_tag): status_tag one of created, already_pending, already_accepted, updated.
    """
    try:
        ff = (from_fid or "").strip()
        to_u = (to_local_user_id or "").strip()
        if not ff or not to_u:
            return None, "invalid"
        msg = (message or "").strip() or None
        now = time.time()
        rid = str(uuid.uuid4())
        with _connect() as c:
            _ensure_schema(c)
            existing = get_row(ff, to_u)
            if existing:
                st = (existing.get("state") or "").strip().lower()
                if st == "accepted":
                    return (existing.get("id") or "").strip() or None, "already_accepted"
                if st == "pending":
                    c.execute(
                        "UPDATE federated_friendships SET message = COALESCE(?, message), updated_at = ? "
                        "WHERE from_fid = ? AND to_local_user_id = ?",
                        (msg, now, ff, to_u),
                    )
                    c.commit()
                    return (existing.get("id") or "").strip() or None, "already_pending"
                if st == "blocked":
                    return (existing.get("id") or "").strip() or None, "blocked"
                if st == "rejected":
                    c.execute(
                        "UPDATE federated_friendships SET state = 'pending', message = ?, updated_at = ?, id = ? "
                        "WHERE from_fid = ? AND to_local_user_id = ?",
                        (msg, now, rid, ff, to_u),
                    )
                    c.commit()
                    return rid, "updated"
            c.execute(
                "INSERT INTO federated_friendships (id, from_fid, to_local_user_id, state, message, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
                (rid, ff, to_u, msg, now, now),
            )
            c.commit()
            return rid, "created"
    except Exception as e:
        logger.warning("federated_friendships create_or_refresh_pending failed: {}", e)
        return None, "error"


def get_by_id_for_recipient(request_id: str, to_local_user_id: str) -> Optional[Dict[str, Any]]:
    """Return row if id matches and recipient is to_local_user_id."""
    try:
        rid = (request_id or "").strip()
        to_u = (to_local_user_id or "").strip()
        if not rid or not to_u:
            return None
        with _connect() as c:
            _ensure_schema(c)
            cur = c.execute(
                "SELECT id, from_fid, to_local_user_id, state, message, created_at FROM federated_friendships WHERE id = ? AND to_local_user_id = ?",
                (rid, to_u),
            )
            r = cur.fetchone()
            return dict(r) if r else None
    except Exception as e:
        logger.debug("federated_friendships get_by_id failed: {}", e)
        return None


def list_pending_for_local_user(to_local_user_id: str) -> List[Dict[str, Any]]:
    """Pending inbound requests for this local user. Newest first."""
    try:
        to_u = (to_local_user_id or "").strip()
        if not to_u:
            return []
        with _connect() as c:
            _ensure_schema(c)
            cur = c.execute(
                "SELECT id, from_fid, to_local_user_id, message, created_at FROM federated_friendships "
                "WHERE to_local_user_id = ? AND state = 'pending' ORDER BY created_at DESC",
                (to_u,),
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.debug("federated_friendships list_pending failed: {}", e)
        return []


def set_state_by_id(request_id: str, to_local_user_id: str, new_state: str) -> Optional[Dict[str, Any]]:
    """
    Set state for a row owned by to_local_user_id. new_state: accepted | rejected | blocked.
    Returns updated row dict (with from_fid) or None.
    """
    try:
        rid = (request_id or "").strip()
        to_u = (to_local_user_id or "").strip()
        st = (new_state or "").strip().lower()
        if st not in ("accepted", "rejected", "blocked") or not rid or not to_u:
            return None
        now = time.time()
        with _connect() as c:
            _ensure_schema(c)
            cur = c.execute(
                "SELECT id, from_fid, to_local_user_id, state FROM federated_friendships WHERE id = ? AND to_local_user_id = ?",
                (rid, to_u),
            )
            r = cur.fetchone()
            if not r:
                return None
            if (dict(r).get("state") or "").strip().lower() != "pending":
                return None
            c.execute(
                "UPDATE federated_friendships SET state = ?, updated_at = ? WHERE id = ?",
                (st, now, rid),
            )
            c.commit()
            return get_row(dict(r)["from_fid"], to_u)
    except Exception as e:
        logger.warning("federated_friendships set_state_by_id failed: {}", e)
        return None


def upsert_reciprocal_accepted(from_fid: str, to_local_user_id: str) -> bool:
    """
    Idempotent: ensure (from_fid → to_local_user_id) is accepted. Used by peer Core after local accept.
    """
    try:
        ff = (from_fid or "").strip()
        to_u = (to_local_user_id or "").strip()
        if not ff or not to_u:
            return False
        now = time.time()
        rid = str(uuid.uuid4())
        with _connect() as c:
            _ensure_schema(c)
            row = get_row(ff, to_u)
            if row and (row.get("state") or "").strip().lower() == "accepted":
                return True
            if row:
                c.execute(
                    "UPDATE federated_friendships SET state = 'accepted', updated_at = ? WHERE from_fid = ? AND to_local_user_id = ?",
                    (now, ff, to_u),
                )
            else:
                c.execute(
                    "INSERT INTO federated_friendships (id, from_fid, to_local_user_id, state, message, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'accepted', NULL, ?, ?)",
                    (rid, ff, to_u, now, now),
                )
            c.commit()
            return True
    except Exception as e:
        logger.warning("federated_friendships upsert_reciprocal_accepted failed: {}", e)
        return False
