"""
Static AST chrome templates for magazine-render (News / RSS daily-brief).

HomeClaw builds story content from RSS/Tavily-shaped JSON using the same Python
builders as always. Optional JSON files under ast_templates/ supply **chrome only**:
layout, styles, header, and footer — merged onto the dynamic AST so typography
and page frame stay editable without forking render_magazine.py.

Merge mode `chrome_only` (v1): replace top-level layout/styles/header/footer from
the template; keep `elements` from the runtime builder (stable data pipeline).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict

# Mock RSS/daily-brief payload for tests and docs (Tavily/RSS normalized shape).
MOCK_DAILY_BRIEF_RSS: Dict[str, Any] = {
    "as_of": "2026-04-15T10:00:00",
    "items": [
        {
            "title": "Regional talks enter third day amid shipping concerns",
            "feed": "world.news",
            "summary": "Delegates continued negotiations as observers noted tighter controls on key straits. Markets opened steady.",
            "link": "https://example.com/article/1",
        },
        {
            "title": "Tech sector outlines voluntary safety framework",
            "feed": "tech.feed",
            "summary": "Industry groups published a draft checklist for large model deployments.",
            "link": "https://example.com/article/2",
        },
        {
            "title": "Local weather: mild week ahead",
            "feed": "weather.local",
            "summary": "Forecasters expect seasonal temperatures with light rain midweek.",
            "link": "https://example.com/article/3",
        },
    ],
}


def load_chrome_template(path: Path) -> Dict[str, Any]:
    """
    Load a chrome-only AST fragment (layout, styles, header, footer).
    Validates meta.homeclaw_template for supported merge modes.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Chrome template not found: {p}")
    raw = p.read_text(encoding="utf-8", errors="replace")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        raise ValueError("Chrome template root must be a JSON object.")
    meta = doc.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Chrome template must include meta object.")
    ht = meta.get("homeclaw_template")
    if not isinstance(ht, dict):
        raise ValueError("Chrome template meta.homeclaw_template must be an object.")
    kind = str(ht.get("kind") or "").strip()
    mode = str(ht.get("merge_mode") or "").strip()
    if kind != "daily_brief_magazine_chrome":
        raise ValueError(
            f"Unsupported chrome template kind: {kind!r} (expected daily_brief_magazine_chrome)."
        )
    if mode != "chrome_only":
        raise ValueError(
            f"Unsupported merge_mode: {mode!r} (v1 supports chrome_only only)."
        )
    for key in ("layout", "styles", "header", "footer"):
        if key not in doc or not isinstance(doc[key], dict):
            raise ValueError(f"Chrome template must include a {key!r} object.")
    return doc


def merge_chrome_template_into_ast(dynamic_ast: Dict[str, Any], chrome: Dict[str, Any]) -> Dict[str, Any]:
    """
    Overlay layout / styles / header / footer from chrome onto a full dynamic AST.
    Story `elements` and documentVersion come from dynamic_ast.
    """
    if not isinstance(dynamic_ast, dict) or not isinstance(chrome, dict):
        raise ValueError("merge_chrome_template_into_ast expects two dicts.")
    out = copy.deepcopy(dynamic_ast)
    for k in ("layout", "styles", "header", "footer"):
        if k in chrome and isinstance(chrome[k], dict):
            out[k] = copy.deepcopy(chrome[k])
    return out


def build_magazine_ast_with_optional_chrome(
    *,
    build_ast: Any,
    data: Dict[str, Any],
    title: str,
    theme: str,
    chrome_template_path: str | None,
) -> Dict[str, Any]:
    """
    build_ast: callable (data, title, theme) -> dict, e.g. _daily_brief_magazine_ast
    """
    ast_doc = build_ast(data, title=title, theme=theme)
    path = (chrome_template_path or "").strip()
    if not path:
        return ast_doc
    chrome = load_chrome_template(Path(path))
    return merge_chrome_template_into_ast(ast_doc, chrome)
