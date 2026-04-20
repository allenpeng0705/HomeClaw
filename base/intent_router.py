"""
Intent router (Phase 2): one short LLM call classifies user query into a category.
Category is then used to filter tools (and optionally skills) before the main LLM turn.

Principle: Prefer LLM classification over brittle phrase tables. Optional regex fast paths may
come from intent category markdown (`match_patterns`) or code preempts. One LLM completion
runs for query -> category when cheaper paths do not decide.

Phase 3.2 fallback: On parse failure, timeout, or any exception, route() returns
"general_chat" so the main turn gets full tools (or config profile).

Config (intent_router): optional router_llm — model ref passed to completion_fn as llm_name for
this call only (use a small/fast model). timeout_seconds caps wait before fallback (see llm_loop).
"""

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from base.tool_profiles import get_tool_names_for_profile
from base.intent_category_router import (
    _intent_category_docs_dir_resolved,
    load_intent_category_docs,
    merge_intent_router_config_with_docs,
    rerank_intent_hits,
    search_intent_categories_by_query,
)
from base.router_reranker import rerank_with_local_model, apply_rerank_scores


# Default categories when not in config (must match docs_design/IntentRouter_CategoriesCoverage.md)
DEFAULT_CATEGORIES = [
    "search_web",
    "list_files",
    "get_file_link",
    "read_document",
    "create_slides",
    "create_html_slides",
    "generate_pdf",
    "summarize_to_page",
    "send_email",
    "schedule_remind",
    "open_url",
    "memory",
    "knowledge_base",
    "image",
    "weather",
    "news_digest",
    "stock_monitor",
    "greeting",
    "identity_capabilities",
    "general_chat",
]

# Optional default descriptions for router prompt (used when config has no category_descriptions)
DEFAULT_CATEGORY_DESCRIPTIONS: Dict[str, str] = {
    "search_web": "User wants to search the web or look up information online.",
    "list_files": "User wants to list, browse, or find files or folders.",
    "get_file_link": "User wants to get a view/download link for a specific file (e.g. 'send me that file', '发给我 img1.png').",
    "read_document": "User wants to read, summarize, or understand a specific document or file.",
    "create_slides": "User wants to create slides, a presentation, or PPT from content (generic; may be HTML or PowerPoint).",
    "create_html_slides": "User wants to create HTML slides or a web-based slide deck from a document (not PowerPoint/PPT).",
    "generate_pdf": "User wants to generate or export a PDF from a document (e.g. summarize to PDF, report to PDF). Markdown is generated first, then converted to PDF.",
    "summarize_to_page": "User wants a summary of a document as a viewable page (link), not necessarily as PDF.",
    "send_email": "User wants to send an email. The assistant will use a contacts list, compose a draft, and ask for confirmation before sending.",
    "schedule_remind": "User wants to set a reminder, schedule, recurring task, or record a date.",
    "open_url": "User wants to open a URL, visit a webpage, or navigate to a link.",
    "memory": "User wants to remember something, recall past context, or search memory.",
    "knowledge_base": "User wants to search or save something in their knowledge base.",
    "image": "User wants to generate, analyze, or describe an image.",
    "weather": "User asks for weather, forecast, or temperature for a place or time.",
    "news_digest": "User wants RSS headlines, daily brief, or news digest (not generic web search).",
    "stock_monitor": "User wants watchlist quotes, portfolio, stock prices, 自选股, or A股/港股/美股行情 (stock-monitor skill).",
    "greeting": "User says a short greeting or thanks with no concrete task.",
    "identity_capabilities": "User asks who the assistant is, what it can do, or to introduce itself (onboarding / meta about the bot).",
    "general_chat": "General conversation, question, or intent that does not fit a specific category above.",
}


def _format_categories_for_prompt(categories: List[str], config: Dict[str, Any]) -> str:
    """Build the category list for the router prompt; add descriptions if configured. Never raises."""
    try:
        if not isinstance(config, dict):
            config = {}
        descriptions = config.get("category_descriptions")
        if not isinstance(descriptions, dict) or not descriptions:
            descriptions = DEFAULT_CATEGORY_DESCRIPTIONS
        lines = []
        for c in (categories or []):
            c = (c or "").strip() if c is not None else ""
            if not c:
                continue
            desc = descriptions.get(c) or descriptions.get((c or "").lower().replace(" ", "_").replace("-", "_"))
            if desc and str(desc).strip():
                lines.append(f"  - {c}: {str(desc).strip()}")
            else:
                lines.append(f"  - {c}")
        if not lines:
            return ", ".join(str(x) for x in (categories or []))
        return "\n".join(lines)
    except Exception:
        return ", ".join(str(x) for x in (categories or []))


