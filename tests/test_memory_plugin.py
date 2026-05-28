"""Tests for core.memory_plugin — Phase 1: MemoryPlugin protocol, slot, and composite adapter."""

from __future__ import annotations

import pytest

from core.memory_plugin import (
    MemoryPlugin,
    MemorySearchResult,
    MemoryGetResult,
    MemoryFlushPlan,
    MemoryFlushResult,
    MemoryHealthStatus,
    register_memory_plugin,
    unregister_memory_plugin,
    get_active_memory_plugin,
    get_active_plugin_info,
    CompositeMemoryPlugin,
)


# ── Mocks ──────────────────────────────────────────────────────────────────


class _FakeMemoryPlugin(MemoryPlugin):
    """Minimal MemoryPlugin for slot tests."""

    def __init__(self, plugin_id: str = "fake"):
        self._plugin_id = plugin_id
        self._search_results: list[MemorySearchResult] = []
        self._get_result: MemoryGetResult | None = None

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    async def search(self, query: str, *, max_results: int = 5, **kwargs) -> list[MemorySearchResult]:
        return self._search_results[:max_results]

    async def get(self, lookup: str, *, from_line=None, line_count=None, **kwargs) -> MemoryGetResult | None:
        return self._get_result

    def build_prompt_section(self, *, available_tools=None, citations_mode="inline") -> str:
        return "## Mock Memory\nUse memory tools.\n\n"


class _FakeCompositeMemory:
    """Minimal CompositeMemory mock for adapter tests."""
    def __init__(self, search_results=None, get_result=None, all_items=None):
        self._search = search_results or []
        self._get = get_result
        self._all = all_items or []

    async def search(self, query, **kwargs):
        return self._search

    def get(self, memory_id):
        return self._get

    def get_all(self, limit=100, **kwargs):
        return self._all[:limit]


# ── Protocol tests ─────────────────────────────────────────────────────────


class TestProtocol:
    """MemoryPlugin ABC and result types."""

    def test_memory_plugin_is_abstract(self):
        import inspect
        assert inspect.isabstract(MemoryPlugin)

    def test_memory_search_result_defaults(self):
        r = MemorySearchResult()
        assert r.score == 0.0
        assert r.snippet == ""

    def test_memory_search_result_with_data(self):
        r = MemorySearchResult(
            corpus="agent_memory", path="mem/001.md",
            score=0.85, snippet="User prefers dark mode.",
            id="mem-001",
        )
        assert r.corpus == "agent_memory"
        assert r.score == 0.85
        assert "dark mode" in r.snippet
        assert r.id == "mem-001"

    def test_memory_get_result(self):
        r = MemoryGetResult(
            corpus="daily_memory", path="2026-05-27.md",
            content="Discussed deployment pipeline.",
            from_line=0, line_count=1, id="daily-001",
        )
        assert r.content == "Discussed deployment pipeline."
        assert r.line_count == 1

    def test_memory_flush_plan_defaults(self):
        plan = MemoryFlushPlan()
        assert plan.soft_threshold_tokens == 30000
        assert plan.reserve_tokens_floor == 4096

    def test_memory_flush_result(self):
        fr = MemoryFlushResult(flushed=True, items_stored=3)
        assert fr.flushed
        assert fr.items_stored == 3

        fr2 = MemoryFlushResult(flushed=False, reason="below threshold", errors=["e1"])
        assert not fr2.flushed
        assert len(fr2.errors) == 1

    def test_memory_health_status(self):
        hs = MemoryHealthStatus(ok=True, backend="composite", index_size=42)
        assert hs.ok
        assert hs.backend == "composite"
        assert hs.index_size == 42

        hs2 = MemoryHealthStatus(ok=False, error_count=1, details={"error": "timeout"})
        assert not hs2.ok
        assert hs2.error_count == 1


# ── Slot tests ─────────────────────────────────────────────────────────────


