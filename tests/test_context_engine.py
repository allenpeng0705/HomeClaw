"""Tests for core.context_engine — Phase 0: ContextEngine protocol, registry, legacy engine, and compact runtime."""

from __future__ import annotations

import pytest

from core.context_engine import (
    # Protocol
    ContextEngine,
    ContextEngineInfo,
    ContextEngineHostCapability,
    ContextEngineOperation,
    ContextEngineHostRequirements,
    ContextEngineProjection,
    ContextProjectionMode,
    ContextEnginePromptCacheInfo,
    ContextEngineRuntimeContext,
    TurnMaintenanceMode,
    PromptAuthority,
    SubagentEndReason,
    AssembleResult,
    CompactResult,
    IngestResult,
    IngestBatchResult,
    BootstrapResult,
    TranscriptRewriteReplacement,
    TranscriptRewriteRequest,
    TranscriptRewriteResult,
    ContextEngineMaintenanceResult,
    SubagentSpawnPreparation,
    # Registry
    register_context_engine,
    unregister_context_engine,
    resolve_context_engine,
    list_engines,
    is_registered,
    clear_registry,
    ensure_context_engines_initialized,
    # Legacy engine
    LegacyContextEngine,
    # Compact runtime
    generate_compaction_summary,
    create_compaction_system_message,
    rotate_session_id,
)


# ── Mocks ──────────────────────────────────────────────────────────────────


class _MockCore:
    """Minimal core mock for LegacyContextEngine tests."""
    def __init__(self, compaction_config: dict | None = None):
        self._compaction = compaction_config or {}

    # Simulate Util().get_core_metadata()
    # The engine uses `from base.util import Util` internally,
    # so we patch via monkeypatch rather than attribute access.

    _compact_session_file: str | None = None


# ── Protocol tests ─────────────────────────────────────────────────────────


class TestProtocol:
    """ContextEngine ABC and result type tests."""

    def test_enums(self):
        assert ContextEngineHostCapability.COMPACT == "compact"
        assert ContextEngineOperation.AGENT_RUN == "agent-run"
        assert ContextProjectionMode.PER_TURN == "per_turn"
        assert PromptAuthority.ASSEMBLED == "assembled"
        assert SubagentEndReason.COMPLETED == "completed"
        assert TurnMaintenanceMode.FOREGROUND == "foreground"

    def test_assemble_result_defaults(self):
        ar = AssembleResult()
        assert ar.messages == []
        assert ar.estimated_tokens == 0
        assert ar.prompt_authority == PromptAuthority.ASSEMBLED
        assert ar.system_prompt_addition is None

    def test_assemble_result_with_data(self):
        ar = AssembleResult(
            messages=[{"role": "user", "content": "hi"}],
            estimated_tokens=5,
            system_prompt_addition="## Memory\n...",
        )
        assert len(ar.messages) == 1
        assert ar.estimated_tokens == 5
        assert ar.system_prompt_addition == "## Memory\n..."

    def test_compact_result_defaults(self):
        cr = CompactResult()
        assert cr.ok is False
        assert cr.compacted is False
        assert cr.tokens_before == 0

    def test_compact_result_after_compaction(self):
        cr = CompactResult(
            ok=True, compacted=True, tokens_before=1000, tokens_after=500,
            summary="Compacted 50 messages.",
            session_id="abc-c1",
        )
        assert cr.ok
        assert cr.compacted
        assert cr.tokens_before == 1000
        assert cr.tokens_after == 500
        assert cr.session_id == "abc-c1"

    def test_ingest_result(self):
        ir = IngestResult(ingested=True)
        assert ir.ingested
        assert IngestResult().ingested is False

    def test_ingest_batch_result(self):
        br = IngestBatchResult(ingested_count=3)
        assert br.ingested_count == 3

    def test_bootstrap_result(self):
        br = BootstrapResult(bootstrapped=True, imported_messages=42)
        assert br.bootstrapped
        assert br.imported_messages == 42

    def test_context_engine_info(self):
        info = ContextEngineInfo(id="test", name="Test Engine", version="2.0.0")
        assert info.id == "test"
        assert info.name == "Test Engine"
        assert info.version == "2.0.0"
        assert info.owns_compaction is False

    def test_context_engine_info_with_host_requirements(self):
        req = ContextEngineHostRequirements(
            required_capabilities=[ContextEngineHostCapability.COMPACT],
        )
        info = ContextEngineInfo(
            id="rich", name="Rich Engine",
            host_requirements={ContextEngineOperation.AGENT_RUN: req},
            owns_compaction=True,
            turn_maintenance_mode=TurnMaintenanceMode.BACKGROUND,
        )
        assert info.owns_compaction is True
        assert info.turn_maintenance_mode == TurnMaintenanceMode.BACKGROUND
        assert ContextEngineOperation.AGENT_RUN in info.host_requirements

    def test_context_engine_runtime_context(self):
        rtx = ContextEngineRuntimeContext(
            token_budget=100000,
            current_token_count=50000,
            allow_deferred_compaction_execution=True,
            extra={"messages": [], "custom": "value"},
        )
        assert rtx.token_budget == 100000
        assert rtx.current_token_count == 50000
        assert rtx.allow_deferred_compaction_execution
        assert rtx.extra["custom"] == "value"

    def test_transcript_rewrite_types(self):
        repl = TranscriptRewriteReplacement(
            entry_id="e1",
            message={"role": "system", "content": "Compacted."},
        )
        req = TranscriptRewriteRequest(replacements=[repl])
        result = TranscriptRewriteResult(changed=True, bytes_freed=1024, rewritten_entries=1)
        assert req.replacements[0].entry_id == "e1"
        assert result.changed
        assert result.bytes_freed == 1024

    def test_context_engine_is_abstract(self):
        """Verify ContextEngine cannot be instantiated directly."""
        import inspect
        assert inspect.isabstract(ContextEngine)

    def test_context_engine_has_required_methods(self):
        """Verify required abstract methods are defined."""
        required = {"info", "ingest", "assemble", "compact"}
        for name in required:
            assert hasattr(ContextEngine, name), f"Missing required method: {name}"

    def test_subagent_types(self):
        prep = SubagentSpawnPreparation()
        assert prep.rollback is None

        callable_rollback = lambda: None
        prep2 = SubagentSpawnPreparation(rollback=callable_rollback)
        assert prep2.rollback is callable_rollback


