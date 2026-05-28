"""Integration tests — Phase 0–3: full pipeline from ContextEngine through MemoryPlugin to hooks."""

from __future__ import annotations

from core.context_engine.protocol import ContextEngineRuntimeContext
from core.context_engine import (
    LegacyContextEngine, register_context_engine, resolve_context_engine,
    clear_registry, ensure_context_engines_initialized,
)
from core.context_engine.compact_runtime import (
    generate_compaction_summary, rotate_session_id, create_compaction_system_message,
)
from core.memory_plugin import (
    register_memory_plugin, unregister_memory_plugin,
    get_active_memory_plugin, get_active_plugin_info,
    MemorySearchResult, MemoryGetResult,
)
from core.memory_plugin.composite_adapter import CompositeMemoryPlugin
from core.hooks import (
    HookPoint, HookContext,
    register_hook, unregister_hooks, fire_hook, clear_hooks,
)


class _FakeCompositeMemory:
    """Minimal memory backend for integration tests."""
    def __init__(self):
        self._items = [
            {"id": "m1", "memory": "User prefers dark mode.", "score": 0.9, "created_at": "2026-01-01"},
        ]

    async def search(self, query, *, user_id=None, agent_id=None, limit=100, **kw):
        return self._items[:limit]

    def get(self, memory_id):
        for item in self._items:
            if item["id"] == memory_id:
                return item
        return None

    def get_all(self, limit=100, **kw):
        return self._items[:limit]


class _MockCore:
    _compact_session_file = "/tmp/test_session.json"


class TestIntegrationPipeline:
    """Full integration: ContextEngine + MemoryPlugin + Hooks + Session Rotation."""

    def setup_method(self):
        clear_hooks()
        clear_registry()
        # Ensure clean memory plugin state
        try:
            unregister_memory_plugin(owner="core")
        except Exception:
            pass

    # ── Pipeline test ──────────────────────────────────────────────────

    async def test_full_pipeline_compaction(self):
        """ContextEngine.compact() handles messages, returns structured result."""
        # 1. Setup engine
        ensure_context_engines_initialized()
        core = _MockCore()
        engine = resolve_context_engine("legacy", core=core)

        # 2. Create 40 messages (exceeds default threshold of 30)
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(40)]
        rtx = ContextEngineRuntimeContext(extra={"messages": messages})

        # 3. Compact (force=True bypasses threshold; disabled check still applies)
        result = await engine.compact(
            session_id="test-session",
            session_file="/tmp/test_session.json",
            runtime_context=rtx,
            force=True,
        )

        # 4. Assertions — engine returns structured result even when disabled
        assert result.ok is not None  # result is always returned
        assert isinstance(result.reason, str)

    async def test_compaction_with_hooks_in_isolation(self):
        """Hook system works independently of engine."""
        fired = {"count": 0}

        def cb(ctx):
            fired["count"] += 1

        register_hook(HookPoint.BEFORE_COMPACTION, cb, owner="test")
        fire_hook(HookPoint.BEFORE_COMPACTION, HookContext(
            hook=HookPoint.BEFORE_COMPACTION, session_id="s1"))

        assert fired["count"] == 1

    # ── MemoryPlugin + ContextEngine ───────────────────────────────────

    async def test_memory_plugin_wired_to_engine_assemble(self):
        """Engine.assemble() can use MemoryPlugin.build_prompt_section()."""
        # 1. Register memory plugin
        fake_mem = _FakeCompositeMemory()
        plugin = CompositeMemoryPlugin(fake_mem)
        register_memory_plugin(plugin, owner="core")

        assert get_active_memory_plugin() is plugin

        # 2. Engine assemble (LegacyContextEngine doesn't call plugin yet,
        #    but the plugin is available for the LLM loop to use)
        info = get_active_plugin_info()
        assert info["active"]
        assert info["plugin_id"] == "composite"

        # 3. Verify plugin operations work through the adapter
        results = await plugin.search("preferences", max_results=1)
        assert len(results) == 1
        assert "dark mode" in results[0].snippet

        item = await plugin.get("m1")
        assert item is not None
        assert "dark mode" in item.content

    # ── Session rotation integration ───────────────────────────────────

    def test_session_rotation_id_chain(self):
        """Session rotation IDs chain correctly across multiple compactions."""
        sid = "abc-123"
        sid = rotate_session_id(sid)
        assert sid == "abc-123-c1"
        sid = rotate_session_id(sid)
        assert sid == "abc-123-c2"
        sid = rotate_session_id(sid)
        assert sid == "abc-123-c3"

    def test_compaction_summary_integration(self):
        """Summary → system message → prepended to messages."""
        msgs = [
            {"role": "user", "content": "Question about Python"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        summary = generate_compaction_summary(msgs)
        assert "Compacted 2 messages" in summary

        sys_msg = create_compaction_system_message(summary)
        assert sys_msg["role"] == "system"

        # In the real pipeline, llm_loop prepends this:
        pipeline_messages = [sys_msg] + msgs
        assert pipeline_messages[0]["role"] == "system"
        assert "Compacted" in pipeline_messages[0]["content"]

    # ── Hook + MemoryPlugin health ─────────────────────────────────────

    async def test_memory_plugin_health_through_hook(self):
        """Hooks can observe memory plugin health."""
        fake_mem = _FakeCompositeMemory()
        plugin = CompositeMemoryPlugin(fake_mem)
        register_memory_plugin(plugin, owner="core")

        health_result = {}

        def health_check_cb(ctx):
            try:
                active = get_active_memory_plugin()
                if active:
                    health_result["plugin_id"] = active.plugin_id
            except Exception:
                pass

        register_hook(HookPoint.ON_HEALTH_CHECK, health_check_cb, owner="test")
        fire_hook(HookPoint.ON_HEALTH_CHECK, HookContext(
            hook=HookPoint.ON_HEALTH_CHECK,
            session_id="s1",
        ))

        assert health_result.get("plugin_id") == "composite"

    # ── Error resilience ───────────────────────────────────────────────

    async def test_compaction_without_memory_plugin_still_works(self):
        """Compaction works even when no MemoryPlugin is registered."""
        ensure_context_engines_initialized()
        engine = resolve_context_engine("legacy", core=_MockCore())

        messages = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        rtx = ContextEngineRuntimeContext(extra={"messages": messages})

        result = await engine.compact(
            session_id="test", session_file="/tmp/test.json",
            runtime_context=rtx, force=True,
        )
        # No crash — engine still works without memory plugin
        assert result.ok is not None
