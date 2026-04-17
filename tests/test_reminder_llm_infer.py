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
        },
    )
    assert out and out["arguments"]["cron_expr"] == "0 8 * * *"


def test_normalize_cron_run_skill_with_args():
    out = normalize_llm_scheduling_result(
        {
            "tool": "cron_schedule",
            "arguments": {
                "cron_expr": "0 7 * * *",
                "task_type": "run_skill",
                "skill_name": "weather-1.0.0",
                "script": "get_weather.py",
                "args": ["北京天气预报"],
                "message": "Morning wx",
            },
        },
    )
    assert out and out["arguments"]["task_type"] == "run_skill"
    assert out["arguments"]["args"] == ["--verbatim-place", "北京"]


def test_normalize_cron_run_tool_web_search():
    out = normalize_llm_scheduling_result(
        {
            "tool": "cron_schedule",
            "arguments": {
                "cron_expr": "0 9 * * *",
                "task_type": "run_tool",
                "tool_name": "web_search",
                "tool_arguments": {"query": "tech headlines", "count": 5},
                "message": "Daily search",
            },
        },
    )
    assert out and out["arguments"]["tool_name"] == "web_search"
    assert out["arguments"]["tool_arguments"]["query"] == "tech headlines"


def test_normalize_cron_run_tool_document_read_default_allowlist():
    """document_read is in the built-in cron run_tool allowlist when config omits cron_run_tool_allowlist."""
    out = normalize_llm_scheduling_result(
        {
            "tool": "cron_schedule",
            "arguments": {
                "cron_expr": "0 8 * * *",
                "task_type": "run_tool",
                "tool_name": "document_read",
                "tool_arguments": {"path": "docs/README.md"},
                "message": "Daily readme",
            },
        },
    )
    assert out and out["arguments"]["tool_name"] == "document_read"
    assert out["arguments"]["tool_arguments"]["path"] == "docs/README.md"


def test_normalize_cron_run_tool_rejected_when_not_allowlisted():
    assert (
        normalize_llm_scheduling_result(
            {
                "tool": "cron_schedule",
                "arguments": {
                    "cron_expr": "0 9 * * *",
                    "task_type": "run_tool",
                    "tool_name": "exec",
                    "tool_arguments": {"cmd": "rm -rf /"},
                    "message": "bad",
                },
            },
            tools_cfg={"cron_run_tool_allowlist": ["web_search", "time"]},
        )
        is None
    )


def test_is_cron_run_tool_allowed_empty_list_disables():
    from tools.builtin import is_cron_run_tool_allowed

    ok, err = is_cron_run_tool_allowed("web_search", {"cron_run_tool_allowlist": []})
    assert not ok
    assert "empty" in err.lower()


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
