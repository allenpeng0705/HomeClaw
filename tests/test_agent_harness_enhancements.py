from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from base.tool_permissions import (
    ALLOW_READ_RESTRICT_WRITE,
    ALLOW_ALL,
    ToolPermissionContext,
    evaluate_tool_permission,
    tool_permission_context_from_meta,
)
from base.tools import ToolContext, ToolDefinition, get_tool_registry, reset_tool_registry
from base.token_estimate import estimate_messages_token_budget


def test_evaluate_permission_allow_all():
    tool = ToolDefinition(
        name="x",
        description="d",
        parameters={"type": "object", "properties": {}},
        execute_async=MagicMock(),
        risk_tier="exec",
    )
    assert evaluate_tool_permission(tool, {}, None).allowed is True
    assert evaluate_tool_permission(
        tool, {}, tool_permission_context_from_meta(MagicMock(tool_policy={"default_mode": ALLOW_ALL}), None)
    ).allowed is True


def test_clawcode_plan_mode_forces_read_restrict_even_when_global_allow_all():
    tool = ToolDefinition(
        name="fw",
        description="d",
        parameters={"type": "object", "properties": {}},
        execute_async=MagicMock(),
        risk_tier="write",
    )
    ctx = ToolPermissionContext(mode=ALLOW_ALL, clawcode_plan_mode=True)
    pr = evaluate_tool_permission(tool, {}, ctx)
    assert pr.allowed is False
    assert pr.reason_code == "policy_tier_blocked"


def test_requires_confirmation_ignored_when_allow_all():
    tool = ToolDefinition(
        name="cautious",
        description="d",
        parameters={"type": "object", "properties": {}},
        execute_async=MagicMock(),
        risk_tier="read",
        requires_confirmation=True,
    )
    assert evaluate_tool_permission(
        tool, {}, tool_permission_context_from_meta(MagicMock(tool_policy={"default_mode": ALLOW_ALL}), None)
    ).allowed is True


@pytest.mark.asyncio
async def test_execute_async_permission_denies_exec_tier():
    reset_tool_registry()
    reg = get_tool_registry()

    async def _ok(args, ctx):
        return "ran"

    reg.register(
        ToolDefinition(
            name="danger_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_async=_ok,
            risk_tier="exec",
        )
    )
    meta = MagicMock()
    meta.tool_policy = {"default_mode": ALLOW_READ_RESTRICT_WRITE}
    ctx = ToolContext(core=MagicMock(), permission_context=tool_permission_context_from_meta(meta, None))
    out = await reg.execute_async("danger_tool", {}, ctx)
    assert "blocked" in out.lower() or "Error" in out


@pytest.mark.asyncio
@patch("base.tools._trace_emit_event")
async def test_execute_async_permission_denied_emits_trace(mock_emit):
    reset_tool_registry()
    reg = get_tool_registry()

    async def _ok(args, ctx):
        return "ran"

    reg.register(
        ToolDefinition(
            name="net_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_async=_ok,
            risk_tier="network",
        )
    )
    meta = MagicMock()
    meta.tool_policy = {"default_mode": ALLOW_READ_RESTRICT_WRITE}
    ctx = ToolContext(core=MagicMock(), permission_context=tool_permission_context_from_meta(meta, None))
    await reg.execute_async("net_tool", {}, ctx)
    mock_emit.assert_called()
    types = [c.kwargs.get("event_type") for c in mock_emit.call_args_list]
    assert "permission_denied" in types


@pytest.mark.asyncio
async def test_execute_async_requires_confirmation_blocked():
    reset_tool_registry()
    reg = get_tool_registry()

    async def _ok(args, ctx):
        return "ran"

    reg.register(
        ToolDefinition(
            name="fragile_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_async=_ok,
            risk_tier="read",
            requires_confirmation=True,
        )
    )
    meta = MagicMock()
    meta.tool_policy = {"default_mode": ALLOW_READ_RESTRICT_WRITE}
    ctx = ToolContext(core=MagicMock(), permission_context=tool_permission_context_from_meta(meta, None))
    out = await reg.execute_async("fragile_tool", {}, ctx)
    assert "requires_confirmation" in out.lower() or "Error" in out


