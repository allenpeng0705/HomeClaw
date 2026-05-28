"""Tests for core.task_registry — Phase 4: Subagent Registry & Task Lifecycle."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from core.task_registry.types import (
    TaskRecord, TaskStatus, TaskRuntime, TaskEvent, TaskEventKind,
    TaskSummary, is_terminal, TERMINAL_STATUSES,
)
from core.task_registry.store import TaskStore
from core.task_registry.registry import (
    create_task, update_task, get_task, list_tasks,
    get_summary, cleanup_tasks, reset_store_for_test,
)


@pytest.fixture
def store():
    """Create a temporary SQLite store for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = TaskStore(db_path=path)
    reset_store_for_test(s)
    yield s
    reset_store_for_test(None)
    try:
        os.unlink(path)
    except OSError:
        pass


class TestTypes:
    """Task type definitions."""

    def test_task_status_enum(self):
        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.SUCCEEDED == "succeeded"

    def test_is_terminal(self):
        assert is_terminal(TaskStatus.SUCCEEDED)
        assert is_terminal(TaskStatus.FAILED)
        assert not is_terminal(TaskStatus.QUEUED)
        assert not is_terminal(TaskStatus.RUNNING)

    def test_terminal_statuses(self):
        assert len(TERMINAL_STATUSES) == 5

    def test_task_record_defaults(self):
        r = TaskRecord(task_id="t1")
        assert r.status == TaskStatus.QUEUED
        assert r.runtime == TaskRuntime.SUBAGENT
        assert r.events == []

    def test_task_summary(self):
        s = TaskSummary(total=5, active=2, terminal=3, failures=1)
        assert s.total == 5


class TestStore:
    """SQLite task persistence."""

    def test_create_and_get(self, store):
        task = TaskRecord(
            task_id="t1", runtime=TaskRuntime.SKILL,
            task_kind="skill:test", status=TaskStatus.QUEUED,
            owner_session_key="s1", owner_user_id="u1",
        )
        store.create(task)
        retrieved = store.get("t1")
        assert retrieved is not None
        assert retrieved.task_id == "t1"
        assert retrieved.task_kind == "skill:test"

    def test_update_status(self, store):
        task = TaskRecord(task_id="t2", status=TaskStatus.QUEUED)
        store.create(task)
        ok = store.update_status("t2", TaskStatus.RUNNING)
        assert ok
        r = store.get("t2")
        assert r.status == TaskStatus.RUNNING

    def test_update_with_event(self, store):
        task = TaskRecord(task_id="t3", status=TaskStatus.QUEUED)
        store.create(task)
        store.update_status("t3", TaskStatus.SUCCEEDED, result_summary="done",
                            event=TaskEvent(at=time.time(), kind=TaskEventKind.SUCCEEDED))
        r = store.get("t3")
        assert r.status == TaskStatus.SUCCEEDED
        assert r.result_summary == "done"
        assert len(r.events) >= 1

    def test_update_terminal_sets_completed_at(self, store):
        task = TaskRecord(task_id="t4", status=TaskStatus.RUNNING)
        store.create(task)
        store.update_status("t4", TaskStatus.SUCCEEDED)
        r = store.get("t4")
        assert r.completed_at is not None
        assert r.completed_at > 0

    def test_list_by_status(self, store):
        for i, st in enumerate([TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.SUCCEEDED]):
            store.create(TaskRecord(task_id=f"t{i}", status=st))
        running = store.list(status="running")
        assert len(running) == 1
        assert running[0].task_id == "t1"

    def test_summary(self, store):
        store.create(TaskRecord(task_id="a", status=TaskStatus.SUCCEEDED))
        store.create(TaskRecord(task_id="b", status=TaskStatus.RUNNING))
        store.create(TaskRecord(task_id="c", status=TaskStatus.FAILED))
        s = store.summary()
        assert s.total == 3
        assert s.active == 1
        assert s.failures == 1

    def test_cleanup(self, store):
        task = TaskRecord(task_id="old", status=TaskStatus.SUCCEEDED)
        store.create(task)
        store.update_status("old", TaskStatus.SUCCEEDED)
        # Artificially age the completed_at
        conn = store._db_path
        import sqlite3
        c = sqlite3.connect(conn)
        c.execute("UPDATE tasks SET completed_at = ? WHERE task_id = ?",
                  (time.time() - 8 * 86400, "old"))
        c.commit()
        c.close()
        removed = store.cleanup(retention_days=7)
        assert removed == 1
        assert store.get("old") is None


class TestRegistry:
    """Task registry API."""

    def test_create_task(self, store):
        task = create_task(
            runtime=TaskRuntime.SKILL,
            task_kind="skill:test",
            owner_session_key="s1",
        )
        assert task.task_id
        assert task.status == TaskStatus.QUEUED
        assert len(task.events) == 1

    def test_update_task(self, store):
        task = create_task(runtime=TaskRuntime.SUBAGENT)
        ok = update_task(task.task_id, TaskStatus.RUNNING)
        assert ok
        r = get_task(task.task_id)
        assert r.status == TaskStatus.RUNNING

    def test_update_to_terminal(self, store):
        task = create_task(runtime=TaskRuntime.SKILL)
        update_task(task.task_id, TaskStatus.SUCCEEDED, result_summary="All good")
        r = get_task(task.task_id)
        assert r.status == TaskStatus.SUCCEEDED
        assert r.result_summary == "All good"

    def test_list_tasks(self, store):
        create_task(runtime=TaskRuntime.SKILL, task_kind="skill:a")
        create_task(runtime=TaskRuntime.SKILL, task_kind="skill:b")
        tasks = list_tasks()
        assert len(tasks) == 2

    def test_get_summary(self, store):
        create_task(runtime=TaskRuntime.SUBAGENT)
        create_task(runtime=TaskRuntime.SKILL)
        s = get_summary()
        assert s.total == 2
        assert s.active == 2

    def test_get_nonexistent(self, store):
        assert get_task("nonexistent") is None
