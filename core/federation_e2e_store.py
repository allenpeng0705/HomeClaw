"""
Per-user X25519 public keys for federated E2E messaging (P5). Private keys stay on Companion only.

SQLite under data_path()/federation_e2e_keys.sqlite
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from base.util import Util


def _db_path() -> Path:
    try:
        return Path(Util().data_path()) / "federation_e2e_keys.sqlite"
    except Exception:
        return Path("federation_e2e_keys.sqlite")


def _connect() -> sqlite3.Connection:
    p = _db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS federation_e2e_keys (
            user_id TEXT PRIMARY KEY,
            public_key_b64 TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.commit()


def get_public_key_b64(user_id: str) -> Optional[str]:
    uid = (user_id or "").strip()
    if not uid:
        return None
    try:
        with _connect() as c:
            _ensure_schema(c)
            cur = c.execute(
                "SELECT public_key_b64 FROM federation_e2e_keys WHERE user_id = ?",
                (uid,),
            )
            row = cur.fetchone()
            if not row:
                return None
            s = (row[0] or "").strip()
            return s if s else None
    except Exception as e:
        logger.debug("federation_e2e get_public_key failed: {}", e)
        return None


def upsert_public_key(user_id: str, public_key_b64: str) -> bool:
    uid = (user_id or "").strip()
    pk = (public_key_b64 or "").strip()
    if not uid or not pk:
        return False
    try:
        now = time.time()
        with _connect() as c:
            _ensure_schema(c)
            c.execute(
                "INSERT INTO federation_e2e_keys (user_id, public_key_b64, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET public_key_b64 = excluded.public_key_b64, updated_at = excluded.updated_at",
                (uid, pk, now),
            )
            c.commit()
            return True
    except Exception as e:
        logger.warning("federation_e2e upsert_public_key failed: {}", e)
        return False