class TestSlot:
    """Single-slot memory plugin registration."""

    def setup_method(self):
        # Ensure clean state — unregister any leftover plugin
        try:
            unregister_memory_plugin(owner="core")
        except Exception:
            pass

    def test_register_and_resolve(self):
        plugin = _FakeMemoryPlugin("test-plugin")
        ok = register_memory_plugin(plugin, owner="core")
        assert ok
        assert get_active_memory_plugin() is plugin

    def test_info_when_none(self):
        info = get_active_plugin_info()
        assert info["active"] is False

    def test_info_when_registered(self):
        plugin = _FakeMemoryPlugin("info-test")
        register_memory_plugin(plugin, owner="core")
        info = get_active_plugin_info()
        assert info["active"] is True
        assert info["plugin_id"] == "info-test"
        assert info["owner"] == "core"

    def test_unregister(self):
        plugin = _FakeMemoryPlugin("tmp")
        register_memory_plugin(plugin, owner="core")
        ok = unregister_memory_plugin(owner="core")
        assert ok
        assert get_active_memory_plugin() is None

    def test_unregister_wrong_owner(self):
        plugin = _FakeMemoryPlugin("owned-by-alice")
        register_memory_plugin(plugin, owner="alice")
        ok = unregister_memory_plugin(owner="bob")
        assert not ok
        assert get_active_memory_plugin() is plugin
        # Cleanup
        unregister_memory_plugin(owner="alice")

    def test_unregister_none(self):
        assert not unregister_memory_plugin(owner="core")

    def test_replace_plugin(self):
        p1 = _FakeMemoryPlugin("first")
        p2 = _FakeMemoryPlugin("second")
        register_memory_plugin(p1, owner="core")
        register_memory_plugin(p2, owner="core")
        assert get_active_memory_plugin() is p2

    def test_displace_by_different_owner(self):
        p1 = _FakeMemoryPlugin("old")
        p2 = _FakeMemoryPlugin("new")
        register_memory_plugin(p1, owner="old-owner")
        register_memory_plugin(p2, owner="new-owner")
        assert get_active_memory_plugin() is p2


# ── CompositeMemoryPlugin tests ────────────────────────────────────────────


class TestCompositeMemoryPlugin:
    """CompositeMemory adapter tests."""

    def test_plugin_id(self):
        cm = _FakeCompositeMemory()
        plugin = CompositeMemoryPlugin(cm)
        assert plugin.plugin_id == "composite"

    async def test_search_maps_results(self):
        cm = _FakeCompositeMemory(search_results=[
            {"id": "1", "memory": "User prefers Python", "score": 0.9},
            {"id": "2", "memory": "Runs on port 9000", "score": 0.7},
        ])
        plugin = CompositeMemoryPlugin(cm)
        results = await plugin.search("preferences", max_results=5)
        assert len(results) == 2
        assert results[0].score == 0.9
        assert "Python" in results[0].snippet
        assert results[0].id == "1"

    async def test_search_empty(self):
        cm = _FakeCompositeMemory(search_results=[])
        plugin = CompositeMemoryPlugin(cm)
        results = await plugin.search("nothing", max_results=5)
        assert results == []

    async def test_get_returns_item(self):
        cm = _FakeCompositeMemory(get_result={
            "id": "abc", "memory": "Full content here."
        })
        plugin = CompositeMemoryPlugin(cm)
        result = await plugin.get("abc")
        assert result is not None
        assert result.content == "Full content here."
        assert result.id == "abc"

    async def test_get_nonexistent(self):
        cm = _FakeCompositeMemory(get_result=None)
        plugin = CompositeMemoryPlugin(cm)
        result = await plugin.get("nonexistent")
        assert result is None

    def test_build_prompt_section_with_tools(self):
        cm = _FakeCompositeMemory()
        plugin = CompositeMemoryPlugin(cm)
        section = plugin.build_prompt_section(
            available_tools={"agent_memory_search", "append_daily_memory"},
        )
        assert "Memory (agent)" in section
        assert "agent_memory_search" in section
        assert "Memory (daily)" in section
        assert "append_daily_memory" in section

    def test_build_prompt_section_no_tools(self):
        cm = _FakeCompositeMemory()
        plugin = CompositeMemoryPlugin(cm)
        section = plugin.build_prompt_section(available_tools=set())
        assert section == ""

    async def test_health_ok(self):
        cm = _FakeCompositeMemory(all_items=[{"id": "1"}])
        plugin = CompositeMemoryPlugin(cm)
        status = await plugin.health()
        assert status.ok
        assert status.backend == "composite"
        assert status.index_size == 1

    async def test_health_error(self):
        cm = _FakeCompositeMemory()
        # Simulate error by making get_all raise
        cm.get_all = lambda **kw: (_ for _ in ()).throw(Exception("boom"))
        plugin = CompositeMemoryPlugin(cm)
        status = await plugin.health()
        assert not status.ok
        assert status.error_count == 1
