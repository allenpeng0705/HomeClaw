"""Tests for Phase 6: Session repair, auth profiles, and tool audit."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import uuid

import pytest

from core.session_repair import check_chat_history, repair_chat_history, RepairReport
from llm.auth_profiles import (
    AuthProfile, AgentAuthConfig, RotationStrategy,
    load_auth_profiles, rotate_key, resolve_auth_for_agent,
)
from core.tool_audit import (
    ToolAuditEvent, init_audit_db, record_event, query_events, get_summary,
)


# ── Session repair tests ───────────────────────────────────────────────


class TestSessionRepair:
    """Chat history integrity checks and repair."""

    @pytest.fixture
    def db_path(self, tmp_path):
        p = str(tmp_path / "chat.db")
        conn = sqlite3.connect(p)
        conn.executescript("""
            CREATE TABLE chat_history (id TEXT, session_id TEXT, user_id TEXT,
                                       question TEXT, answer TEXT);
            CREATE TABLE chat_sessions (id TEXT, user_id TEXT, friend_id TEXT);
        """)
        conn.close()
        return p

    def test_check_clean_db(self, db_path):
        report = check_chat_history(db_path)
        assert report.ok
        assert len(report.issues) == 0

    def test_check_duplicate_ids(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('dup', 's1', 'u1')")
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('dup', 's2', 'u2')")
        conn.commit()
        conn.close()

        report = check_chat_history(db_path)
        assert not report.ok
        assert any("Duplicate id" in i.message for i in report.issues)

    def test_check_empty_fields(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('a1', '', '')")
        conn.commit()
        conn.close()

        report = check_chat_history(db_path)
        assert any("empty session_id" in i.message for i in report.issues)

    def test_check_empty_content(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO chat_history (id, session_id, user_id, question, answer) VALUES ('a1', 's1', 'u1', '', '')")
        conn.commit()
        conn.close()

        report = check_chat_history(db_path)
        assert any("empty question and answer" in i.message for i in report.issues)

    def test_check_nonexistent_db(self):
        report = check_chat_history("/nonexistent/path/db.sqlite")
        assert not report.ok
        assert any("Failed to open" in i.message for i in report.issues)

    def test_repair_removes_duplicates(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('dup', 's1', 'u1')")
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('dup', 's2', 'u2')")
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('uniq', 's3', 'u3')")
        conn.commit()
        conn.close()

        report = repair_chat_history(db_path)
        assert report.fixes_applied >= 1

        # Verify only one 'dup' remains
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM chat_history WHERE id = 'dup'").fetchone()[0]
        assert rows == 1
        conn.close()

    def test_repair_dry_run(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('dup', 's1', 'u1')")
        conn.execute("INSERT INTO chat_history (id, session_id, user_id) VALUES ('dup', 's2', 'u2')")
        conn.commit()
        conn.close()

        report = repair_chat_history(db_path, dry_run=True)
        assert report.fixes_applied == 0  # dry run, no changes
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM chat_history WHERE id = 'dup'").fetchone()[0]
        assert rows == 2  # both still there
        conn.close()


# ── Auth profile tests ─────────────────────────────────────────────────


class TestAuthProfiles:
    """API key rotation engine."""

    def test_round_robin(self):
        config = AgentAuthConfig(agent_id="test", strategy=RotationStrategy.ROUND_ROBIN, profiles=[
            AuthProfile(provider="p1", api_key="k1"),
            AuthProfile(provider="p2", api_key="k2"),
            AuthProfile(provider="p3", api_key="k3"),
        ])
        assert rotate_key(config).api_key == "k1"
        assert rotate_key(config).api_key == "k2"
        assert rotate_key(config).api_key == "k3"
        assert rotate_key(config).api_key == "k1"  # wraps

    def test_fallback(self):
        config = AgentAuthConfig(agent_id="test", strategy=RotationStrategy.FALLBACK, profiles=[
            AuthProfile(provider="primary", api_key="pk"),
            AuthProfile(provider="backup", api_key="bk"),
        ])
        # Always returns primary
        for _ in range(5):
            assert rotate_key(config).api_key == "pk"

    def test_random(self):
        config = AgentAuthConfig(agent_id="test", strategy=RotationStrategy.RANDOM, profiles=[
            AuthProfile(provider="p", api_key="k1"),
        ])
        assert rotate_key(config).api_key == "k1"

    def test_weighted(self):
        config = AgentAuthConfig(agent_id="test", strategy=RotationStrategy.WEIGHTED, profiles=[
            AuthProfile(provider="heavy", api_key="hk", weight=100),
            AuthProfile(provider="light", api_key="lk", weight=1),
        ])
        # Heavy should win most of the time
        results = [rotate_key(config).api_key for _ in range(50)]
        assert results.count("hk") > results.count("lk")

    def test_load_from_config(self):
        config = {
            "default": {
                "strategy": "round_robin",
                "profiles": [
                    {"provider": "deepseek", "api_key": "sk-aaa", "label": "primary"},
                    {"provider": "deepseek", "api_key": "sk-bbb", "label": "backup"},
                ],
            },
            "clawcode": {
                "strategy": "fallback",
                "profiles": [{"provider": "openai", "api_key": "sk-ccc"}],
            },
        }
        agents = load_auth_profiles(config)
        assert len(agents) == 2
        assert agents["default"].profiles[0].api_key == "sk-aaa"
        assert agents["clawcode"].strategy == RotationStrategy.FALLBACK

    def test_resolve_agent(self):
        agents = load_auth_profiles({
            "default": {"strategy": "round_robin", "profiles": [
                {"provider": "p", "api_key": "key-default"}]},
            "custom": {"strategy": "fallback", "profiles": [
                {"provider": "p", "api_key": "key-custom"}]},
        })
        assert resolve_auth_for_agent("custom", agents).api_key == "key-custom"
        assert resolve_auth_for_agent("unknown", agents).api_key == "key-default"

    def test_empty_profiles(self):
        config = AgentAuthConfig(agent_id="test", profiles=[])
        assert rotate_key(config) is None


# ── Tool audit tests ───────────────────────────────────────────────────


class TestToolAudit:
    """Structured audit events for tool executions."""

    @pytest.fixture
    def db_path(self, tmp_path):
        p = str(tmp_path / "audit.db")
        init_audit_db(db_path=p)
        return p

    def test_record_and_query(self, db_path):
        event = ToolAuditEvent(
            event_id=str(uuid.uuid4()),
            tool_name="file_read",
            agent_id="clawcode",
            session_id="s1",
            result_status="ok",
            result_summary="Read 100 lines",
            duration_ms=42.0,
        )
        record_event(event, db_path=db_path)

        results = query_events(tool_name="file_read", db_path=db_path)
        assert len(results) == 1
        assert results[0]["result_status"] == "ok"

    def test_query_by_agent(self, db_path):
        for i in range(3):
            record_event(ToolAuditEvent(
                event_id=str(uuid.uuid4()),
                tool_name="test",
                agent_id=f"agent_{i % 2}",
                result_status="ok",
            ), db_path=db_path)

        a0 = query_events(agent_id="agent_0", db_path=db_path)
        a1 = query_events(agent_id="agent_1", db_path=db_path)
        assert len(a0) >= 1
        assert len(a1) >= 1

    def test_query_by_status(self, db_path):
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t1",
                                     result_status="error"), db_path=db_path)
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t2",
                                     result_status="ok"), db_path=db_path)

        errors = query_events(result_status="error", db_path=db_path)
        assert len(errors) == 1

    def test_get_summary(self, db_path):
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t1",
                                     result_status="ok"), db_path=db_path)
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t2",
                                     result_status="error"), db_path=db_path)
        record_event(ToolAuditEvent(event_id=str(uuid.uuid4()), tool_name="t1",
                                     result_status="denied"), db_path=db_path)

        summary = get_summary(db_path=db_path)
        assert summary["total"] == 3
        assert summary["errors"] == 1
        assert summary["denied"] == 1
        assert summary["by_tool"]["t1"] == 2
