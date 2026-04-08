"""Unit tests for daily-brief strict_fallback intent detection."""

from core.daily_brief_intent import daily_brief_lang_from_query, strict_fallback_daily_brief_intent


def test_yesterday_chinese_news():
    assert strict_fallback_daily_brief_intent("昨天的新闻 10条，中文，杂志格式")
    assert daily_brief_lang_from_query("昨天的新闻 10条，中文，杂志格式") == "cn"


def test_english_news_magazine():
    assert strict_fallback_daily_brief_intent("News, English, 10 items, magazine style")
    assert daily_brief_lang_from_query("News, English, 10 items, magazine style") == "en"


def test_today_news_still_matches():
    assert strict_fallback_daily_brief_intent("今日新闻 10条，中文")


def test_news_magazine_without_count_still_matches():
    """杂志/ magazine counts as digest shape even without 条 / N items."""
    assert strict_fallback_daily_brief_intent("新闻，英文，杂志格式")
    assert daily_brief_lang_from_query("新闻，英文，杂志格式") == "en"


def test_random_news_excludes_web_search_phrase():
    assert not strict_fallback_daily_brief_intent("google search latest news headlines")


def test_plain_chat_not_digest():
    assert not strict_fallback_daily_brief_intent("what is the capital of France")
