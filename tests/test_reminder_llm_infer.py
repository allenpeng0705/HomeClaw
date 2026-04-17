"""Tests for LLM scheduling JSON normalization (no live LLM)."""

import pytest

from core.reminder_llm_infer import (
    _parse_json_object,
    merge_companion_scheduling_inference,
    normalize_llm_scheduling_result,
)


def test_normalize_remind_me_minutes():
    out = normalize_llm_scheduling_result(
        {"tool": "remind_me", "arguments": {"minutes": 15, "message": "喝水"}}
    )
    assert out == {"tool": "remind_me", "arguments": {"minutes": 15, "message": "喝水"}}


def test_normalize_remind_me_at_time():
    out = normalize_llm_scheduling_result(
        {
            "tool": "remind_me",
            "arguments": {"at_time": "2026-04-18 08:00:00", "message": "Meeting"},
        }
    )
    assert out and out["arguments"]["at_time"] == "2026-04-18 08:00:00"


def test_normalize_cron_five_fields():
    out = normalize_llm_scheduling_result(
        {
            "tool": "cron_schedule",
            "arguments": {"cron_expr": "0 8 * * *", "message": "Weather check"},
        }
    )
    assert out and out["arguments"]["cron_expr"] == "0 8 * * *"


def test_normalize_rejects_bad_cron_field_count():
    assert (
        normalize_llm_scheduling_result(
            {"tool": "cron_schedule", "arguments": {"cron_expr": "0 8 * *", "message": "x"}}
        )
        is None
    )


def test_normalize_null_tool():
    assert normalize_llm_scheduling_result({"tool": None, "arguments": {}}) is None


def test_parse_json_strips_fence():
    raw = '```json\n{"tool": null, "arguments": {}}\n```'
    obj = _parse_json_object(raw)
    assert obj == {"tool": None, "arguments": {}}


@pytest.mark.asyncio
async def test_merge_regex_fallback_when_core_none():
    """infer_scheduling_tools_from_llm returns None when core is missing; merge still uses regex."""
    q = "15分钟后提醒我喝水"
    got = await merge_companion_scheduling_inference(
        q, None, "2026-04-17 12:00:00", {"reminder_scheduling_llm_infer": True}
    )
    assert got and got.get("tool") == "remind_me"
    assert got["arguments"].get("minutes") == 15
