"""
Tests for magazine-render static chrome templates + RSS-shaped mock data.

Upstream VMPrint scripting fixtures (YAML + JSON) live under tools/vmprint when installed;
see skills/magazine-render-1.0.0/ast_templates/README.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_MR_SCR = _ROOT / "skills" / "magazine-render-1.0.0" / "scripts"
if str(_MR_SCR) not in sys.path:
    sys.path.insert(0, str(_MR_SCR))

from ast_template_merge import (  # noqa: E402
    MOCK_DAILY_BRIEF_RSS,
    load_chrome_template,
    merge_chrome_template_into_ast,
)
from render_magazine import (  # noqa: E402
    _daily_brief_magazine_ast,
    _validate_ast_1_1,
)

_CHROME = _ROOT / "skills" / "magazine-render-1.0.0" / "ast_templates" / "daily_brief_magazine_chrome_v1.json"


def test_chrome_template_file_exists():
    assert _CHROME.is_file(), f"Expected {_CHROME} (regenerate per ast_templates/README.md)"


def test_load_chrome_template_meta():
    doc = load_chrome_template(_CHROME)
    assert doc["meta"]["homeclaw_template"]["merge_mode"] == "chrome_only"
    assert "layout" in doc and "styles" in doc


def test_merge_mock_rss_then_validate_ast():
    base = _daily_brief_magazine_ast(MOCK_DAILY_BRIEF_RSS, title="TEST BRIEF", theme="dispatch")
    chrome = load_chrome_template(_CHROME)
    merged = merge_chrome_template_into_ast(base, chrome)
    assert merged["documentVersion"] == "1.1"
    assert merged["elements"] == base["elements"]
    assert merged["layout"] == chrome["layout"]
    _validate_ast_1_1(merged)


def test_merge_preserves_story_when_chrome_changes_typography():
    base = _daily_brief_magazine_ast(MOCK_DAILY_BRIEF_RSS, title="TEST BRIEF", theme="dispatch")
    chrome = load_chrome_template(_CHROME)
    merged = merge_chrome_template_into_ast(base, chrome)
    zone = next((e for e in merged["elements"] if e.get("type") == "zone-map"), None)
    assert zone is not None
    zones = zone.get("zones") or []
    lead = next((z for z in zones if z.get("id") == "lead"), None)
    assert lead is not None
    assert any("Regional talks" in str(x.get("content", "")) for x in (lead.get("elements") or []) if isinstance(x, dict))
