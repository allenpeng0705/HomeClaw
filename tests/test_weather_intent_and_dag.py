"""Intent router weather preempt + planner weather DAG args / fail-on-error."""

import pytest

from base.intent_router import route
from base.planner_executor import _resolve_flow_step_args, get_flow_for_categories, run_dag


def test_get_flow_for_categories_prefers_intent_that_has_dag():
    """Multi-category: try categories with a configured flow before ones without (e.g. general_chat, weather)."""
    pe_cfg = {
        "flows": {
            "weather": {"category": "weather", "steps": [{"tool": "run_skill", "args": {}}]},
        }
    }
    flow = get_flow_for_categories(["general_chat", "weather"], pe_cfg)
    assert flow is not None
    assert flow.get("category") == "weather"


@pytest.mark.asyncio
async def test_intent_router_weather_preempt_no_llm():
    async def _no_llm(*_a, **_k):
        raise AssertionError("router should preempt without calling the LLM")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "categories": ["weather", "general_chat"],
        "category_descriptions": {},
    }
    assert await route("北京明天天气怎么样", cfg, _no_llm) == "weather"
    assert await route("What's the weather in London?", cfg, _no_llm) == "weather"


@pytest.mark.asyncio
async def test_weather_dag_resolves_run_skill_args():
    pe_cfg = {
        "flows": {
            "weather": {
                "trigger": "category",
                "category": "weather",
                "dag_fail_if_last_starts_with_error": True,
                "steps": [
                    {
                        "tool": "run_skill",
                        "args": {"skill_name": "weather-1.0.0", "script": "get_weather.py"},
                        "args_from": {"args": ["user_message_text_as_run_skill_args", ""]},
                    }
                ],
            }
        }
    }
    flow = get_flow_for_categories(["weather"], pe_cfg)
    assert flow and (flow.get("category") == "weather")
    step = flow["steps"][0]
    args = await _resolve_flow_step_args(
        step, 1, {}, "北京明天天气怎么样", None, {}, flow, None, "weather"
    )
    assert args.get("skill_name") == "weather-1.0.0"
    assert args.get("script") == "get_weather.py"
    assert args.get("args") == ["北京明天天气怎么样"]


class _MockRegistryErrorSkill:
    async def execute_async(self, tool_name, args, context):
        assert tool_name == "run_skill"
        return "Error: could not reach wttr.in: timed out"


@pytest.mark.asyncio
async def test_weather_dag_fails_on_error_prefix_for_react_fallback():
    flow = {
        "category": "weather",
        "dag_fail_if_last_starts_with_error": True,
        "steps": [
            {
                "tool": "run_skill",
                "args": {"skill_name": "weather-1.0.0", "script": "get_weather.py"},
                "args_from": {"args": ["user_message_text_as_run_skill_args", ""]},
            }
        ],
    }
    ok, result = await run_dag(
        flow,
        _MockRegistryErrorSkill(),
        None,
        user_message="北京明天天气怎么样",
        tool_names=["run_skill", "web_search", "time"],
    )
    assert ok is False
    assert "Error:" in (result or "")
