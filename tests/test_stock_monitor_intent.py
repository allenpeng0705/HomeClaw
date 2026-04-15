"""stock_monitor intent preempt + DAG config."""

import pytest

from base.intent_router import route
from base.planner_executor import get_flow_for_categories


@pytest.mark.asyncio
async def test_stock_preempt_returns_stock_monitor():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier must not run")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "categories": ["stock_monitor", "memory", "general_chat"],
        "category_descriptions": {},
    }
    assert await route("自选股今天怎么样", cfg, _no_llm) == "stock_monitor"


@pytest.mark.asyncio
async def test_stock_preempt_falls_back_general_chat_without_category():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier must not run")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "categories": ["memory", "general_chat"],
        "category_descriptions": {},
    }
    assert await route("股票行情", cfg, _no_llm) == "general_chat"


def test_planner_has_stock_monitor_flow():
    pe_cfg = {
        "flows": {
            "stock_monitor": {
                "category": "stock_monitor",
                "steps": [
                    {
                        "tool": "run_skill",
                        "args": {
                            "skill_name": "stock-monitor-1.0.0",
                            "script": "stock_monitor.py",
                            "args": ["portfolio"],
                        },
                    }
                ],
            }
        }
    }
    f = get_flow_for_categories(["stock_monitor"], pe_cfg)
    assert f and f.get("category") == "stock_monitor"
