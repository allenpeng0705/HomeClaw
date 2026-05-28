"""Tests for core.hooks — Phase 3: lifecycle hooks for agent operations."""

from __future__ import annotations

from core.hooks import (
    HookPoint,
    HookContext,
    register_hook,
    unregister_hooks,
    fire_hook,
    clear_hooks,
)


class TestHooks:
    """Lifecycle hook system tests."""

    def setup_method(self):
        clear_hooks()

    def test_register_and_fire(self):
        fired: list[HookContext] = []

        def callback(ctx: HookContext):
            fired.append(ctx)

        register_hook(HookPoint.AFTER_COMPACTION, callback, owner="test")
        fire_hook(HookPoint.AFTER_COMPACTION, HookContext(
            hook=HookPoint.AFTER_COMPACTION,
            session_id="s1", token_count=5000,
        ))

        assert len(fired) == 1
        assert fired[0].session_id == "s1"
        assert fired[0].token_count == 5000

    def test_multiple_callbacks(self):
        calls: list[str] = []

        def cb_a(ctx): calls.append("a")
        def cb_b(ctx): calls.append("b")

        register_hook(HookPoint.AFTER_TURN, cb_a, owner="p1")
        register_hook(HookPoint.AFTER_TURN, cb_b, owner="p2")
        fire_hook(HookPoint.AFTER_TURN)

        assert calls == ["a", "b"]

    def test_default_context(self):
        fired = False

        def cb(ctx): nonlocal fired; fired = (ctx.hook == HookPoint.AFTER_COMPACTION)

        register_hook(HookPoint.AFTER_COMPACTION, cb, owner="test")
        fire_hook(HookPoint.AFTER_COMPACTION)

        assert fired

    def test_unregister_by_owner(self):
        calls: list[str] = []

        def cb_a(ctx): calls.append("a")
        def cb_b(ctx): calls.append("b")

        register_hook(HookPoint.AFTER_TURN, cb_a, owner="keep")
        register_hook(HookPoint.AFTER_TURN, cb_b, owner="remove")
        removed = unregister_hooks(owner="remove")

        assert removed == 1
        fire_hook(HookPoint.AFTER_TURN)
        assert calls == ["a"]

    def test_unregister_none(self):
        assert unregister_hooks(owner="nobody") == 0

    def test_clear_hooks(self):
        register_hook(HookPoint.AFTER_TURN, lambda ctx: None, owner="test")
        clear_hooks()
        # Should not raise — all hooks gone
        fire_hook(HookPoint.AFTER_TURN)

    def test_callback_exception_doesnt_block(self):
        calls: list[str] = []

        def bad(ctx): raise RuntimeError("boom")
        def good(ctx): calls.append("good")

        register_hook(HookPoint.AFTER_TURN, bad, owner="bad")
        register_hook(HookPoint.AFTER_TURN, good, owner="good")
        # Should not raise — bad callback is caught
        fire_hook(HookPoint.AFTER_TURN)
        assert calls == ["good"]

    def test_all_hook_points(self):
        for hp in HookPoint:
            fired = False

            def cb(ctx, _hp=hp): nonlocal fired; fired = (ctx.hook == _hp)

            register_hook(hp, cb, owner="test")
            fire_hook(hp)
            assert fired, f"Hook {hp} did not fire"

    def test_hook_context_extra(self):
        ctx = HookContext(
            hook=HookPoint.BEFORE_MEMORY_FLUSH,
            session_id="s1",
            extra={"custom": "value", "count": 42},
        )
        assert ctx.extra["custom"] == "value"
        assert ctx.extra["count"] == 42
        assert ctx.compaction_result is None
