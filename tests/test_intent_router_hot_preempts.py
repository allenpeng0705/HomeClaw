"""Preempt routing for hot intents (no classifier LLM)."""

import pytest

from base.intent_router import route

_CATS = [
    "search_web",
    "list_files",
    "weather",
    "general_chat",
    "summarize_to_page",
    "send_email",
    "schedule_remind",
    "open_url",
    "memory",
    "knowledge_base",
    "read_document",
    "coding",
]


@pytest.fixture
def cfg():
    return {"enabled": True, "categories": _CATS, "category_descriptions": {}}


@pytest.mark.asyncio
async def test_preempt_search_web_no_llm(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("上网搜 Python asyncio 教程", cfg, _no_llm) == "search_web"
    assert await route("search the web for python 3.13", cfg, _no_llm) == "search_web"


@pytest.mark.asyncio
async def test_preempt_search_web_skips_weather_phrases(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("上网搜一下北京明天天气", cfg, _no_llm) == "weather"


@pytest.mark.asyncio
async def test_preempt_summarize_to_page(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("把 report.md 总结成网页", cfg, _no_llm) == "summarize_to_page"


@pytest.mark.asyncio
async def test_preempt_send_email(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("发邮件给老板说明进度", cfg, _no_llm) == "send_email"


@pytest.mark.asyncio
async def test_preempt_schedule_remind(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("提醒我明天9点开会", cfg, _no_llm) == "schedule_remind"


@pytest.mark.asyncio
async def test_preempt_open_url(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("打开 https://example.com 看看", cfg, _no_llm) == "open_url"


@pytest.mark.asyncio
async def test_preempt_memory(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("帮我记住：门禁密码在抽屉", cfg, _no_llm) == "memory"


@pytest.mark.asyncio
async def test_preempt_knowledge_base(cfg):
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier LLM must not run")

    assert await route("在知识库里搜索 部署流程", cfg, _no_llm) == "knowledge_base"
