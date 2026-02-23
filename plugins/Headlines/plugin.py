"""
Headlines plugin: fetch top headlines from News API. Parameters (country, category, sources,
page_size, q, language) come from user message or config; language defaults to main model first language.
Scheduling: cron_schedule(task_type='run_plugin', plugin_id='headlines', ...).
See https://newsapi.org/docs/endpoints/top-headlines and https://newsapi.org/docs/endpoints/sources
"""
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from base.BasePlugin import BasePlugin
from base.util import Util
from core.coreInterface import CoreInterface

try:
    import requests
except ImportError:
    requests = None

try:
    from loguru import logger
except ImportError:
    logger = logging.getLogger(__name__)


# Map main_llm_language (e.g. en, zh, ja) to News API language codes.
# News API: ar, de, en, es, fr, he, it, nl, no, pt, ru, sv, ud, zh
_LANG_TO_NEWS_API = {
    "ar": "ar", "de": "de", "en": "en", "es": "es", "fr": "fr",
    "he": "he", "it": "it", "nl": "nl", "no": "no", "pt": "pt",
    "ru": "ru", "sv": "sv", "zh": "zh", "zh-cn": "zh", "zh-tw": "zh",
    "ja": "en", "ko": "en", "ud": "ud",
}


def _news_api_language(main_lang: Optional[str]) -> str:
    """Map main model first language to News API code. Default en when not supported."""
    if not main_lang or not isinstance(main_lang, str):
        return "en"
    key = main_lang.strip().lower()[:5]
    return _LANG_TO_NEWS_API.get(key) or _LANG_TO_NEWS_API.get(key[:2]) or "en"


# Common source names (user says "from BBC") -> News API source id
_SOURCE_NAME_TO_ID = {
    "bbc": "bbc-news",
    "bbc news": "bbc-news",
    "techcrunch": "techcrunch",
    "the verge": "the-verge",
    "verge": "the-verge",
    "cnn": "cnn",
    "reuters": "reuters",
    "associated press": "associated-press",
    "ap": "associated-press",
    "al jazeera": "al-jazeera-english",
    "bloomberg": "bloomberg",
    "espn": "espn",
    "fox news": "fox-news",
    "google news": "google-news",
    "hacker news": "hacker-news",
    "ign": "ign",
    "national geographic": "national-geographic",
    "nbc": "nbc-news",
    "polygon": "polygon",
    "the economist": "the-economist",
    "the guardian": "the-guardian",
    "guardian": "the-guardian",
    "the hill": "the-hill",
    "the huffington post": "the-huffington-post",
    "huffpost": "the-huffington-post",
    "time": "time",
    "usa today": "usa-today",
    "wired": "wired",
}

_ALLOWED_CATEGORIES = frozenset(
    ("business", "entertainment", "general", "health", "science", "sports", "technology")
)


def _normalize_source(user_input: str) -> str:
    """Map user-friendly name (e.g. BBC, TechCrunch) to News API source id. Accepts comma-separated."""
    if not user_input or not isinstance(user_input, str):
        return ""
    out = []
    for part in (user_input or "").strip().split(","):
        part = part.strip().lower()
        if not part:
            continue
        if "-" in part and " " not in part:
            out.append(part)
            continue
        out.append(_SOURCE_NAME_TO_ID.get(part) or part.replace(" ", "-"))
    return ",".join(out) if out else ""


