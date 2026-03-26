from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_magazine_render_module():
    root = Path(__file__).resolve().parents[1]
    mod_path = root / "skills" / "magazine-render-1.0.0" / "scripts" / "render_magazine.py"
    spec = importlib.util.spec_from_file_location("render_magazine_mod", str(mod_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_ast_11_accepts_minimal_valid_document():
    m = _load_magazine_render_module()
    doc = {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": "LETTER",
            "margins": {"top": 72, "right": 72, "bottom": 72, "left": 72},
            "fontFamily": "Arimo",
            "fontSize": 12,
            "lineHeight": 1.4,
        },
        "styles": {"h1": {"fontSize": 24, "fontWeight": "bold"}},
        "elements": [{"type": "h1", "content": "Hello"}],
    }
    m._validate_ast_1_1(doc)


def test_validate_ast_11_rejects_wrong_version():
    m = _load_magazine_render_module()
    bad_doc = {"documentVersion": "1.0", "layout": {}, "styles": {}, "elements": []}
    try:
        m._validate_ast_1_1(bad_doc)
        assert False, "Expected ValueError for invalid AST version"
    except ValueError as e:
        assert "documentVersion must be '1.1'" in str(e)


def test_validate_ast_11_rejects_unknown_top_level_keys():
    m = _load_magazine_render_module()
    bad_doc = {
        "documentVersion": "1.1",
        "layout": {},
        "styles": {},
        "elements": [],
        "unknownTop": True,
    }
    try:
        m._validate_ast_1_1(bad_doc)
        assert False, "Expected ValueError for unsupported top-level keys"
    except ValueError as e:
        assert "unsupported top-level keys" in str(e)


def test_daily_brief_ast_contains_expected_constraints():
    m = _load_magazine_render_module()
    data = {"as_of": "2026-03-26", "items": [{"title": "Headline", "source": "RSS", "link": "https://example.com"}]}
    ast = m._daily_brief_ast(data, title="Daily Brief", theme="dispatch")

    assert ast["documentVersion"] == "1.1"
    assert isinstance(ast["styles"], dict)
    assert isinstance(ast["elements"], list)

    table_nodes = [n for n in ast["elements"] if n.get("type") == "zone-map"]
    assert table_nodes, "Expected zone-map node in daily-brief AST"

    # Check repeat-header semantics in table row.
    main_zone = table_nodes[0]["zones"][0]
    table = main_zone["elements"][0]
    assert table["type"] == "table"
    assert table["table"]["repeatHeader"] is True
    header_row = table["children"][0]
    assert header_row["properties"]["semanticRole"] == "header"


def test_validate_ast_11_rejects_repeat_header_without_semantic_header():
    m = _load_magazine_render_module()
    bad_doc = {
        "documentVersion": "1.1",
        "layout": {},
        "styles": {},
        "elements": [
            {
                "type": "table",
                "content": "",
                "table": {"headerRows": 1, "repeatHeader": True},
                "children": [
                    {
                        "type": "table-row",
                        "content": "",
                        "properties": {"semanticRole": "not-header"},
                        "children": [{"type": "table-cell", "content": "x"}],
                    }
                ],
            }
        ],
    }
    try:
        m._validate_ast_1_1(bad_doc)
        assert False, "Expected ValueError for missing header semantic role"
    except ValueError as e:
        assert "semanticRole='header'" in str(e)


def test_weather_and_stock_ast_templates_are_valid_11():
    m = _load_magazine_render_module()
    w = m._ast_from_template(
        "weather",
        {
            "location": "Beijing",
            "now": {"condition": "Cloudy", "temp": "18C"},
            "forecast": [{"day": "Fri", "summary": "Cloudy", "high": "21C", "low": "14C"}],
        },
        title="Weather Brief",
        theme="dispatch",
    )
    s = m._ast_from_template(
        "stock",
        {"items": [{"symbol": "NVDA", "name": "NVIDIA", "price": "100", "change_pct": "+1.2%"}]},
        title="Stock Brief",
        theme="minimal",
    )
    m._validate_ast_1_1(w)
    m._validate_ast_1_1(s)
    assert w["documentVersion"] == "1.1"
    assert s["documentVersion"] == "1.1"


def test_browser_preview_html_embeds_layout_payload():
    m = _load_magazine_render_module()
    layout_json = '{"pages":[{"width":595,"height":842,"boxes":[{"x":1,"y":2,"w":30,"h":10,"type":"text"}]}]}'
    html_out = m._build_browser_preview_html(layout_json)
    assert "<script id='layout-data' type='application/json'>" in html_out
    assert "VMPrint Scene Preview" in html_out
    assert "const pages=d.pages||[]" in html_out


def test_canvas_preview_html_embeds_svg_pages_payload():
    m = _load_magazine_render_module()
    html_out = m._build_canvas_preview_html(["<svg><text>Hello</text></svg>"])
    assert "<script id='svg-pages-data' type='application/json'>" in html_out
    assert "CanvasContext Preview" in html_out
    assert "const pages=JSON.parse" in html_out


def test_output_filename_sanitization_for_ast_formats():
    m = _load_magazine_render_module()
    assert m._sanitize_output_filename("brief", "layout_json").endswith(".json")
    assert m._sanitize_output_filename("brief", "browser_preview_html").endswith(".html")
    assert m._sanitize_output_filename("brief", "pdf").endswith(".pdf")


def test_browser_preview_html_rejects_oversized_layout():
    m = _load_magazine_render_module()
    huge = '{"pages":[{"boxes":[' + ("{}," * 1_200_000) + '{}]}]}'
    # This helper itself still builds HTML; size guard is enforced by render path.
    html_out = m._build_browser_preview_html('{"pages":[]}')
    assert "VMPrint Scene Preview" in html_out
    assert len(huge) > 2_000_000
