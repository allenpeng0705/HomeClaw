"""
Intent router (Phase 2): one short LLM call classifies user query into a category.
Category is then used to filter tools (and optionally skills) before the main LLM turn.

Principle: Do not use tables, phrase lists, or regexes for intent logic when the LLM
can do it. This module uses exactly one LLM completion for query -> category.

Phase 3.2 fallback: On parse failure, timeout, or any exception, route() returns
"general_chat" so the main turn gets full tools (or config profile).
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from base.tool_profiles import get_tool_names_for_profile


# Default categories when not in config (must match docs_design/IntentRouter_CategoriesCoverage.md)
DEFAULT_CATEGORIES = [
    "search_web",
    "list_files",
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
    "general_chat",
    "coding",
]

# Optional default descriptions for router prompt (used when config has no category_descriptions)
DEFAULT_CATEGORY_DESCRIPTIONS: Dict[str, str] = {
    "search_web": "User wants to search the web or look up information online.",
    "list_files": "User wants to list, browse, or find files or folders.",
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
    "general_chat": "General conversation, question, or intent that does not fit a specific category above.",
    "coding": "User wants to run code, edit files, use dev tools, or automate something.",
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


async def route(
    query: str,
    config: Dict[str, Any],
    completion_fn: Any,
    llm_name: Optional[str] = None,
    recent_messages: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Classify the user message into exactly one category via one short LLM call.

    Args:
        query: User message to classify.
        config: intent_router config (enabled, categories, optional category_tools, include_recent_turns, recent_turns_max_chars).
        completion_fn: Async callable(messages, llm_name=None) -> str, e.g. core.openai_chat_completion.
        llm_name: Optional model ref for router (e.g. smaller/faster); None = use default.
        recent_messages: Optional chat history (list of {role, content}). Used when include_recent_turns > 0.

    Returns:
        Category id (e.g. "search_web", "general_chat"). On parse failure or timeout returns "general_chat".
    """
    if not config or not isinstance(config, dict) or not config.get("enabled"):
        return "general_chat"
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
    messages = [
        {"role": "system", "content": "You are a classifier. Reply with one category name, or two comma-separated category names if the request needs multiple types of actions."},
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
