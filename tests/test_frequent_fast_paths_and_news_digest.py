"""frequent_fast_paths YAML + news_digest preempt + news_digest DAG config shape."""

import pytest

from base.intent_router import match_frequent_fast_path, route
from base.planner_executor import get_flow_for_categories


def test_match_frequent_fast_path_read_document():
    cfg = {
        "frequent_fast_paths": [
            {"category": "read_document", "patterns": [r"(?i)read\s+file\s+"]},
        ],
        "categories": ["read_document", "general_chat"],
    }
    assert match_frequent_fast_path("Read file documents/notes.md", ["read_document", "general_chat"], cfg) == "read_document"
    assert match_frequent_fast_path("hello", ["read_document", "general_chat"], cfg) is None


def test_match_frequent_fast_path_unknown_category_ignored():
    cfg = {
        "frequent_fast_paths": [{"category": "nope", "patterns": [".*"]}],
        "categories": ["general_chat"],
    }
    assert match_frequent_fast_path("anything", ["general_chat"], cfg) is None


@pytest.mark.asyncio
async def test_news_digest_preempt_daily_brief():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier must not run")

    cfg = {
        "enabled": True,
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

