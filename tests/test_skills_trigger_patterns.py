"""Unit tests for skills_with_matching_trigger_patterns and lexical overlap (semantic router)."""

from types import SimpleNamespace

from base.skill_router import skills_semantic_embed_body_max_chars, skills_semantic_rerank_body_max_chars
from base.skills import (
    skills_with_lexical_overlap,
    skills_with_matching_trigger_patterns,
)


def test_skills_with_matching_trigger_patterns_empty_query():
    skills = [{"folder": "a", "trigger": {"patterns": [r"foo"]}}]
    assert skills_with_matching_trigger_patterns(skills, "") == []
    assert skills_with_matching_trigger_patterns(skills, "   ") == []


def test_skills_with_matching_trigger_patterns_omits_no_trigger_or_no_patterns():
    skills = [
        {"folder": "no_trigger", "name": "x"},
        {"folder": "empty_patterns", "trigger": {"patterns": []}},
        {"folder": "no_patterns_key", "trigger": {}},
    ]
    assert skills_with_matching_trigger_patterns(skills, "anything") == []


def test_skills_with_matching_trigger_patterns_matches_regex():
    skills = [
        {"folder": "email", "trigger": {"patterns": [r"@\w+\.\w+", r"\bemail\b"]}},
        {"folder": "other", "trigger": {"patterns": [r"^onlystart"]}},
    ]
    out = skills_with_matching_trigger_patterns(skills, "Contact me at a@b.co please")
    folders = {s["folder"] for s in out}
    assert folders == {"email"}

    out2 = skills_with_matching_trigger_patterns(skills, "onlystart here")
    assert {s["folder"] for s in out2} == {"other"}


def test_skills_with_matching_trigger_patterns_single_pattern_alias():
    skills = [{"folder": "p", "trigger": {"pattern": r"bar"}}]
    assert skills_with_matching_trigger_patterns(skills, "foo bar baz") == skills


def test_skills_with_lexical_overlap_matches_name():
    skills = [
        {"folder": "a", "name": "PDF Export", "description": "Make files", "keywords": []},
        {"folder": "b", "name": "Other", "description": "Nothing", "keywords": []},
    ]
    out = skills_with_lexical_overlap(skills, "how do I use pdf export")
    assert len(out) == 1 and out[0]["folder"] == "a"


def test_skills_semantic_embed_and_rerank_body_caps():
    meta = SimpleNamespace(
        skills_router_config={
            "semantic": {"embed_body_max_chars": 2400, "rerank_include_body_max_chars": 1800},
        }
    )
    assert skills_semantic_embed_body_max_chars(meta) == 2400
    assert skills_semantic_rerank_body_max_chars(meta, {}) == 1800
    assert skills_semantic_rerank_body_max_chars(SimpleNamespace(skills_router_config={}), {"include_body_max_chars": 500}) == 500


def test_skills_with_lexical_overlap_subword_no_false_positive():
    """'cat' should not match inside 'category'."""
    skills = [
        {"folder": "x", "name": "Category", "description": "", "keywords": []},
        {"folder": "y", "name": "Cat Tool", "description": "", "keywords": []},
    ]
    out = skills_with_lexical_overlap(skills, "cat help", min_token_len=3)
    folders = {s["folder"] for s in out}
    assert "y" in folders and "x" not in folders