@pytest.mark.asyncio
async def test_permission_denial_progress_queue():
    reset_tool_registry()
    reg = get_tool_registry()

    async def _ok(args, ctx):
        return "ran"

    reg.register(
        ToolDefinition(
            name="write_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            execute_async=_ok,
            risk_tier="write",
        )
    )
    meta = MagicMock()
    meta.tool_policy = {"default_mode": ALLOW_READ_RESTRICT_WRITE}
    pq = MagicMock()
    req = MagicMock()
    req.request_metadata = {"progress_queue": pq}
    ctx = ToolContext(
        core=MagicMock(),
        permission_context=tool_permission_context_from_meta(meta, None),
        request=req,
    )
    await reg.execute_async("write_tool", {}, ctx)
    pq.put_nowait.assert_called_once()
    arg = pq.put_nowait.call_args[0][0]
    assert arg.get("event") == "progress"
    assert "Permission denied" in (arg.get("message") or "")


@pytest.mark.asyncio
async def test_list_available_tools_executor():
    from tools.builtin import _list_available_tools_executor

    reset_tool_registry()
    reg = get_tool_registry()

    async def _noop(a, c):
        return "ok"

    reg.register(ToolDefinition(name="alpha", description="Alpha tool", parameters={"type": "object", "properties": {}}, execute_async=_noop))
    ctx = ToolContext(core=MagicMock())
    raw = await _list_available_tools_executor({"limit": 5}, ctx)
    assert "alpha" in raw


def test_estimate_messages_token_budget():
    msgs = [
        {"role": "user", "content": "a" * 400},
        {"role": "assistant", "content": "b" * 400},
    ]
    assert estimate_messages_token_budget(msgs) >= 100


def test_filter_openai_tools_for_llm():
    from base.tools import filter_openai_tools_for_llm

    tools = [
        {"type": "function", "function": {"name": "a", "description": ""}},
        {"type": "function", "function": {"name": "b", "description": ""}},
    ]
    out = filter_openai_tools_for_llm(tools, ["a"])
    assert len(out) == 1
    assert (out[0].get("function") or {}).get("name") == "a"


def test_strip_deferred_tools_from_openai_list():
    from base.tools import strip_deferred_tools_from_openai_list

    tools = [
        {"type": "function", "function": {"name": "keep", "description": ""}},
        {"type": "function", "function": {"name": "drop", "description": ""}},
    ]
    out = strip_deferred_tools_from_openai_list(tools, ["drop"])
    assert len(out) == 1
    assert (out[0].get("function") or {}).get("name") == "keep"


def test_trim_skills_list_for_char_budget():
    from base.skills import trim_skills_list_for_char_budget

    skills = [
        {"name": "A", "folder": "a-1", "description": "x" * 500},
        {"name": "B", "folder": "b-1", "description": "y" * 500},
    ]
    out = trim_skills_list_for_char_budget(skills, budget_chars=400, entry_max_chars=80)
    assert len(out) >= 1
    assert len(out[0].get("description") or "") <= 81


def test_build_skills_system_block_invocation_contract_toggle():
    from base.skills import build_skills_system_block

    skills = [{"name": "Test", "folder": "t-1", "description": "d"}]
    with_contract = build_skills_system_block(skills, include_invocation_contract=True)
    assert "Skill invocation contract" in with_contract
    without = build_skills_system_block(skills, include_invocation_contract=False)
    assert "Skill invocation contract" not in without


def test_rerank_skill_vector_hits_weight_zero_unchanged():
    from base.skill_usage import rerank_skill_vector_hits

    hits = [("a", 0.9), ("b", 0.85)]
    assert rerank_skill_vector_hits(hits, "u", weight=0.0, enabled=True) == hits


def test_rerank_skill_vector_hits_boost_changes_order(monkeypatch):
    import base.skill_usage as su

    def _boost(uid, folder):
        return 1.0 if folder == "b" else 0.0

    monkeypatch.setattr(su, "usage_boost_score", _boost)
    hits = [("a", 0.95), ("b", 0.80)]
    out = su.rerank_skill_vector_hits(hits, "u", weight=0.5, enabled=True)
    assert out[0][0] == "b"
    assert out[1][0] == "a"
