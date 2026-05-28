"""
Task registry — Phase 4: create, track, query, and clean up tasks.

Inspired by OpenClaw's src/tasks/task-registry.ts.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from core.task_registry.types import (
    TaskRecord, TaskStatus, TaskRuntime, TaskEvent, TaskEventKind,
    TaskSummary, is_terminal,
)
from core.task_registry.store import TaskStore


_store: Optional[TaskStore] = None


def _get_store() -> TaskStore:
    global _store
    if _store is None:
        try:
            from base.util import Util
            root = getattr(Util(), "root_path", None)
            db_dir = str(root() / "database" / "tasks.db") if callable(root) else None
            _store = TaskStore(db_path=db_dir)
        except Exception:
            _store = TaskStore()
    return _store


def reset_store_for_test(store: Optional[TaskStore] = None) -> None:
    global _store
    _store = store


def create_task(
    *,
    runtime: TaskRuntime = TaskRuntime.SUBAGENT,
    task_kind: Optional[str] = None,
    owner_session_key: str = "",
    owner_user_id: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> TaskRecord:
    task = TaskRecord(
        task_id=str(uuid.uuid4()),
        runtime=runtime,
        task_kind=task_kind,
        status=TaskStatus.QUEUED,
        owner_session_key=owner_session_key,
        owner_user_id=owner_user_id,
        created_at=time.time(),
        metadata=metadata or {},
        events=[TaskEvent(at=time.time(), kind=TaskEventKind.QUEUED,
                          summary=f"Task queued ({runtime.value})")],
    )
    _get_store().create(task)
    logger.debug("Task created: {} ({})", task.task_id, task_kind or runtime.value)
    return task


def update_task(
    task_id: str,
    status: TaskStatus,
    *,
    result_summary: Optional[str] = None,
    event_summary: Optional[str] = None,
) -> bool:
    event = TaskEvent(
        at=time.time(),
        kind=TaskEventKind(status.value),
        summary=event_summary or f"Status → {status.value}",
    )
    ok = _get_store().update_status(task_id, status, result_summary=result_summary, event=event)
    if ok:
        logger.debug("Task {} → {}", task_id, status.value)
    return ok


def get_task(task_id: str) -> Optional[TaskRecord]:
    return _get_store().get(task_id)


def list_tasks(
    *,
    status: Optional[str] = None,
    owner_key: Optional[str] = None,
    runtime: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[TaskRecord]:
    return _get_store().list(
        status=status, owner_key=owner_key, runtime=runtime,
        limit=limit, offset=offset,
    )


def get_summary() -> TaskSummary:
    return _get_store().summary()


def cleanup_tasks(retention_days: int = 7) -> int:
    return _get_store().cleanup(retention_days)
