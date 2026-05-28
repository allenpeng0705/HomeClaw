"""
Tool audit — Phase 6: Structured audit events for tool executions.

Inspired by OpenClaw's agents/tool-policy-audit.ts.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from loguru import logger


@dataclass
class ToolAuditEvent:
    event_id: str
    tool_name: str
    timestamp: float = 0.0
    agent_id: str = ""
    session_id: str = ""
    user_id: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    result_status: str = ""  # "ok" | "error" | "timeout" | "denied"
    result_summary: str = ""
    duration_ms: float = 0.0
    approved: bool = False


# Default DB path
_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "database"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "audit.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_audit (
    event_id      TEXT PRIMARY KEY,
    tool_name     TEXT NOT NULL,
    timestamp     REAL NOT NULL,
    agent_id      TEXT DEFAULT '',
    session_id    TEXT DEFAULT '',
    user_id       TEXT DEFAULT '',
    tool_args     TEXT DEFAULT '{}',
    result_status TEXT DEFAULT '',
    result_summary TEXT DEFAULT '',
    duration_ms   REAL DEFAULT 0,
    approved      INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_audit_tool ON tool_audit(tool_name);
CREATE INDEX IF NOT EXISTS idx_audit_time ON tool_audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON tool_audit(agent_id);
"""

_lock = Lock()


def _get_db_path() -> str:
    return str(_DEFAULT_DB_PATH)


def init_audit_db(db_path: Optional[str] = None) -> None:
    path = db_path or _get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path)
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()


def record_event(event: ToolAuditEvent, db_path: Optional[str] = None) -> None:
    path = db_path or _get_db_path()
    event.timestamp = event.timestamp or time.time()
    with _lock:
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                """INSERT INTO tool_audit (event_id, tool_name, timestamp,
                   agent_id, session_id, user_id, tool_args, result_status,
                   result_summary, duration_ms, approved)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event.event_id, event.tool_name, event.timestamp,
                 event.agent_id, event.session_id, event.user_id,
                 json.dumps(event.tool_args, ensure_ascii=False),
                 event.result_status, event.result_summary,
                 event.duration_ms, 1 if event.approved else 0),
            )
            conn.commit()
        finally:
            conn.close()


def query_events(
    *,
    tool_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    session_id: Optional[str] = None,
    result_status: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query audit events with optional filters."""
    path = db_path or _get_db_path()
    conditions = []
    params: List[Any] = []
    if tool_name:
        conditions.append("tool_name = ?")
        params.append(tool_name)
    if agent_id:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if result_status:
        conditions.append("result_status = ?")
        params.append(result_status)
    if since is not None:
        conditions.append("timestamp >= ?")
        params.append(since)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit])

    with _lock:
        conn = sqlite3.connect(path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM tool_audit {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_summary(
    *,
    since: Optional[float] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Get a summary of recent audit activity."""
    path = db_path or _get_db_path()
    cond = "WHERE timestamp >= ?" if since is not None else ""
    params: List[Any] = [since] if since is not None else []

    with _lock:
        conn = sqlite3.connect(path)
        try:
            total = conn.execute(
                f"SELECT COUNT(*) FROM tool_audit {cond}", params
            ).fetchone()[0]
            errors = conn.execute(
                f"SELECT COUNT(*) FROM tool_audit {cond} {'AND' if since else 'WHERE'} result_status = 'error'",
                params,
            ).fetchone()[0]
            denied = conn.execute(
                f"SELECT COUNT(*) FROM tool_audit {cond} {'AND' if since else 'WHERE'} result_status = 'denied'",
                params,
            ).fetchone()[0]
            by_tool: Dict[str, int] = {}
            for row in conn.execute(
                f"SELECT tool_name, COUNT(*) FROM tool_audit {cond} {'AND' if since else 'WHERE'} 1=1 GROUP BY tool_name",
                params,
            ):
                by_tool[row[0]] = row[1]
            return {"total": total, "errors": errors, "denied": denied, "by_tool": by_tool}
        finally:
            conn.close()
