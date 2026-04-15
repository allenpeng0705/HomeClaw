"""news_digest preempt + news_digest DAG config shape."""

import pytest

from base.intent_router import route
from base.planner_executor import get_flow_for_categories


@pytest.mark.asyncio
async def test_news_digest_preempt_daily_brief():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier must not run")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "categories": ["news_digest", "general_chat", "search_web"],
        "category_descriptions": {},
    }
    assert await route("今日新闻头条", cfg, _no_llm) == "news_digest"


@pytest.mark.asyncio
async def test_daily_brief_falls_back_general_chat_without_news_digest_category():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier must not run")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "categories": ["general_chat", "search_web"],
        "category_descriptions": {},
    }
    assert await route("今日新闻", cfg, _no_llm) == "general_chat"


def test_planner_config_has_news_digest_flow():
    pe_cfg = {
        "flows": {
            "news_digest": {
                "category": "news_digest",
                "dag_fail_if_last_starts_with_error": True,
                "steps": [
                    {
                        "tool": "run_skill",
                        "args": {
                            "skill_name": "daily-brief-1.0.0",
                            "script": "fetch_rss.py",
                            "args": ["fetch-vmprint", "--max", "20", "--lang", "all"],
                        },
                    }
                ],
            }
        }
    }
    flow = get_flow_for_categories(["news_digest"], pe_cfg)
    assert flow and flow.get("category") == "news_digest"