# ── Registry tests ──────────────────────────────────────────────────────────


class FakeEngine:
    """Minimal ContextEngine for registry tests — doesn't need to be fully functional."""
    def __init__(self, core=None):
        self.core = core
        self._info = ContextEngineInfo(id="fake", name="Fake Engine")

    @property
    def info(self):
        return self._info

    async def ingest(self, **kwargs):
        return IngestResult()

    async def assemble(self, **kwargs):
        return AssembleResult()

    async def compact(self, **kwargs):
        return CompactResult()


class TestRegistry:
    """ContextEngine registry tests."""

    def setup_method(self):
        clear_registry()

    def test_initialization(self):
        ensure_context_engines_initialized()
        assert "legacy" in list_engines()
        assert is_registered("legacy")
        assert list_engines()["legacy"] == "core"

    def test_double_init_is_idempotent(self):
        ensure_context_engines_initialized()
        first = list_engines()
        ensure_context_engines_initialized()
        assert list_engines() == first

    def test_register_custom_engine(self):
        ok = register_context_engine("custom", lambda c: FakeEngine(c), owner="plugin-x")
        assert ok
        assert is_registered("custom")
        assert list_engines()["custom"] == "plugin-x"

    def test_double_register_blocked(self):
        register_context_engine("a", lambda c: FakeEngine(c), owner="owner1")
        ok = register_context_engine("a", lambda c: FakeEngine(c), owner="owner2")
        assert not ok

    def test_same_owner_refresh(self):
        register_context_engine("a", lambda c: FakeEngine(c), owner="me")
        ok = register_context_engine("a", lambda c: FakeEngine(c), owner="me", allow_same_owner_refresh=True)
        assert ok

    def test_resolve_returns_instance(self):
        register_context_engine("fake", lambda c: FakeEngine(c), owner="core")
        engine = resolve_context_engine("fake", core=_MockCore())
        assert engine is not None
        assert isinstance(engine, FakeEngine)
        assert engine.info.id == "fake"

    def test_resolve_unknown_returns_none(self):
        engine = resolve_context_engine("nonexistent", core=_MockCore())
        assert engine is None

    def test_unregister(self):
        register_context_engine("x", lambda c: FakeEngine(c), owner="me")
        ok = unregister_context_engine("x", owner="me")
        assert ok
        assert not is_registered("x")

    def test_unregister_wrong_owner(self):
        register_context_engine("x", lambda c: FakeEngine(c), owner="alice")
        ok = unregister_context_engine("x", owner="bob")
        assert not ok
        assert is_registered("x")

    def test_unregister_nonexistent(self):
        assert not unregister_context_engine("nope", owner="me")

    def test_list_engines_multiple(self):
        register_context_engine("a", lambda c: FakeEngine(c), owner="p1")
        register_context_engine("b", lambda c: FakeEngine(c), owner="p2")
        engines = list_engines()
        assert len(engines) == 2
        assert engines["a"] == "p1"
        assert engines["b"] == "p2"

    def test_clear_registry(self):
        register_context_engine("a", lambda c: FakeEngine(c), owner="p")
        clear_registry()
        assert not list_engines()

    def test_legacy_engine_resolves(self):
        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())
        assert engine is not None
        assert engine.info.id == "legacy"
        assert engine.info.name == "Legacy Context Engine"
        assert isinstance(engine, LegacyContextEngine)


# ── LegacyContextEngine tests ──────────────────────────────────────────────


