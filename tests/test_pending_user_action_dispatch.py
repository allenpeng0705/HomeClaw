"""Unit tests for core/pending_user_action_dispatch.py (no Core, no DB)."""

import asyncio

import pytest

from base.tools import ToolContext


def test_generic_allowlist_defaults_to_run_skill():
    from core.pending_user_action_dispatch import _generic_allowlist

    assert _generic_allowlist({}) == {"run_skill"}
    assert _generic_allowlist({"pending_user_action_generic_tools": []}) == {"run_skill"}
    assert _generic_allowlist({"pending_user_action_generic_tools": ["", "   ", ""]}) == {"run_skill"}
    assert _generic_allowlist({"pending_user_action_generic_tools": ["run_skill"]}) == {"run_skill"}
    assert _generic_allowlist({"pending_user_action_generic_tools": ["time", "run_skill"]}) == {"time", "run_skill"}


@pytest.fixture
def minimal_context():
    return ToolContext(
        core=None,
        app_id="homeclaw",
        user_name="",
        user_id="u1",
        friend_id="HomeClaw",
        session_id="",
        request=None,
    )


class _MockRegistry:
    def __init__(self, result="mock ok"):
        self.result = result
        self.calls = []

    async def execute_async(self, name, args, context):
        self.calls.append((name, args, context))
        return self.result


def _run(coro):
    return asyncio.run(coro)


def test_registered_handler_empty_result_is_failed_keep(minimal_context):
    from core.pending_user_action_dispatch import (
        _PENDING_HANDLERS,
        execute_pending_user_action,
        register_pending_user_action_handler,
    )

    kind = "_pytest_pending_empty_result"

    async def _empty_handler(registry, context, payload):
        return "   "

    register_pending_user_action_handler(kind, _empty_handler)
    try:
        reg = _MockRegistry()
        msg, outcome = _run(
            execute_pending_user_action(kind, {}, reg, minimal_context, {})
        )
        assert outcome == "failed_keep"
        assert "无结果" in msg or "empty" in msg.lower()
        assert reg.calls == []
    finally:
        _PENDING_HANDLERS.pop(kind, None)


def test_generic_single_tool_executed_when_kind_unknown(minimal_context):
    from core.pending_user_action_dispatch import execute_pending_user_action

    reg = _MockRegistry(result="pdf link")
    msg, outcome = _run(
        execute_pending_user_action(
            "custom_future_kind",
            {"tool": "run_skill", "arguments": {"skill_name": "x", "script": "y.py", "args": ["a"]}},
            reg,
            minimal_context,
            {"pending_user_action_generic_tools": ["run_skill"]},
        )
    )
    assert outcome == "executed"
    assert msg == "pdf link"
    assert len(reg.calls) == 1
    assert reg.calls[0][0] == "run_skill"


def test_generic_list_args_cancelled_unsupported(minimal_context):
    """Generic path requires arguments dict, not CLI args list."""
    from core.pending_user_action_dispatch import execute_pending_user_action

    reg = _MockRegistry()
    msg, outcome = _run(
        execute_pending_user_action(
            "unknown_kind",
            {"tool": "run_skill", "args": ["fetch", "--max", "5"]},
            reg,
            minimal_context,
            {},
        )
    )
    assert outcome == "cancelled_unsupported"
    assert reg.calls == []


def test_generic_registry_returns_only_whitespace_is_failed_keep(minimal_context):
    from core.pending_user_action_dispatch import execute_pending_user_action

    reg = _MockRegistry(result="  \n  ")
    msg, outcome = _run(
        execute_pending_user_action(
            "unknown_kind",
            {"tool": "run_skill", "arguments": {}},
            reg,
            minimal_context,
            {},
        )
    )
    assert outcome == "failed_keep"
    assert len(reg.calls) == 1
