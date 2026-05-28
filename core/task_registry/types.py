"""
Task registry types — Phase 4: Subagent Registry & Task Lifecycle.

Inspired by OpenClaw's src/tasks/task-registry.types.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    LOST = "lost"


class TaskRuntime(str, Enum):
    SUBAGENT = "subagent"
    SKILL = "skill"
    CRON = "cron"
    MANUAL = "manual"


class TaskEventKind(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    PROGRESS = "progress"


@dataclass
class TaskEvent:
    at: float  # unix timestamp
    kind: TaskEventKind
    summary: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


@dataclass
class TaskRecord:
    task_id: str
    runtime: TaskRuntime = TaskRuntime.SUBAGENT
    task_kind: Optional[str] = None       # e.g., "skill:vimprint", "cron:daily_brief"
    status: TaskStatus = TaskStatus.QUEUED
    owner_session_key: str = ""            # who created the task
    owner_user_id: str = ""
    created_at: float = 0.0               # unix timestamp
    updated_at: float = 0.0
    completed_at: Optional[float] = None
    events: List[TaskEvent] = field(default_factory=list)
    result_summary: Optional[str] = None
    child_session_id: Optional[str] = None  # subagent session, if spawned
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskSummary:
    total: int = 0
    active: int = 0
    terminal: int = 0
    failures: int = 0
    by_status: Dict[str, int] = field(default_factory=dict)
    by_runtime: Dict[str, int] = field(default_factory=dict)


TERMINAL_STATUSES: set[TaskStatus] = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.TIMED_OUT,
    TaskStatus.CANCELLED,
    TaskStatus.LOST,
}


def is_terminal(status: TaskStatus) -> bool:
    return status in TERMINAL_STATUSES
