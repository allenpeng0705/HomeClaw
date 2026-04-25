"""Intent category docs drive categories, classifier blurbs, and category_tools from markdown."""

from pathlib import Path

from base.intent_category_router import (
    clear_intent_category_manifest_cache,
    load_intent_category_manifest,
    merge_intent_router_config_with_docs,
)
from base.intent_router import DEFAULT_CATEGORY_DESCRIPTIONS

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_load_manifest_includes_standard_categories():
    clear_intent_category_manifest_cache()
    man = load_intent_category_manifest(_REPO_ROOT / "config" / "intent_category")
    cats = man.get("categories") or []
    assert "search_web" in cats
    assert "weather" in cats
    assert "greeting" in cats
    assert "identity_capabilities" in cats
    assert "general_chat" in cats
    assert man.get("category_descriptions", {}).get("weather")
    assert man.get("category_tools_map", {}).get("weather", {}).get("skills")


def test_merge_fills_categories_and_descriptions():
    clear_intent_category_manifest_cache()
    cfg = {
        "intent_category_docs_dir": "config/intent_category",
    }
    merged = merge_intent_router_config_with_docs(
        cfg,
        root_path=_REPO_ROOT,
        default_descriptions=DEFAULT_CATEGORY_DESCRIPTIONS,
    )
    assert isinstance(merged.get("categories"), list)
    # Intent categories include at least these standard groups:
    # search_web, weather, greeting, identity_capabilities, general_chat, news, etc.
    # Update this constant if categories are added or reorganized.
    _MIN_EXPECTED_CATEGORIES = 10
    assert len(merged["categories"]) >= _MIN_EXPECTED_CATEGORIES
    assert merged["category_descriptions"].get("greeting")
    assert isinstance(merged.get("_doc_pattern_entries"), list)
    assert merged.get("category_tools", {}).get("weather", {}).get("skills")
