"""
Task registry SQLite store — Phase 4.

Persists TaskRecords in database/tasks.db with status transitions and event logs.
Uses the same SQLAlchemy pattern as HomeClaw's existing database modules.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from loguru import logger

from core.task_registry.types import (
    TaskRecord, TaskStatus, TaskRuntime, TaskEvent, TaskEventKind,
    TaskSummary, is_terminal,
)

# Default DB path: same as HomeClaw's database directory
_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent.parent / "database"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "tasks.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    runtime        TEXT NOT NULL DEFAULT 'subagent',
    task_kind      TEXT,
    status         TEXT NOT NULL DEFAULT 'queued',
    owner_key      TEXT NOT NULL DEFAULT '',
    owner_user_id  TEXT NOT NULL DEFAULT '',
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    completed_at   REAL,
    result_summary TEXT,
    child_session  TEXT,
    metadata_json  TEXT DEFAULT '{}',
    events_json    TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_key);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
"""


class TaskStore:
    """SQLite-backed task persistence."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or str(_DEFAULT_DB_PATH)
        self._lock = Lock()
        self._init_db()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def create(self, task: TaskRecord) -> None:
        now = time.time()
        task.created_at = task.created_at or now
        task.updated_at = now
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    """INSERT INTO tasks (task_id, runtime, task_kind, status,
                       owner_key, owner_user_id, created_at, updated_at,
                       metadata_json, events_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (task.task_id, task.runtime.value, task.task_kind,
                     task.status.value, task.owner_session_key, task.owner_user_id,
                     task.created_at, task.updated_at,
                     json.dumps(task.metadata, ensure_ascii=False),
                     json.dumps([self._event_to_dict(e) for e in task.events], ensure_ascii=False)),
                )
                conn.commit()
            finally:
                conn.close()

    def update_status(self, task_id: str, status: TaskStatus,
                      result_summary: Optional[str] = None,
                      event: Optional[TaskEvent] = None) -> bool:
        now = time.time()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                updates = {"status": status.value, "updated_at": now}
                if result_summary is not None:
                    updates["result_summary"] = result_summary
                if is_terminal(status):
                    updates["completed_at"] = now

                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [task_id]
                cursor = conn.execute(
                    f"UPDATE tasks SET {set_clause} WHERE task_id = ?", values)

                if event is not None and cursor.rowcount > 0:
                    current = conn.execute(
                        "SELECT events_json FROM tasks WHERE task_id = ?", (task_id,)
                    ).fetchone()
                    if current:
                        try:
                            events = json.loads(current[0] or "[]")
                        except json.JSONDecodeError:
                            events = []
                        events.append(self._event_to_dict(event))
                        conn.execute(
                            "UPDATE tasks SET events_json = ? WHERE task_id = ?",
                            (json.dumps(events, ensure_ascii=False), task_id))

                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                row = conn.execute(
                    "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()
                return self._row_to_record(row) if row else None
            finally:
                conn.close()

    def list(
        self,
        status: Optional[str] = None,
        owner_key: Optional[str] = None,
        runtime: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TaskRecord]:
        conditions = []
        params: List[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if owner_key:
            conditions.append("owner_key = ?")
            params.append(owner_key)
        if runtime:
            conditions.append("runtime = ?")
            params.append(runtime)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                rows = conn.execute(
                    f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    params,
                ).fetchall()
                return [r for r in (self._row_to_record(row) for row in rows) if r is not None]
            finally:
                conn.close()

    def summary(self) -> TaskSummary:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
                active = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status NOT IN ('succeeded','failed','timed_out','cancelled','lost')"
                ).fetchone()[0]
                terminal = total - active
                failures = conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE status IN ('failed','timed_out','lost')"
                ).fetchone()[0]
                by_status: Dict[str, int] = {}
                for row in conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status"):
                    by_status[row[0]] = row[1]
                by_runtime: Dict[str, int] = {}
                for row in conn.execute("SELECT runtime, COUNT(*) FROM tasks GROUP BY runtime"):
                    by_runtime[row[0]] = row[1]
                return TaskSummary(
                    total=total, active=active, terminal=terminal, failures=failures,
                    by_status=by_status, by_runtime=by_runtime,
                )
            finally:
                conn.close()

    def cleanup(self, retention_days: int = 7) -> int:
        cutoff = time.time() - (retention_days * 86400)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                cursor = conn.execute(
                    "DELETE FROM tasks WHERE status IN ('succeeded','failed','timed_out','cancelled','lost') AND completed_at < ?",
                    (cutoff,),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    @staticmethod
    def _event_to_dict(e: TaskEvent) -> Dict[str, Any]:
        return {"at": e.at, "kind": e.kind.value,
                "summary": e.summary, "detail": e.detail}

    @staticmethod
    def _row_to_record(row: Any) -> Optional[TaskRecord]:
        if row is None:
            return None
        try:
            meta = json.loads(row[11] or "{}") if len(row) > 11 else {}
            events_raw = json.loads(row[12] or "[]") if len(row) > 12 else []
            events = [
                TaskEvent(at=e.get("at", 0), kind=TaskEventKind(e["kind"]),
                          summary=e.get("summary"), detail=e.get("detail"))
                for e in events_raw if isinstance(e, dict)
            ]
            return TaskRecord(
                task_id=row[0],
                runtime=TaskRuntime(row[1]),
                task_kind=row[2],
                status=TaskStatus(row[3]),
                owner_session_key=row[4],
                owner_user_id=row[5],
                created_at=row[6],
                updated_at=row[7],
                completed_at=row[8],
                result_summary=row[9],
                child_session_id=row[10] if len(row) > 10 else None,
                metadata=meta,
                events=events,
            )
        except Exception as e:
            logger.debug("TaskStore._row_to_record failed: {}", e)
            return None
