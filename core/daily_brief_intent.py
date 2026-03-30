"""
Heuristics for when to run daily-brief strict_fallback (model returned no tool_calls).

Kept separate from llm_loop.py so tests do not import the full Core stack.
"""

from __future__ import annotations

import re
from typing import Optional


def strict_fallback_daily_brief_intent(query: Optional[str]) -> bool:
    """
    True when the user clearly wants the RSS daily-brief / magazine digest path but the model may omit tool_calls.
    """
    q_raw = (query or "").strip()
    if not q_raw:
        return False
    q_lo = q_raw.lower()
    _phrases = (
        "daily brief",
        "morning report",
        "rss",
        "headline digest",
        "news digest",
        "今日新闻",
        "新闻订阅",
        "头条",
        "新闻摘要",
    )
    if any((p in q_lo if p.isascii() else p in q_raw) for p in _phrases):
        return True
    if ("昨天" in q_raw or "昨日" in q_raw) and "新闻" in q_raw:
        return True
    if re.search(r"\byesterday'?s\s+news\b", q_lo) or re.search(r"\byesterday\s+news\b", q_lo):
        return True
    if ("新闻" in q_raw or "头条" in q_raw or "daily brief" in q_lo or "headlines" in q_lo) and (
        "条" in q_raw
        or re.search(r"\b\d{1,3}\s*(items?|headlines?)\b", q_lo)
        or "杂志" in q_raw
        or "magazine" in q_lo
    ):
        if not any(k in q_lo for k in ("web search", "search web", "google", "bing", "tavily", "live web", "latest on web")):
            if not any(k in q_raw for k in ("网页搜索", "上网搜", "实时搜索", "全网搜索")):
                return True
    if re.search(r"\bnews\b", q_lo) and (
        re.search(r"\b\d{1,3}\s*(items?|headlines?)\b", q_lo)
        or "magazine" in q_lo
        or "digest" in q_lo
        or re.search(r"\brss\b", q_lo)
    ):
        if not any(k in q_lo for k in ("web search", "search web", "google", "bing", "tavily")):
            if not any(k in q_raw for k in ("网页搜索", "上网搜", "实时搜索", "全网搜索")):
                return True
    return False


def daily_brief_lang_from_query(query: Optional[str]) -> str:
    """Infer --lang for daily-brief fetch: cn | en | all."""
    q_raw = (query or "").strip()
    q_lo = q_raw.lower()
    if any(k in q_raw for k in ("中文", "汉语", "国内")) or any(k in q_lo for k in (" chinese", "lang cn", " cn ")):
        return "cn"
    if any(k in q_raw for k in ("英文", "英语")) or re.search(r"\benglish\b", q_lo):
        return "en"
    return "all"