def _merge_intent_router_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge categories, descriptions, patterns, and category_tools from config/intent_category/*.md unless disabled."""
    from pathlib import Path

    from base.util import Util

    if not isinstance(config, dict):
        return {}
    if _intent_category_docs_dir_resolved(config) is None:
        return dict(config)
    root = Path(Util().root_path()).resolve()
    return merge_intent_router_config_with_docs(
        config,
        root_path=root,
        default_descriptions=DEFAULT_CATEGORY_DESCRIPTIONS,
    )


def _match_doc_category_patterns(query: str, config: Dict[str, Any], categories: List[str]) -> Optional[str]:
    """Optional re.search patterns from intent category markdown frontmatter."""
    entries = config.get("_doc_pattern_entries")
    if not isinstance(entries, list) or not entries:
        return None
    allowed = {str(c).strip() for c in categories if c is not None and str(c).strip()}
    q = (query or "").strip()
    if not q:
        return None
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        cid = (ent.get("id") or "").strip()
        if not cid or cid not in allowed:
            continue
        for pat in ent.get("patterns") or []:
            if not isinstance(pat, str) or not pat.strip():
                continue
            try:
                if re.search(pat, q):
                    return cid
            except re.error as e:
                logger.warning("intent category match_patterns invalid regex {!r}: {}", pat, e)
    return None


def _normalize_category(raw: str, allowed: List[str]) -> str:
    """Map LLM reply to a known category id; return general_chat on failure."""
    if not raw or not isinstance(raw, str):
        return "general_chat"
    s = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if not s:
        return "general_chat"
    # Exact match: return canonical form from allowed list
    for c in allowed:
        cn = (c or "").strip().lower().replace(" ", "_").replace("-", "_")
        if cn and cn == s:
            return c.strip()
    # Fuzzy: allow substring match
    for c in allowed:
        cn = (c or "").strip().lower().replace(" ", "_").replace("-", "_")
        if cn and (s in cn or cn in s):
            return c.strip()
    return "general_chat"


def _query_matches_list_files_intent(query: str) -> bool:
    """Phrasing for list/browse folder contents; must run before semantic so embeddings cannot override (e.g. -> coding)."""
    if not query or not isinstance(query, str) or not query.strip():
        return False
    q_raw = query.strip()
    q_lo = q_raw.lower()
    return bool(
        "里有什么" in q_raw
        or "里有哪些" in q_raw
        or ("list" in q_lo and ("file" in q_lo or "folder" in q_lo or "content" in q_lo or "directory" in q_lo))
        or (
            "what" in q_lo
            and ("in " in q_lo or "inside" in q_lo)
            and ("folder" in q_lo or "file" in q_lo or "directory" in q_lo or "images" in q_lo or "documents" in q_lo)
        )
        or ("show" in q_lo and ("file" in q_lo or "folder" in q_lo or "content" in q_lo))
        or "有哪些文件" in q_raw
        or "有什么文件" in q_raw
        or "有什么图片" in q_raw
    )


def _query_matches_get_file_link_intent(query: str) -> bool:
    """Match explicit file/image/link sending requests while avoiding news/web-share phrasing."""
    if not query or not isinstance(query, str) or not query.strip():
        return False
    q_raw = query.strip()
    q_lo = q_raw.lower()
    has_send_phrase = (
        "发给我" in q_raw
        or ("send" in q_lo and "me" in q_lo and ("file" in q_lo or "image" in q_lo or "that" in q_lo or "link" in q_lo))
    )
    if not has_send_phrase:
        return False

    # Do not hijack requests like "把最新新闻发给我" unless there is a clear file/path cue.
    looks_like_news_share = any(
        k in q_raw for k in ("新闻", "头条", "快讯")
    ) or any(
        k in q_lo for k in ("news", "headline", "breaking")
    )

    has_path_or_filename = bool(
        re.search(r"[A-Za-z0-9_\-./]+\.(?:pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|txt|md|csv|zip|mp3|mp4)\b", q_lo)
        or "/" in q_raw
        or "\\" in q_raw
    )
    has_file_noun = (
        "文件" in q_raw
        or "图片" in q_raw
        or "文档" in q_raw
        or "pdf" in q_lo
        or "doc" in q_lo
        or "image" in q_lo
        or "file" in q_lo
    )
    if looks_like_news_share and not has_path_or_filename:
        return False
    return bool(has_path_or_filename or has_file_noun)


def _query_matches_web_news_search_intent(query: str) -> bool:
    """
    User wants to search the web for news/headlines (not get_file_link).
    High precision: must combine a search verb with news/资讯-style topic cues.
    """
    q_raw = (query or "").strip()
    if not q_raw:
        return False
    q_lo = q_raw.lower()
    if any(p in q_raw for p in ("新闻", "资讯", "头条", "消息")):
        if any(
            p in q_raw
            for p in ("搜", "搜索", "搜一下", "查一下", "查", "看看", "浏览", "找一下", "帮我搜", "上网搜")
        ):
            return True
    if "搜" in q_raw and ("最新" in q_raw or "资讯" in q_raw):
        return True
    if ("news" in q_lo or "headline" in q_lo) and any(
        p in q_lo for p in ("search", "latest", "current", "today", "look up", "lookup", "find ")
    ):
        return True
    return False


def _query_is_short_greeting(query: str) -> bool:
    """Short greeting/thanks only; excludes question-like asks."""
    if not query or not isinstance(query, str):
        return False
    q_raw = query.strip()
    if not q_raw or len(q_raw) > 30:
        return False
    q_lo = q_raw.lower()
    greeting_phrases = ("你好", "hi", "hello", "嗨", "hey", "thanks", "谢谢", "thank you", "哈喽")
    has_greeting = any((p in q_lo if p.isascii() else p in q_raw) for p in greeting_phrases)
    if not has_greeting:
        return False
    has_question_cue = any(c in q_raw for c in ("?", "？", "吗", "什么", "怎么")) or any(
        p in q_lo for p in ("how", "what", "why", "can you", "帮我")
    )
    return not has_question_cue


def _format_recent_context(
    recent_messages: List[Dict[str, Any]],
    max_chars_per_message: int,
) -> str:
    """Format last N messages for router context; each content truncated to max_chars_per_message. Never raises."""
    if not recent_messages or max_chars_per_message <= 0:
        return ""
    lines = []
    try:
        for m in recent_messages:
            if not isinstance(m, dict):
                continue
            role = (m.get("role") or "user").strip().lower()
            if role not in ("user", "assistant"):
                continue
            content = (m.get("content") or "").strip()
            if content:
                if len(content) > max_chars_per_message:
                    content = content[: max_chars_per_message] + "…"
                lines.append(f"{role.capitalize()}: {content}")
    except Exception:
        pass
    if not lines:
        return ""
    return "Recent context:\n" + "\n".join(lines)


async def _route_semantic_intent(
    query: str,
    config: Dict[str, Any],
    categories: List[str],
    semantic_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Return semantic route result (category or comma-separated), or None when no semantic hit."""
    sem_cfg = config.get("semantic") if isinstance(config.get("semantic"), dict) else {}
    if not bool(sem_cfg.get("enabled", True)):
        return None
    ctx = semantic_context if isinstance(semantic_context, dict) else {}
    vs = ctx.get("vector_store")
    emb = ctx.get("embedder")
    if vs is None or emb is None:
        return None
    top_k = max(1, min(100, int(sem_cfg.get("top_k", 20) or 20)))
    min_score = float(sem_cfg.get("threshold", 0.0) or 0.0)
    final_top_n = max(1, min(5, int(sem_cfg.get("final_top_n", 2) or 2)))
    accept_top_n = max(1, min(final_top_n, int(sem_cfg.get("accept_top_n", 1) or 1)))
    margin = float(sem_cfg.get("margin_threshold", 0.08) or 0.08)
    hits = await search_intent_categories_by_query(
        vector_store=vs,
        embedder=emb,
        query=query or "",
        limit=top_k,
        min_similarity=min_score,
        allowed_categories=categories,
    )
    if not hits:
        return None
    hits = rerank_intent_hits(query or "", hits)
    rr_cfg = sem_cfg.get("reranker") if isinstance(sem_cfg.get("reranker"), dict) else {}
    if rr_cfg.get("enabled"):
        try:
            from pathlib import Path

            docs_dir = str(sem_cfg.get("docs_dir") or "config/intent_category").strip() or "config/intent_category"
            p = Path(docs_dir)
            if not p.is_absolute():
                from base.util import Util

                p = Path(Util().root_path()).resolve() / docs_dir
            docs = load_intent_category_docs(p, allowed_categories=categories)
            doc_map = {str(d.get("id") or ""): d for d in docs}
            candidates = []
            for cid, _sc in hits[: max(1, int(sem_cfg.get("rerank_top_n", 10) or 10))]:
                d = doc_map.get(cid) or {}
                txt = "\n".join(
                    [
                        str(d.get("display_name") or cid),
                        str(d.get("text") or ""),
                    ]
                ).strip()
                candidates.append({"id": cid, "text": txt})
            rr_scores = await rerank_with_local_model(
                query=query or "",
                candidates=candidates,
                reranker_cfg={**rr_cfg, "log_tag": "intent_router"},
            )
            hits = apply_rerank_scores(hits, rr_scores)
        except Exception as e:
            logger.debug("Intent router model rerank skipped: {}", e)
    picked: List[str] = []
    if hits:
        picked.append(hits[0][0])
        if accept_top_n > 1 and len(hits) > 1:
            if (hits[0][1] - hits[1][1]) <= margin:
                picked.append(hits[1][0])
    picked = [p for p in picked[:accept_top_n] if p in categories]
    if not picked:
        return None
    return ",".join(picked)


async def route(
    query: str,
    config: Dict[str, Any],
    completion_fn: Any,
    llm_name: Optional[str] = None,
    recent_messages: Optional[List[Dict[str, Any]]] = None,
    semantic_context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Classify the user message into exactly one category via one short LLM call.

    Args:
        query: User message to classify.
        config: intent_router config (enabled, categories, category_tools, include_recent_turns, recent_turns_max_chars).
        completion_fn: Async callable(messages, llm_name=None) -> str, e.g. core.openai_chat_completion.
        llm_name: Optional model ref for router (e.g. smaller/faster); None = use default.
        recent_messages: Optional chat history (list of {role, content}). Used when include_recent_turns > 0.

    Returns:
        Category id (e.g. "search_web", "general_chat"). On parse failure or timeout returns "general_chat".
    """
    if not config or not isinstance(config, dict) or not config.get("enabled"):
        return "general_chat"
    config = _merge_intent_router_config(config)
    try:
        categories = config.get("categories") or DEFAULT_CATEGORIES
    except Exception:
        categories = DEFAULT_CATEGORIES
    if not isinstance(categories, list):
        categories = DEFAULT_CATEGORIES
    try:
        categories = [str(c).strip() for c in categories if c is not None and str(c).strip()]
    except Exception:
        categories = list(DEFAULT_CATEGORIES)
    if not categories:
        return "general_chat"
    mode = str(config.get("mode") or "static").strip().lower()
    sem_cfg = config.get("semantic") if isinstance(config.get("semantic"), dict) else {}

    # Weather keywords before semantic: embedding similarity can mislabel e.g. 北京明天天气怎么样 as "coding".
    # Same rules as the static weather block below; must run even when mode==semantic (see tests).
    try:
        if query and isinstance(query, str) and query.strip() and "weather" in categories:
            q_lo = query.strip().lower()
            q_raw = query.strip()
            if (
                "weather" in q_lo
                or "forecast" in q_lo
                or "temperature" in q_lo
                or "wttr" in q_lo
                or "天气" in q_raw
                or "气温" in q_raw
                or "天气预报" in q_raw
            ):
                logger.debug("Intent router: early weather preempt (before semantic) -> category weather")
                return "weather"
    except Exception as e:
        logger.debug("Intent router early weather preempt failed (non-fatal): {}", e)

    # List-files phrasing before semantic: similarity can mislabel e.g. 我有哪些文件？ as "coding"; DAG list_files returns full folder_list output.
    try:
        if query and isinstance(query, str) and query.strip() and "list_files" in categories:
            if _query_matches_list_files_intent(query.strip()):
                logger.debug("Intent router: early list_files preempt (before semantic) -> category list_files")
                return "list_files"
    except Exception as e:
        logger.debug("Intent router early list_files preempt failed (non-fatal): {}", e)

    # Web/news search before semantic: hybrid semantic can mislabel e.g. 搜一下…新闻…发给我 as greeting.
    try:
        if query and isinstance(query, str) and query.strip() and "search_web" in categories:
            if _query_matches_web_news_search_intent(query.strip()):
                logger.debug("Intent router: early web/news search preempt (before semantic) -> category search_web")
                return "search_web"
    except Exception as e:
        logger.debug("Intent router early web/news search preempt failed (non-fatal): {}", e)

    # Greeting/thanks before semantic: short social turns should never be mislabeled as coding.
    try:
        if query and isinstance(query, str) and query.strip() and "greeting" in categories:
            if _query_is_short_greeting(query):
                logger.debug("Intent router: early greeting preempt (before semantic) -> category greeting")
                return "greeting"
    except Exception as e:
        logger.debug("Intent router early greeting preempt failed (non-fatal): {}", e)

    # Semantic-only mode: skip static preempts/hot rules; semantic first, then classifier fallback if enabled.
    if mode == "semantic":
        try:
            _sem = await _route_semantic_intent(query, config, categories, semantic_context=semantic_context)
            if _sem:
                logger.debug("Intent router semantic matched -> {}", _sem)
                return _sem
            if not bool(sem_cfg.get("fail_open_to_static", True)):
                return "general_chat"
        except Exception as e:
            logger.debug("Intent router semantic failed (non-fatal): {}", e)

    # Stocks / watchlist: never "memory" (run_skill would be stripped). Prefer stock_monitor + DAG run_skill(portfolio) when configured; else general_chat.
    try:
        if query is not None and isinstance(query, str) and query.strip():
            q_lo = query.strip().lower()
            q_raw = query.strip()
            if (
                any(p in q_lo for p in ("portfolio", "watchlist", "ticker", "stock", "stocks"))
                or any(
                    p in q_raw
                    for p in (
                        "股票",
                        "持仓",
                        "行情",
                        "股价",
                        "自选股",
                        "大盘",
                        "涨停",
                        "跌停",
                        "个股",
                        "A股",
                        "港股",
                        "美股",
                    )
                )
            ):
                if "stock_monitor" in categories:
                    logger.debug("Intent router: stock/watchlist query -> category stock_monitor (preempt LLM)")
                    return "stock_monitor"
                logger.debug("Intent router: stock/watchlist query -> category general_chat (preempt LLM)")
                return "general_chat"
    except Exception as e:
        logger.debug("Intent router stock preempt failed (non-fatal): {}", e)

    # When user explicitly asks for HTML slides, route to create_html_slides so the html-slides skill runs (not summarize_to_page → markdown).
    try:
        if "create_html_slides" in categories and query is not None and isinstance(query, str) and query.strip():
            q = query.strip().lower()
            if (
                "html slides" in q
                or "html_slides" in q
                or "html-slides" in q
                or ("生成" in query and "html" in q)
                or "html幻灯片" in query
                or "html 幻灯片" in q
            ):
                logger.debug("Intent router: query matches HTML slides -> category create_html_slides")
                return "create_html_slides"
    except Exception as e:
        logger.debug("Intent router HTML slides pre-check failed (non-fatal): {}", e)

    # When user asks to list files/folder contents (e.g. "images里有什么图片", "documents里有什么"), route to list_files so DAG runs folder_list and we don't block on slow LLM.
    try:
        if "list_files" in categories and query is not None and isinstance(query, str) and query.strip():
            if _query_matches_list_files_intent(query.strip()):
                logger.debug("Intent router: query matches list folder -> category list_files")
                return "list_files"
    except Exception as e:
        logger.debug("Intent router list_files pre-check failed (non-fatal): {}", e)

    # When user asks to get/send a file or image link (e.g. "把img1.png发给我", "send me that file"), route to get_file_link so DAG runs get_file_view_link with path from context.
    try:
        if "get_file_link" in categories and query is not None and isinstance(query, str) and query.strip():
            if _query_matches_get_file_link_intent(query.strip()):
                logger.debug("Intent router: query matches get/send file -> category get_file_link")
                return "get_file_link"
    except Exception as e:
        logger.debug("Intent router get_file_link pre-check failed (non-fatal): {}", e)

    # Skill-like intents: route away from search_web so skill/tool selection can happen.
    # These are high-precision phrase checks (short, stable keywords) to avoid false positives.
    try:
        if "general_chat" in categories and query is not None and isinstance(query, str) and query.strip():
            q_lo = query.strip().lower()
            q_raw = query.strip()

            # Baidu search skill (explicitly asked for Baidu/百度/智能搜索)
            if any(p in q_raw for p in ("百度搜索", "用百度搜", "智能搜索")) or "baidu search" in q_lo:
                logger.debug("Intent router: query matches Baidu search skill -> category general_chat")
                return "general_chat"

            # RSS / Daily brief: prefer news_digest (DAG run_skill) when that category exists; else general_chat + run_skill.
            if any(p in q_lo for p in ("daily brief", "morning report", "rss")) or any(
                p in q_raw for p in ("新闻订阅", "今日新闻", "每日简报", "头条新闻", "rss摘要")
            ):
                if "news_digest" in categories:
                    logger.debug("Intent router: query matches daily-brief -> category news_digest (preempt)")
                    return "news_digest"
                logger.debug("Intent router: query matches daily-brief skill -> category general_chat")
                return "general_chat"

            # Stocks: handled by early preempt (stock_monitor or general_chat).

    except Exception as e:
        logger.debug("Intent router skill-intent pre-check failed (non-fatal): {}", e)

    # Hot intents: preempt to category so DAG runs (or narrow ReAct) without the classifier LLM.
    # Placed after weather so 天气/forecast queries stay weather, not search_web.
    try:
        if query is not None and isinstance(query, str) and query.strip():
            q_raw = query.strip()
            q_lo = q_raw.lower()
            _wx = (
                "天气" in q_raw
                or "气温" in q_raw
                or "天气预报" in q_raw
                or "weather" in q_lo
                or "forecast" in q_lo
                or "wttr" in q_lo
            )
            if "search_web" in categories and not _wx:
                if (
                    "上网搜" in q_raw
                    or "网上搜索" in q_raw
                    or "查一下网上" in q_raw
                    or "search the web" in q_lo
                    or "web search" in q_lo
                    or "look it up online" in q_lo
                    or "google it" == q_lo.strip()
                    or "百度一下" in q_raw
                    or ("百度" in q_raw and "搜" in q_raw)
                ):
                    logger.debug("Intent router: query matches search_web -> category search_web (preempt)")
                    return "search_web"
            if "summarize_to_page" in categories:
                if (
                    "总结成网页" in q_raw
                    or "总结到页面" in q_raw
                    or "summary page" in q_lo
                    or "summarize to a page" in q_lo
                    or "readable page" in q_lo
                ):
                    logger.debug("Intent router: query matches summarize_to_page -> category summarize_to_page (preempt)")
                    return "summarize_to_page"
            if "send_email" in categories:
                if (
                    "发封邮件" in q_raw
                    or "发邮件" in q_raw
                    or ("写邮件" in q_raw and "给" in q_raw)
                    or "send an email" in q_lo
                    or "send email to" in q_lo
                    or "write an email" in q_lo
                    or "write me an email" in q_lo
                ):
                    logger.debug("Intent router: query matches send_email -> category send_email (preempt)")
                    return "send_email"
            if "schedule_remind" in categories:
                if (
                    "提醒我" in q_raw
                    or "定个闹钟" in q_raw
                    or "定个提醒" in q_raw
                    or "remind me" in q_lo
                    or "set a reminder" in q_lo
                    or "set reminder" in q_lo
                ):
                    logger.debug("Intent router: query matches schedule_remind -> category schedule_remind (preempt)")
                    return "schedule_remind"
            if "open_url" in categories and ("http://" in q_raw or "https://" in q_raw):
                if (
                    "打开" in q_raw
                    or "访问" in q_raw
                    or "点开" in q_raw
                    or "open " in q_lo
                    or "visit " in q_lo
                    or "go to " in q_lo
                ):
                    logger.debug("Intent router: query matches open_url -> category open_url (preempt)")
                    return "open_url"
            if "memory" in categories:
                if (
                    q_raw.startswith("请记住")
                    or q_raw.startswith("帮我记住")
                    or q_lo.startswith("remember this:")
                    or q_lo.startswith("save to memory:")
                ):
                    logger.debug("Intent router: query matches memory -> category memory (preempt)")
                    return "memory"
            if "knowledge_base" in categories:
                # Chinese: 知识库 + clear action
                if "知识库" in q_raw and (
                    "搜索" in q_raw or "查找" in q_raw or "添加" in q_raw or "保存到" in q_raw
                ):
                    logger.debug("Intent router: query matches knowledge_base -> category knowledge_base (preempt)")
                    return "knowledge_base"
                # English / mixed: explicit "knowledge base" or word "kb" + search/add/list/remove cue
                _kb_scope = (
                    "knowledge base" in q_lo
                    or bool(re.search(r"\bkb\b", q_lo))
                    or "my kb" in q_lo
                    or "in my kb" in q_lo
                    or q_lo.startswith("kb ")
                )
                # Word-boundary verbs so "research" does not match "search"
                _kb_action = bool(
                    re.search(
                        r"\b(search|find|lookup|list|add|append|remove|delete|query)\b",
                        q_lo,
                    )
                ) or "look up" in q_lo or "what's in" in q_lo or "what is in" in q_lo or "save to" in q_lo
                _kb_action = _kb_action or any(
                    p in q_raw for p in ("检索", "查找", "搜索", "添加", "保存到", "删除", "列出")
                )
                if _kb_scope and _kb_action:
                    logger.debug("Intent router: query matches knowledge_base (EN/KB scope) -> category knowledge_base (preempt)")
                    return "knowledge_base"
            if "identity_capabilities" in categories:
                if (
                    any(p in q_raw for p in ("你能为我做什么", "你能做什么", "你能帮我做什么", "你有什么功能", "介绍你自己", "你是谁"))
                    or any(
                        p in q_lo
                        for p in (
                            "what can you do",
                            "who are you",
                            "what are your capabilities",
                            "introduce yourself",
                            "what can you do for me",
                        )
                    )
                ):
                    logger.debug("Intent router: query matches identity/capabilities -> category identity_capabilities (preempt)")
                    return "identity_capabilities"
    except Exception as e:
        logger.debug("Intent router hot-intent preempt failed (non-fatal): {}", e)

    # Image generation requests: route to image category so only image-related tools/skills are available.
    try:
        if "image" in categories and query is not None and isinstance(query, str) and query.strip():
            q = query.strip().lower()
            if (
                "generate image" in q
                or "create image" in q
                or "make an image" in q
                or "draw" in q and "image" in q
                or "生成图片" in query
                or "创建图片" in query
                or "生成" in query and "图" in query
                or "画" in query and "图" in query
            ):
                logger.debug("Intent router: query matches image generation -> category image")
                return "image"
    except Exception as e:
        logger.debug("Intent router image pre-check failed (non-fatal): {}", e)

    # PPT / slides: route to create_slides when available.
    try:
        if "create_slides" in categories and query is not None and isinstance(query, str) and query.strip():
            q = query.strip().lower()
            if (
                ".pptx" in q
                or "powerpoint" in q
                or "ppt" in q
                or "幻灯片" in query
                or "做个ppt" in query
                or "生成ppt" in query
                or ("生成" in query and "PPT" in query)
            ):
                logger.debug("Intent router: query matches PPT/slides -> category create_slides")
                return "create_slides"
    except Exception as e:
        logger.debug("Intent router create_slides pre-check failed (non-fatal): {}", e)

    # When user explicitly asks to convert Markdown to PDF (e.g. "convert X.md to PDF", "把X.md转成PDF"),
    # route directly to generate_pdf so the fixed DAG (document_read -> markdown_to_pdf) runs and uses
    # VMPrint/pandoc/weasyprint instead of generic file_write. This makes Markdown→PDF behavior consistent
    # and avoids hallucinated PDFs.
    try:
        if "generate_pdf" in categories and query is not None and isinstance(query, str) and query.strip():
            q = query.strip().lower()
            has_pdf = "pdf" in q
            has_md = ".md" in q or "markdown" in q or "mark down" in q or "md文" in query or "markdown文" in query
            mentions_convert = (
                "convert" in q
                or "to pdf" in q
                or "export" in q and "pdf" in q
                or "转成pdf" in query
                or "转为pdf" in query
                or "生成pdf" in query
                or "导出为pdf" in query
            )
            if has_pdf and has_md and mentions_convert:
                logger.debug("Intent router: query matches markdown->PDF convert -> category generate_pdf")
                return "generate_pdf"
    except Exception as e:
        logger.debug("Intent router generate_pdf pre-check failed (non-fatal): {}", e)

    # Doc-defined regex patterns (YAML frontmatter match_patterns in config/intent_category/*.md).
    try:
        _doc_hit = _match_doc_category_patterns(query or "", config, categories)
        if _doc_hit:
            logger.debug("Intent router: intent_category doc match_patterns -> category {}", _doc_hit)
            return _doc_hit
    except Exception as e:
        logger.debug("Intent router doc pattern match failed (non-fatal): {}", e)

    # Semantic intent routing: vector retrieve + lightweight rerank over category docs.
    # mode:
    #   - static  : skip semantic
    #   - semantic: semantic only (fallback general_chat or classifier based on fail_open_to_static)
    #   - hybrid  : semantic first, then static classifier fallback
    try:
        # Hybrid mode: static preempts first, then semantic before classifier fallback.
        if mode == "hybrid":
            _sem = await _route_semantic_intent(query, config, categories, semantic_context=semantic_context)
            if _sem:
                logger.debug("Intent router semantic matched -> {}", _sem)
                return _sem
    except Exception as e:
        logger.debug("Intent router semantic failed (non-fatal): {}", e)

    try:
        include_turns = max(0, int(config.get("include_recent_turns", 0) or 0))
    except (TypeError, ValueError):
        include_turns = 0
    try:
        max_chars = max(0, int(config.get("recent_turns_max_chars", 300) or 300))
    except (TypeError, ValueError):
        max_chars = 300
    recent_block = ""
    if include_turns > 0 and recent_messages:
        # Last N exchanges = 2*N messages (user + assistant each)
        take = min(len(recent_messages), include_turns * 2)
        last_m = recent_messages[-take:] if take else []
        recent_block = _format_recent_context(last_m, max_chars)
    categories_text = _format_categories_for_prompt(categories, config)
    if recent_block:
        prompt = (
            "Classify this user message into one category, or two categories if the request clearly needs multiple types of actions (e.g. search then save, read then create slides). "
            "Reply with only the category name(s), nothing else. If two categories, separate with a comma, e.g. search_web, list_files.\n\n"
            "Categories:\n" + categories_text + "\n\n"
            + recent_block + "\n\n"
            "Current message: " + (query or "")[:2000]
        )
    else:
        prompt = (
            "Classify this user message into one category, or two categories if the request clearly needs multiple types of actions (e.g. search then save, read then create slides). "
            "Reply with only the category name(s), nothing else. If two categories, separate with a comma, e.g. search_web, list_files.\n\n"
            "Categories:\n" + categories_text + "\n\n"
            "User message: " + (query or "")[:2000]
        )
    system_content = (
        "You are a classifier. Reply with one category name, or two comma-separated category names if the request needs multiple types of actions. "
        "If the user asks for HTML slides (e.g. 'html slides', '生成html slides', '生成幻灯片'), choose create_html_slides, not summarize_to_page."
    )
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    try:
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(
                messages=messages,
                llm_name=llm_name,
            )
        else:
            response = await completion_fn(messages, llm_name=llm_name)
        if not response or not isinstance(response, str):
            return "general_chat"
        # Allow comma-separated categories (e.g. "search_web, list_files"); normalize each part.
        parts = [p.strip() for p in response.split(",") if (p or "").strip()]
        if not parts:
            return "general_chat"
        normalized = [_normalize_category(p, categories) for p in parts]
        # Deduplicate while preserving order; drop general_chat if we have another category.
        seen = set()
        unique = []
        for c in normalized:
            if c not in seen:
                seen.add(c)
                if c == "general_chat" and len(normalized) > 1:
                    continue  # skip general_chat when user asked for multiple
                unique.append(c)
        if not unique:
            return "general_chat"
        category = unique[0] if len(unique) == 1 else ",".join(unique)
        logger.debug("Intent router: query truncated -> category {}", category)
        return category
    except Exception as e:
        logger.debug("Intent router failed: {}; fallback general_chat", e)
        return "general_chat"


def get_tools_filter_for_category(
    config: Dict[str, Any],
    category: str,
) -> Optional[Dict[str, Any]]:
    """
    Return the tool filter for a category: either {profile: "minimal"} or {tools: ["web_search", ...]}.
    Used by llm_loop to filter tools after routing. None = no filter (use full tools). Never raises.
    """
    try:
        if not config or not isinstance(config, dict) or not category or not isinstance(category, str):
            return None
        category_tools = config.get("category_tools") or config.get("category_profile") or {}
        if not isinstance(category_tools, dict):
            return None
        cat_key = (category or "").strip().lower().replace(" ", "_").replace("-", "_")
        if not cat_key:
            return None
        for k, v in category_tools.items():
            if not isinstance(v, dict):
                continue
            k_norm = (str(k) if k is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
            if k_norm == cat_key:
                return v
        return None
    except Exception:
        return None


def get_skills_filter_for_category(
    config: Dict[str, Any],
    category: str,
) -> Optional[List[str]]:
    """
    Return the skill folder allowlist for a category, if any (Phase 3.1).
    When present, llm_loop filters skills_list to only these folders so skill_name enum matches router output. Never raises.
    """
    try:
        if not config or not category:
            return None
        cat_filter = get_tools_filter_for_category(config, category)
        if not cat_filter:
            return None
        skills = cat_filter.get("skills")
        if not isinstance(skills, list):
            return None
        return [str(s).strip() for s in skills if s is not None and str(s).strip()]
    except Exception:
        return None


def get_tools_filter_for_categories(
    config: Dict[str, Any],
    categories: List[str],
) -> Optional[Dict[str, Any]]:
    """
    Return a merged tool filter for multiple categories (union of tools from each).
    Used when the router returns comma-separated categories (e.g. "search_web, list_files").
    If any category has profile "full", returns None (no filter = full tools).
    Otherwise returns { "tools": [ ... ] } with the union of tool names from each category's
    profile (resolved via get_tool_names_for_profile) or explicit tools list. Never raises.
    """
    if not categories or not isinstance(categories, list):
        return None
    try:
        union_names = set()
        for cat in categories:
            if not cat or not isinstance(cat, str):
                continue
            cat = (cat or "").strip()
            if not cat:
                continue
            cat_filter = get_tools_filter_for_category(config, cat)
            if not cat_filter or not isinstance(cat_filter, dict):
                continue
            profile = (cat_filter.get("profile") or "").strip()
            if profile and str(profile).strip().lower() == "full":
                return None  # any "full" => no filter
            if profile:
                for name in get_tool_names_for_profile(profile):
                    if name:
                        union_names.add(name)
            tools_list = cat_filter.get("tools")
            if isinstance(tools_list, list):
                for t in tools_list:
                    if t is not None and str(t).strip():
                        union_names.add(str(t).strip())
        if not union_names:
            return None
        return {"tools": sorted(union_names)}
    except Exception:
        return None


def get_skills_filter_for_categories(
    config: Dict[str, Any],
    categories: List[str],
) -> Optional[List[str]]:
    """
    Return the union of skill folder allowlists for the given categories.
    Used when the router returns comma-separated categories. Categories with no skills
    in config add nothing to the union. If the union is empty, returns None (no filter). Never raises.
    """
    if not categories or not isinstance(categories, list):
        return None
    try:
        union = set()
        for cat in categories:
            if not cat or not isinstance(cat, str):
                continue
            skills = get_skills_filter_for_category(config, (cat or "").strip())
            if isinstance(skills, list):
                for s in skills:
                    if s is not None and str(s).strip():
                        union.add(str(s).strip())
        if not union:
            return None
        return sorted(union)
    except Exception:
        return None


# Phase 3.3: tools that may get a verification step (exec, file_write)
DEFAULT_VERIFY_TOOLS = ("exec", "file_write")


async def verify_tool_selection(
    query: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    completion_fn: Any,
) -> bool:
    """
    Optional Phase 3.3: one short LLM call to check if the selected tool matches user intent.
    Returns True to proceed with execution, False to skip (caller should use a skip message as result). Never raises.
    """
    if not completion_fn:
        return True
    try:
        query_safe = (query or "")[:500] if isinstance(query, str) else ""
        args_safe = tool_args if isinstance(tool_args, dict) else {}
        prompt = (
            f"User said: {query_safe}\n\n"
            f"The model chose to call tool: {tool_name} with arguments: {args_safe}\n\n"
            "Does this match the user's intent? Reply only Yes or No."
        )
        messages = [
            {"role": "system", "content": "You are a verifier. Reply only Yes or No."},
            {"role": "user", "content": prompt},
        ]
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(messages=messages)
        else:
            response = await completion_fn(messages) if callable(completion_fn) else None
        if not response or not isinstance(response, str):
            return True  # on failure, allow execution
        r = response.strip().lower()
        if r.startswith("no") or r == "n":
            logger.debug("Tool verification: intent mismatch for {} -> skip", tool_name)
            return False
        return True
    except Exception as e:
        logger.debug("Tool verification failed: {}; allow execution", e)
        return True
