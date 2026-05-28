"""
Task registry — Phase 4: Subagent Registry & Task Lifecycle.

Provides structured tracking for subagent invocations and long-running
tasks with a persisted lifecycle (queued → running → succeeded/failed/…).

Usage:
    from core.task_registry import create_task, update_task, list_tasks
    task = create_task(runtime=TaskRuntime.SUBAGENT, task_kind="skill:vmprint")
    update_task(task.task_id, TaskStatus.RUNNING)
    update_task(task.task_id, TaskStatus.SUCCEEDED, result_summary="Done.")
"""

from core.task_registry.types import (
    TaskRecord, TaskStatus, TaskRuntime, TaskEvent, TaskEventKind,
    TaskSummary, is_terminal,
)
from core.task_registry.registry import (
    create_task, update_task, get_task, list_tasks,
    get_summary, cleanup_tasks, reset_store_for_test,
)

__all__ = [
    "TaskRecord", "TaskStatus", "TaskRuntime", "TaskEvent", "TaskEventKind",
    "TaskSummary", "is_terminal",
    "create_task", "update_task", "get_task", "list_tasks",
    "get_summary", "cleanup_tasks", "reset_store_for_test",
]
