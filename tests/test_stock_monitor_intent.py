"""stock_monitor intent preempt + DAG config."""

import pytest

from base.intent_router import match_frequent_fast_path, route
from base.planner_executor import get_flow_for_categories


@pytest.mark.asyncio
async def test_stock_preempt_returns_stock_monitor():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier must not run")

    cfg = {
        "enabled": True,
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
        "categories": ["memory", "general_chat"],
        "category_descriptions": {},
    }
    assert await route("股票行情", cfg, _no_llm) == "general_chat"


def test_frequent_fast_path_stock_monitor():
    cfg = {
        "frequent_fast_paths": [{"category": "stock_monitor", "patterns": [r"自选股", r"(?i)watchlist"]}],
        "categories": ["stock_monitor", "general_chat"],
    }
    assert match_frequent_fast_path("看下自选股", ["stock_monitor", "general_chat"], cfg) == "stock_monitor"


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
