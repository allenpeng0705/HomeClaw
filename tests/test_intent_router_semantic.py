import pytest

from base.intent_router import route


class _Hit:
    def __init__(self, i: str, score: float):
        self.id = i
        self.score = score


class _VS:
    def __init__(self, hits):
        self._hits = hits

    def search(self, _q, limit=5):
        return self._hits[:limit]


class _Emb:
    async def embed(self, _text):
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_semantic_mode_routes_without_classifier():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "semantic",
        "categories": ["alpha", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "something unrelated",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("alpha", 0.1)]), "embedder": _Emb()},
    )
    assert out == "alpha"


@pytest.mark.asyncio
async def test_semantic_mode_fail_closed_to_general_chat():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "semantic",
        "categories": ["alpha", "general_chat"],
        "semantic": {"enabled": True, "threshold": 0.9, "fail_open_to_static": False},
    }
    out = await route(
        "something unrelated",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("alpha", 0.9)]), "embedder": _Emb()},
    )
    assert out == "general_chat"


@pytest.mark.asyncio
async def test_semantic_mode_skips_static_preempts():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "semantic",
        "categories": ["stock_monitor", "alpha", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    # "股票行情" would normally trigger static stock preempt; semantic mode must use semantic routing first.
    out = await route(
        "股票行情",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("alpha", 0.1)]), "embedder": _Emb()},
    )
    assert out == "alpha"


@pytest.mark.asyncio
async def test_semantic_mode_weather_preempt_before_semantic():
    """Clear 天气 queries must not lose to embedding (e.g. mislabeled as coding)."""

    async def _no_llm(*_a, **_k):
        raise AssertionError("semantic vector path should not run when weather keywords match")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "semantic",
        "categories": ["weather", "coding", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "北京明天天气怎么样",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("coding", 0.99)]), "embedder": _Emb()},
    )
    assert out == "weather"


@pytest.mark.asyncio
async def test_semantic_mode_list_files_preempt_before_semantic():
    """List-folder phrasing must not lose to embedding (e.g. mislabeled as coding); use list_files DAG for full folder_list."""

    async def _no_llm(*_a, **_k):
        raise AssertionError("semantic vector path should not run when list_files keywords match")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "semantic",
        "categories": ["list_files", "coding", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "我有哪些文件？",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("coding", 0.99)]), "embedder": _Emb()},
    )
    assert out == "list_files"


@pytest.mark.asyncio
async def test_hybrid_mode_keeps_static_preempt_first():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "hybrid",
        "categories": ["stock_monitor", "alpha", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "股票行情",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("alpha", 0.1)]), "embedder": _Emb()},
    )
    assert out == "stock_monitor"


@pytest.mark.asyncio
async def test_hybrid_mode_get_file_link_preempt_for_real_file_request():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "hybrid",
        "categories": ["get_file_link", "search_web", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "把images/ID1.jpg发给我",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("search_web", 0.9)]), "embedder": _Emb()},
    )
    assert out == "get_file_link"


@pytest.mark.asyncio
async def test_hybrid_mode_get_file_link_preempt_does_not_hijack_news_share():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "hybrid",
        "categories": ["get_file_link", "search_web", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "帮我上网搜一下伊美战争的最新新闻，发给我",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("search_web", 0.9)]), "embedder": _Emb()},
    )
    assert out == "search_web"


@pytest.mark.asyncio
async def test_hybrid_mode_list_files_preempt_for_chinese_folder_phrase():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "hybrid",
        "categories": ["list_files", "coding", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "images里有什么文件",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("coding", 0.99)]), "embedder": _Emb()},
    )
    assert out == "list_files"


@pytest.mark.asyncio
async def test_hybrid_mode_file_link_requires_file_like_signal():
    async def _no_llm(*_a, **_k):
        raise AssertionError("classifier should not be called")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "hybrid",
        "categories": ["get_file_link", "search_web", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "把最新新闻发给我",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("search_web", 0.95)]), "embedder": _Emb()},
    )
    assert out == "search_web"


@pytest.mark.asyncio
async def test_semantic_mode_greeting_preempt_before_semantic():
    async def _no_llm(*_a, **_k):
        raise AssertionError("semantic vector path should not run when greeting preempt matches")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "semantic",
        "categories": ["greeting", "coding", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "你好",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("coding", 0.99)]), "embedder": _Emb()},
    )
    assert out == "greeting"


@pytest.mark.asyncio
async def test_hybrid_mode_web_news_search_preempt_before_semantic():
    """News + 搜/搜索 must win over semantic 'greeting' mislabels."""

    async def _no_llm(*_a, **_k):
        raise AssertionError("semantic/classifier should not run when web/news preempt matches")

    cfg = {
        "enabled": True,
        "intent_category_docs_dir": "",
        "mode": "hybrid",
        "categories": ["search_web", "greeting", "general_chat"],
        "semantic": {"enabled": True, "top_k": 5, "threshold": 0.0, "accept_top_n": 1},
    }
    out = await route(
        "搜一下伊美战争最新的新闻，发给我",
        cfg,
        _no_llm,
        semantic_context={"vector_store": _VS([_Hit("greeting", 0.99)]), "embedder": _Emb()},
    )
    assert out == "search_web"

