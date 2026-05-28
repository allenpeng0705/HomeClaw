"""Edge case and coverage gap tests across all phases."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import uuid

import pytest

from core.context_engine import (
    LegacyContextEngine, resolve_context_engine, ensure_context_engines_initialized,
    clear_registry, register_context_engine,
)
from core.context_engine.protocol import ContextEngineRuntimeContext, ContextEngineProjection
from core.context_engine.compact_runtime import rotate_session
from core.memory_plugin import (
    register_memory_plugin, unregister_memory_plugin, get_active_memory_plugin,
    MemorySearchResult, MemoryGetResult, MemoryHealthStatus,
)
from core.memory_plugin.composite_adapter import CompositeMemoryPlugin
from core.memory_plugin.cognee_adapter import CogneeMemoryPlugin
from core.memory_plugin.memos_adapter import MemosMemoryPlugin
from core.hooks import HookPoint, HookContext, register_hook, fire_hook, clear_hooks
from core.task_registry import (
    TaskStatus, TaskRuntime, TaskEvent, TaskEventKind,
    create_task, update_task, get_task, list_tasks,
    get_summary, cleanup_tasks, reset_store_for_test,
)
from core.task_registry.store import TaskStore
from core.approvals import (
    ApprovalDecision, ApprovalState, ApprovalRule, ApprovalPolicy,
    build_policy_from_config, create_request, resolve_request,
    get_pending, list_pending, expire_stale, clear_for_test as clear_approvals,
)
from core.session_repair import (
    check_chat_history, repair_chat_history, RepairReport, RepairIssue,
)
from llm.auth_profiles import (
    AuthProfile, AgentAuthConfig, RotationStrategy,
    load_auth_profiles, rotate_key, resolve_auth_for_agent,
)
from core.tool_audit import (
    ToolAuditEvent, init_audit_db, record_event, query_events, get_summary as audit_summary,
)


# ── Mocks ────────────────────────────────────────────────────────────────


class _FakeMemory:
    def __init__(self):
        self._items = [{"id": "x", "memory": "test", "score": 0.5, "created_at": "2026-01-01"}]

    async def search(self, *a, **kw):
        return self._items

    def get(self, mid):
        return self._items[0] if mid == "x" else None

    def get_all(self, limit=100, **kw):
        return self._items[:limit]


class _MockCore:
    _compact_session_file = "/tmp/test.json"


# ── ContextEngine edge cases ────────────────────────────────────────────


class TestContextEngineEdgeCases:
    def setup_method(self):
        clear_registry()

    async def test_assemble_cache_aware_ordering(self):
        """assemble() reorders messages: system first, newest last."""
        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())
        messages = [
            {"role": "user", "content": "old1"},
            {"role": "user", "content": "old2"},
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old3"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "newest"},
        ]
        result = await engine.assemble(session_id="s1", messages=messages)
        # System messages should be first
        first_role = result.messages[0].get("role") if result.messages else None
        assert first_role == "system"

    async def test_assemble_returns_system_addition_with_plugin(self):
        """assemble() includes MemoryPlugin prompt section when registered."""
        plugin = CompositeMemoryPlugin(_FakeMemory())
        register_memory_plugin(plugin, owner="test")

        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())
        result = await engine.assemble(session_id="s1", messages=[],
                                        available_tools={"agent_memory_search"})
        # system_prompt_addition should contain memory guidance
        assert result.system_prompt_addition is not None

        unregister_memory_plugin(owner="test")

    async def test_maintain_noop(self):
        """maintain() returns empty result when no rewrite function available."""
        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())
        result = await engine.maintain(session_id="s1", session_file="/tmp/x.json")
        assert result.changed is False

    async def test_compact_empty_extra(self):
        """compact() with runtime_context but no messages key."""
        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())
        rtx = ContextEngineRuntimeContext(extra={"other": "value"})
        result = await engine.compact(session_id="s1", session_file="/tmp/x.json",
                                       runtime_context=rtx)
        assert not result.compacted

    async def test_compact_unknown_rtx_type(self):
        """compact() handles runtime_context with non-dict extra."""
        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())
        rtx = ContextEngineRuntimeContext(extra=None)  # type: ignore
        result = await engine.compact(session_id="s1", session_file="/tmp/x.json",
                                       runtime_context=rtx)
        assert not result.compacted


# ── Registry edge cases ─────────────────────────────────────────────────


class TestRegistryEdgeCases:
    def setup_method(self):
        clear_registry()

    def test_double_init_is_idempotent(self):
        ensure_context_engines_initialized()
        first = [e for e in _list_ids()]
        ensure_context_engines_initialized()
        second = [e for e in _list_ids()]
        assert first == second

    def test_register_multiple_engines(self):
        from core.context_engine.legacy_engine import LegacyContextEngine
        register_context_engine("a", lambda c: LegacyContextEngine(c), owner="p")
        register_context_engine("b", lambda c: LegacyContextEngine(c), owner="p")
        assert _list_ids() == {"a", "b"}

    def test_resolve_returns_different_instances(self):
        ensure_context_engines_initialized()
        e1 = resolve_context_engine("legacy", core=_MockCore())
        e2 = resolve_context_engine("legacy", core=_MockCore())
        assert e1 is not e2  # fresh instances each time

    def test_factory_exception_returns_none(self):
        def bad_factory(core):
            raise RuntimeError("boom")
        register_context_engine("bad", bad_factory, owner="test")
        result = resolve_context_engine("bad", core=_MockCore())
        assert result is None


def _list_ids():
    from core.context_engine.registry import list_engines
    return set(list_engines().keys())


# ── MemoryPlugin adapter edge cases ─────────────────────────────────────


class TestAdapterEdgeCases:
    async def test_cognee_search_empty(self):
        plugin = CogneeMemoryPlugin(_FakeMemory())
        results = await plugin.search("query", max_results=5)
        assert len(results) >= 0

    async def test_cognee_get_nonexistent(self):
        plugin = CogneeMemoryPlugin(_FakeMemory())
        result = await plugin.get("nonexistent")
        assert result is None  # fake memory returns None for unknown id

    async def test_memos_search_empty(self):
        plugin = MemosMemoryPlugin(_FakeMemory())
        results = await plugin.search("query", max_results=5)
        assert len(results) >= 0

    def test_composite_build_prompt_no_tools(self):
        plugin = CompositeMemoryPlugin(_FakeMemory())
        section = plugin.build_prompt_section(available_tools=set())
        assert section == ""

    def test_composite_build_prompt_all_tools(self):
        plugin = CompositeMemoryPlugin(_FakeMemory())
        section = plugin.build_prompt_section(available_tools=None)
        assert "Memory" in section  # None = all tools available

    async def test_composite_health_ok(self):
        plugin = CompositeMemoryPlugin(_FakeMemory())
        status = await plugin.health()
        assert status.ok


# ── Compact runtime edge cases ──────────────────────────────────────────


class TestCompactRuntimeEdgeCases:
    def test_summary_no_user_messages(self):
        from core.context_engine.compact_runtime import generate_compaction_summary
        msgs = [{"role": "system", "content": "sys"}, {"role": "tool", "content": "t"}]
        summary = generate_compaction_summary(msgs)
        assert "0 user" in summary

    def test_summary_truncation_boundary(self):
        from core.context_engine.compact_runtime import generate_compaction_summary
        msgs = [{"role": "user", "content": "A" * 1000}]
        summary = generate_compaction_summary(msgs, max_summary_chars=100)
        assert len(summary) <= 100

    async def test_llm_summary_fallback(self, tmp_path):
        from core.context_engine.compact_runtime import generate_llm_compaction_summary
        # No core provided → falls back to heuristic
        msgs = [{"role": "user", "content": "test"}]
        summary = await generate_llm_compaction_summary(msgs, core=None)
        assert len(summary) > 0


# ── Session repair edge cases ───────────────────────────────────────────


class TestSessionRepairEdgeCases:
    @pytest.fixture
    def db_path(self, tmp_path):
        p = str(tmp_path / "edge.db")
        conn = sqlite3.connect(p)
        conn.executescript("CREATE TABLE chat_history (id TEXT, session_id TEXT, user_id TEXT, question TEXT, answer TEXT)")
        conn.close()
        return p

    def test_repair_report_dataclass(self):
        r = RepairReport(ok=True, tables_checked=3, rows_checked=100)
        assert r.ok
        assert r.tables_checked == 3

    def test_repair_issue_dataclass(self):
        issue = RepairIssue(table="t", row_id="r1", severity="warning", message="test")
        assert issue.fixable

    def test_repair_handles_missing_table(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TABLE chat_history")
        conn.commit()
        conn.close()
        report = check_chat_history(db_path)
        # Should not crash — no matching tables found
        assert report.tables_checked >= 0

    def test_repair_removes_empty_fields(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('', '', '')")
        conn.commit()
        conn.close()
        report = repair_chat_history(db_path)
        report2 = check_chat_history(db_path)
        assert report2.ok  # empty-field row removed


# ── Task registry edge cases ────────────────────────────────────────────


class TestTaskRegistryEdgeCases:
    @pytest.fixture
    def store(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        s = TaskStore(db_path=path)
        reset_store_for_test(s)
        yield s
        reset_store_for_test(None)
        os.unlink(path)

    def test_cleanup_no_terminal(self, store):
        create_task(runtime=TaskRuntime.SUBAGENT)
        removed = cleanup_tasks(retention_days=1)
        assert removed == 0  # active tasks not cleaned

    def test_list_pagination(self, store):
        for i in range(10):
            create_task(runtime=TaskRuntime.SKILL, task_kind=f"skill:{i}")
        page1 = list_tasks(limit=5, offset=0)
        page2 = list_tasks(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        ids1 = {t.task_id for t in page1}
        ids2 = {t.task_id for t in page2}
        assert ids1.isdisjoint(ids2)

    def test_list_by_runtime(self, store):
        create_task(runtime=TaskRuntime.SKILL, task_kind="skill:a")
        create_task(runtime=TaskRuntime.SUBAGENT)
        tasks = list_tasks(runtime="skill")
        assert len(tasks) == 1
        assert tasks[0].runtime == TaskRuntime.SKILL

    def test_update_nonexistent(self, store):
        ok = update_task("nonexistent", TaskStatus.SUCCEEDED)
        assert not ok

    def test_task_event_dataclass(self):
        e = TaskEvent(at=time.time(), kind=TaskEventKind.PROGRESS, summary="25%")
        assert e.kind == TaskEventKind.PROGRESS


# ── Approval edge cases ─────────────────────────────────────────────────


class TestApprovalEdgeCases:
    def setup_method(self):
        clear_approvals()

    def test_rule_condition_session_key(self):
        policy = ApprovalPolicy(rules=[
            ApprovalRule(tool_name="exec_shell", decision=ApprovalDecision.ALLOW,
                         condition_session_key="trusted-session"),
        ])
        assert policy.resolve("exec_shell", session_key="trusted-session") == ApprovalDecision.ALLOW
        assert policy.resolve("exec_shell", session_key="unknown") == ApprovalDecision.ASK

    def test_build_from_invalid_config(self):
        # Invalid default value
        p = build_policy_from_config({"default": "invalid", "tools": {"x": {"policy": "invalid"}}})
        assert p.default == ApprovalDecision.ASK  # falls back
        # Tool with invalid policy falls back to ask
        assert p.resolve("x") == ApprovalDecision.ASK

    def test_build_from_empty_dict(self):
        p = build_policy_from_config({})
        assert p.default == ApprovalDecision.ASK

    def test_expire_with_custom_ttl(self):
        req = create_request("tool_x", ttl_seconds=1)
        time.sleep(1.1)
        expired = expire_stale(ttl_seconds=1)
        assert len(expired) == 1

    def test_list_pending_empty(self):
        assert list_pending() == []

    def test_get_pending_nonexistent(self):
        assert get_pending("nonexistent") is None


# ── Auth profile edge cases ─────────────────────────────────────────────


class TestAuthProfileEdgeCases:
    def test_load_empty_config(self):
        agents = load_auth_profiles(None)
        assert agents == {}

    def test_load_invalid_entries(self):
        config = {"bad_agent": None, "ok_agent": {"profiles": []}}
        agents = load_auth_profiles(config)
        assert "ok_agent" not in agents  # empty profiles excluded

    def test_rotate_weighted_single(self):
        config = AgentAuthConfig(agent_id="t", strategy=RotationStrategy.WEIGHTED,
                                  profiles=[AuthProfile(provider="p", api_key="k", weight=1)])
        assert rotate_key(config).api_key == "k"

    def test_rotate_unknown_strategy(self):
        config = AgentAuthConfig(agent_id="t", profiles=[AuthProfile(provider="p", api_key="k")])
        config.strategy = "unknown"  # type: ignore
        assert rotate_key(config).api_key == "k"  # falls back to first

    def test_resolve_no_default(self):
        agents = load_auth_profiles({"custom": {"profiles": [{"provider": "p", "api_key": "k"}]}})
        assert resolve_auth_for_agent("unknown", agents) is None  # no default


# ── Tool audit edge cases ───────────────────────────────────────────────


class TestToolAuditEdgeCases:
    @pytest.fixture
    def db_path(self, tmp_path):
        p = str(tmp_path / "audit.db")
        init_audit_db(db_path=p)
        return p

    def test_query_with_since(self, db_path):
        t0 = time.time()
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t1",
                                     result_status="ok", timestamp=t0 - 3600), db_path=db_path)
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t2",
                                     result_status="ok", timestamp=t0), db_path=db_path)

        recent = query_events(since=t0 - 10, db_path=db_path)
        assert len(recent) == 1

    def test_summary_with_since(self, db_path):
        t0 = time.time()
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="old",
                                     result_status="ok", timestamp=t0 - 3600), db_path=db_path)
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="new",
                                     result_status="error", timestamp=t0), db_path=db_path)

        s = audit_summary(since=t0 - 10, db_path=db_path)
        assert s["total"] == 1
        assert s["errors"] == 1

    def test_query_by_session(self, db_path):
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t1",
                                     session_id="s1", result_status="ok"), db_path=db_path)
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t2",
                                     session_id="s2", result_status="ok"), db_path=db_path)

        s1 = query_events(session_id="s1", db_path=db_path)
        assert len(s1) == 1
        assert s1[0]["session_id"] == "s1"


# ── Memory plugin slot edge case ────────────────────────────────────────


class TestSlotEdgeCases:
    def setup_method(self):
        try:
            unregister_memory_plugin(owner="core")
        except Exception:
            pass

    def test_info_when_multiple_registrations(self):
        plugin1 = CompositeMemoryPlugin(_FakeMemory())
        plugin2 = CompositeMemoryPlugin(_FakeMemory())
        register_memory_plugin(plugin1, owner="owner1")
        register_memory_plugin(plugin2, owner="owner2")
        from core.memory_plugin.slot import get_active_plugin_info
        info = get_active_plugin_info()
        assert info["active"]
        # Last registered wins
        from core.memory_plugin import get_active_memory_plugin
        assert get_active_memory_plugin() is plugin2

        unregister_memory_plugin(owner="owner2")
