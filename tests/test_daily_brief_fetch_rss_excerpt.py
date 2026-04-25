"""Unit tests for daily-brief RSS excerpt helper (content fallback)."""

import sys
from pathlib import Path

# Add skill scripts directory to path so we can import the module directly.
_root = Path(__file__).resolve().parent.parent
_fetch_rss_path = _root / "skills/daily-brief-1.0.0/scripts"
sys.path.insert(0, str(_fetch_rss_path))
from fetch_rss import _entry_summary_excerpt


class _Entry:
    """Minimal mock entry object for testing _entry_summary_excerpt."""
    def __init__(self, summary="", description="", content=None):
        self.summary = summary
        self.description = description
        self.content = content or []


def test_entry_summary_prefers_summary_over_content():
    entry = _Entry(
        summary="<p>Short blurb</p>",
        description="",
        content=[{"value": "<p>Long body ignored when summary set.</p>", "type": "text/html"}],
    )
    assert _entry_summary_excerpt(entry, 500) == "Short blurb"


def test_fetch_vmprint_items_out_includes_summary_key():
    """Regression: render-daily-brief-ast Snippet column needs summary on each item."""
    text = (_fetch_rss_path / "fetch_rss.py").read_text(encoding="utf-8")
    start = text.find("items_out = [")
    assert start >= 0
    block = text[start : start + 700]
    assert '"summary"' in block


def test_entry_summary_falls_back_to_content_encoded():
    entry = _Entry(
        summary="",
        description="",
        content=[{"value": "<p>First paragraph of article.</p>", "type": "text/html"}],
    )
    out = _entry_summary_excerpt(entry, 500)
    assert "First paragraph" in out
    assert "<" not in out