class HeadlinesPlugin(BasePlugin):
    def __init__(self, coreInst: CoreInterface):
        super().__init__(coreInst=coreInst)
        self.config: Dict[str, Any] = {}
        try:
            config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.yml")
            if os.path.exists(config_path):
                loaded = Util().load_yml_config(config_path) or {}
                self.config = {k: v for k, v in loaded.items() if k not in ("tasks", "keywords")}
        except Exception as e:
            logger.debug("Headlines plugin config load: {}", e)

    def initialize(self):
        if self.initialized:
            return
        try:
            super().initialize()
            self.initialized = True
        except Exception as e:
            logger.debug("Headlines plugin initialize: {}", e)
            self.initialized = True

    def _params_from_request(self) -> Dict[str, Any]:
        """Merge capability_parameters from request with config defaults. Language default from main_llm_language. Normalize sources (BBC -> bbc-news); validate category."""
        params: Dict[str, Any] = {}
        req = getattr(self, "promptRequest", None)
        meta = (getattr(req, "request_metadata", None) or {}) if req else {}
        cap = (meta.get("capability_parameters") or {}) if isinstance(meta, dict) else {}
        if isinstance(cap, dict):
            params.update(cap)

        # Track what user provided (for hint when using defaults)
        user_provided = {
            "category": (params.get("category") or "").strip(),
            "sources": (params.get("sources") or "").strip(),
            "country": (params.get("country") or "").strip(),
            "q": (params.get("q") or "").strip(),
        }

        # Config defaults
        default_country = (self.config.get("default_country") or "us").strip().lower()
        default_category = (self.config.get("default_category") or "general").strip().lower()
        params.setdefault("country", default_country)
        params.setdefault("category", default_category)
        raw_sources = (params.get("sources") or self.config.get("default_sources") or "").strip()
        params["sources"] = _normalize_source(raw_sources) if raw_sources else ""

        # Validate category
        cat = (params.get("category") or "general").strip().lower()
        if cat not in _ALLOWED_CATEGORIES:
            params["category"] = default_category
        else:
            params["category"] = cat

        # page_size: from user ("top 5") or default
        page = params.get("page_size")
        if page is None:
            page = self.config.get("default_page_size", 10)
        try:
            page = max(1, min(100, int(page)))
        except (TypeError, ValueError):
            page = 10
        params["page_size"] = page
        params.setdefault("q", (params.get("q") or "").strip())

        # Language: user-provided, else main model first language; fallback to en when not supported
        if not (params.get("language") or str(params.get("language", "")).strip()):
            first_lang = Util().main_llm_language()
            params["language"] = _news_api_language(first_lang)
        else:
            raw = (str(params["language"]).strip().lower())[:5]
            params["language"] = _news_api_language(raw) or "en"

        params["_user_provided"] = user_provided
        return params

    async def fetch_headlines(self, params: Optional[Dict[str, Any]] = None) -> str:
        """Fetch top headlines and return formatted text. Uses params from request if not given. Never raises."""
        if not requests:
            return "Error: requests is not installed (pip install requests)."
        params = params or self._params_from_request()
        user_provided = params.pop("_user_provided", None) or {}

        base_url = (self.config.get("base_url") or "").strip()
        api_key = (self.config.get("apiKey") or self.config.get("api_key") or "").strip()
        if not base_url or not api_key:
            return "Headlines plugin: base_url and apiKey must be set in config.yml."

        # News API: cannot mix sources with country/category
        sources = (params.get("sources") or "").strip()
        if sources:
            query = {"sources": sources.replace(" ", ""), "apiKey": api_key, "pageSize": params.get("page_size", 10)}
            q = (params.get("q") or "").strip()
            if q:
                query["q"] = q
        else:
            country = (params.get("country") or "us").strip().lower()
            category = (params.get("category") or "general").strip().lower()
            query = {
                "country": country,
                "category": category,
                "apiKey": api_key,
                "pageSize": params.get("page_size", 10),
            }
            lang = (params.get("language") or "").strip()
            if lang:
                query["language"] = lang
            q = (params.get("q") or "").strip()
            if q:
                query["q"] = q

        url = f"{base_url}?{urlencode(query)}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.debug("Headlines fetch {}: {}", url[:80], e)
            return f"Failed to fetch headlines: {e!s}"

        if data.get("status") != "ok":
            err = data.get("message") or data.get("code") or "Unknown error"
            return f"Headlines API error: {err}"

        articles = data.get("articles") or []
        if not articles:
            return "No headlines found for the given filters."

        # Sort by publishedAt descending (guard against None/non-dict items from API)
        sorted_articles = sorted(
            articles,
            key=lambda x: (x or {}).get("publishedAt") or "",
            reverse=True,
        )
        page_size = min(len(sorted_articles), params.get("page_size", 10))
        output_fmt = (params.get("output_format") or self.config.get("default_output_format") or "markdown").strip().lower()
        use_markdown = output_fmt == "markdown"
        if sources:
            header_label = "Headlines"
        else:
            header_label = (params.get("category") or "general").strip().capitalize() + " Headlines"
        parts = []
        for j, article in enumerate(sorted_articles[:page_size]):
            a = article if isinstance(article, dict) else {}
            title = (a.get("title") or "").strip()
            content = (a.get("content") or a.get("description") or "").strip()
            if content:
                content = content[:500] + ("..." if len(content) > 500 else "")
            if title:
                if use_markdown:
                    parts.append(f"{j + 1}. **{title}**\n   {content}" if content else f"{j + 1}. **{title}**")
                else:
                    parts.append(f"{j + 1}. {title}\n   {content}" if content else f"{j + 1}. {title}")

        if use_markdown:
            result = f"## Top {page_size} {header_label}\n\n" + ("\n\n".join(parts) if parts else "No headlines found.")
        else:
            result = "\n\n".join(parts) if parts else "No headlines found."
        # When user gave no filters, add a short hint so they can refine next time
        if user_provided and not any((user_provided.get("category"), user_provided.get("sources"), user_provided.get("q"))):
            result += "\n\nTip: You can say e.g. \"headlines about sports\", \"top 5 from BBC\", or \"what sources are available?\" to filter or choose a source."
        return result

    async def list_sources(self, params: Optional[Dict[str, Any]] = None) -> str:
        """Fetch available sources from News API for user selection. Optional filters: country, category, language. Never raises."""
        if not requests:
            return "Error: requests is not installed (pip install requests)."
        params = params or self._params_from_request()
        params.pop("_user_provided", None)
        base_url = (self.config.get("base_url") or "").strip().replace("/top-headlines", "/top-headlines/sources")
        api_key = (self.config.get("apiKey") or self.config.get("api_key") or "").strip()
        if not base_url or not api_key:
            return "Headlines plugin: base_url and apiKey must be set in config.yml."
        query = {"apiKey": api_key}
        country = (params.get("country") or "").strip().lower()
        if country:
            query["country"] = country
        category = (params.get("category") or "").strip().lower()
        if category and category in _ALLOWED_CATEGORIES:
            query["category"] = category
        lang = (params.get("language") or "").strip()
        if lang:
            query["language"] = lang
        url = f"{base_url}?{urlencode(query)}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.debug("Headlines list_sources {}: {}", url[:80], e)
            return f"Failed to fetch sources: {e!s}"
        if data.get("status") != "ok":
            return data.get("message") or "Sources API error."
        sources_list = data.get("sources") or []
        if not sources_list:
            return "No sources found for the given filters. Try a different country or category."
        lines = ["Available sources (use the id in parentheses when you say \"from X\" or \"headlines from X\"):"]
        for s in sources_list[:30]:
            s = s if isinstance(s, dict) else {}
            sid = (s.get("id") or "").strip()
            name = (s.get("name") or "").strip()
            if sid and name:
                lines.append(f"  • {name} ({sid})")
        if len(sources_list) > 30:
            lines.append(f"  … and {len(sources_list) - 30} more.")
        return "\n".join(lines)

    async def run(self) -> str:
        """Return formatted headlines or list of sources. Core may post_process (LLM) or send directly."""
        try:
            req = getattr(self, "promptRequest", None)
            meta = (getattr(req, "request_metadata", None) or {}) if req else {}
            cap_id = (meta.get("capability_id") or "fetch_headlines").strip().lower().replace(" ", "_")
            if cap_id == "list_sources":
                return await self.list_sources()
            return await self.fetch_headlines()
        except Exception as e:
            logger.exception("Headlines run: {}", e)
            return f"Error: {e!s}"
