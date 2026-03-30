"""Unit tests for daily-brief RSS excerpt helper (content fallback)."""

import importlib.util
from pathlib import Path


def _load_fetch_rss():
    root = Path(__file__).resolve().parent.parent
    path = root / "skills/daily-brief-1.0.0/scripts/fetch_rss.py"
    spec = importlib.util.spec_from_file_location("fetch_rss_mod", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_entry_summary_prefers_summary_over_content():
    m = _load_fetch_rss()

    class E:
        summary = "<p>Short blurb</p>"
        description = ""
        content = [{"value": "<p>Long body ignored when summary set.</p>", "type": "text/html"}]

    assert m._entry_summary_excerpt(E(), 500) == "Short blurb"


def test_fetch_vmprint_items_out_includes_summary_key():
    """Regression: render-daily-brief-ast Snippet column needs summary on each item."""
    root = Path(__file__).resolve().parent.parent / "skills/daily-brief-1.0.0/scripts/fetch_rss.py"
    text = root.read_text(encoding="utf-8")
    start = text.find("items_out = [")
    assert start >= 0
    block = text[start : start + 700]
    assert '"summary"' in block


def test_entry_summary_falls_back_to_content_encoded():
    m = _load_fetch_rss()

    class E:
        summary = ""
        description = ""
        content = [{"value": "<p>First paragraph of article.</p>", "type": "text/html"}]

    out = m._entry_summary_excerpt(E(), 500)
    assert "First paragraph" in out
    assert "<" not in out