class TestLegacyContextEngine:
    """LegacyContextEngine: ingest, assemble, compact."""

    def setup_method(self):
        clear_registry()

    def _engine(self, core=None):
        """Create LegacyContextEngine with optional mock core."""
        if core is None:
            core = _MockCore()
        return LegacyContextEngine(core)

    async def test_info(self):
        engine = self._engine()
        assert engine.info.id == "legacy"
        assert engine.info.version == "1.0.0"

    async def test_ingest_is_noop(self):
        engine = self._engine()
        result = await engine.ingest(
            session_id="s1",
            message={"role": "user", "content": "hello"},
        )
        assert result.ingested is False  # No-op: session manager handles persistence

    async def test_assemble_passthrough(self):
        engine = self._engine()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        result = await engine.assemble(session_id="s1", messages=messages)
        assert result.messages == messages
        assert result.estimated_tokens > 0

    async def test_assemble_with_tools_and_model(self):
        engine = self._engine()
        result = await engine.assemble(
            session_id="s1",
            messages=[{"role": "user", "content": "test"}],
            available_tools={"read", "write"},
            model="deepseek-v4",
        )
        assert len(result.messages) == 1

    async def test_compact_no_messages(self):
        engine = self._engine()
        rtx = ContextEngineRuntimeContext(extra={"messages": []})
        result = await engine.compact(
            session_id="s1", session_file="/tmp/s.json",
            runtime_context=rtx,
        )
        assert result.compacted is False
        assert "no messages" in (result.reason or "")

    async def test_compact_disabled(self):
        engine = self._engine()
        rtx = ContextEngineRuntimeContext(extra={
            "messages": [{"role": "user", "content": "hi"}] * 50,
        })
        result = await engine.compact(
            session_id="s1", session_file="/tmp/s.json",
            runtime_context=rtx,
        )
        # Compaction is disabled by default (no config)
        assert result.compacted is False
        assert "disabled" in (result.reason or "")

    async def test_compact_below_threshold(self):
        engine = self._engine()
        rtx = ContextEngineRuntimeContext(extra={
            "messages": [{"role": "user", "content": "hi"}] * 5,
        })
        result = await engine.compact(
            session_id="s1", session_file="/tmp/s.json",
            runtime_context=rtx,
        )
        # 5 messages < default threshold of 30
        assert result.compacted is False

    async def test_compact_without_runtime_context(self):
        engine = self._engine()
        result = await engine.compact(
            session_id="s1", session_file="/tmp/s.json",
        )
        assert result.compacted is False
        assert "no messages" in (result.reason or "")

    async def test_ingest_batch_delegates_to_ingest(self):
        engine = self._engine()
        result = await engine.ingest_batch(
            session_id="s1",
            messages=[
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ],
        )
        # ingest is no-op, so all 3 return ingested=False
        assert result.ingested_count == 0

    async def test_after_turn_noop(self):
        engine = self._engine()
        # Should not raise
        await engine.after_turn(
            session_id="s1", session_file="/tmp/s.json",
            messages=[], pre_prompt_message_count=0,
        )

    async def test_dispose_noop(self):
        engine = self._engine()
        await engine.dispose()  # Should not raise

    async def test_subagent_methods_noop(self):
        engine = self._engine()
        prep = await engine.prepare_subagent_spawn(
            parent_session_key="p", child_session_key="c",
        )
        assert prep is None
        await engine.on_subagent_ended(
            child_session_key="c",
            reason=SubagentEndReason.COMPLETED,
        )


# ── Compact runtime tests ──────────────────────────────────────────────────


class TestCompactRuntime:
    """Session rotation, summary generation, system message creation."""

    def test_rotate_session_id_first_time(self):
        assert rotate_session_id("abc123") == "abc123-c1"

    def test_rotate_session_id_second_time(self):
        assert rotate_session_id("abc123-c1") == "abc123-c2"

    def test_rotate_session_id_many_compactions(self):
        assert rotate_session_id("abc123-c9") == "abc123-c10"

    def test_rotate_session_id_no_existing_suffix(self):
        assert rotate_session_id("session-xyz") == "session-xyz-c1"

    def test_rotate_session_id_with_dashes(self):
        sid = rotate_session_id("user-123-abc")
        assert sid == "user-123-abc-c1"

    def test_generate_compaction_summary_empty(self):
        assert generate_compaction_summary([]) == ""

    def test_generate_compaction_summary_basic(self):
        messages = [
            {"role": "user", "content": "What is the capital?"},
            {"role": "assistant", "content": "Paris."},
        ]
        summary = generate_compaction_summary(messages)
        assert "Compacted 2 messages" in summary
        assert "What is the capital?" in summary

    def test_generate_compaction_summary_counts_roles(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "tool", "content": "result"},
        ]
        summary = generate_compaction_summary(messages)
        assert "2 user" in summary
        assert "1 assistant" in summary
        assert "1 tool" in summary

    def test_generate_compaction_summary_truncates_long_content(self):
        messages = [
            {"role": "user", "content": "A" * 2000},
        ]
        summary = generate_compaction_summary(messages, max_summary_chars=100)
        assert len(summary) <= 100

    def test_create_compaction_system_message(self):
        msg = create_compaction_system_message("Compacted.")
        assert msg["role"] == "system"
        assert msg["content"] == "Compacted."
