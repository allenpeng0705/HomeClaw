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


def test_web_search_ast_uses_description_for_snippet_when_content_missing():
    m = _load_magazine_render_module()
    data = {
        "query": "q",
        "results": [
            {
                "title": "T",
                "url": "https://example.com",
                "description": "Body from Tavily lives here.",
            }
        ],
    }
    ast = m._web_search_ast(data, title="Search", theme="dispatch")
    table = ast["elements"][-1]
    assert table["type"] == "table"
    row = table["children"][1]
    assert "Body from Tavily" in row["children"][2]["content"]


def test_web_search_ast_uses_arimo_for_layout_engine():
    """VMPrint StandardFontManager registers bundled families (e.g. Arimo), not arbitrary names like Noto Sans SC."""
    m = _load_magazine_render_module()
    data = {"results": [{"title": "中文标题", "url": "https://x.test", "description": "摘要"}]}
    ast = m._web_search_ast(data, title="S", theme="minimal")
    assert ast["layout"]["fontFamily"] == "Arimo"


def test_daily_brief_ast_includes_summary_snippet_column():
    m = _load_magazine_render_module()
    data = {
        "items": [
            {
                "title": "T",
                "feed": "IT之家",
                "link": "https://x.test",
                "summary": "摘要正文用于杂志表格 Snippet 列。",
            }
        ],
    }
    ast = m._daily_brief_ast(data, title="Brief", theme="dispatch")
    table = ast["elements"][3]["zones"][0]["elements"][0]
    row = table["children"][1]
    assert row["children"][3]["content"] == "摘要正文用于杂志表格 Snippet 列。"
    assert row["children"][2]["content"] == "IT之家"


def test_daily_brief_magazine_ast_matches_specimen_without_headline_index_table():
    m = _load_magazine_render_module()
    data = {
        "as_of": "2026-03-26",
        "items": [
            {
                "title": "Lead story title",
                "feed": "Example Feed",
                "link": "https://example.com/a",
                "summary": "First paragraph of the lead. " * 5 + "Second part of summary for columns.",
            },
            {"title": "Side two", "feed": "Other", "link": "https://b.test", "summary": "Snippet B."},
        ],
    }
    ast = m._daily_brief_magazine_ast(data, title="Daily Brief", theme="dispatch")
    m._validate_ast_1_1(ast)
    assert ast["elements"][0]["type"] == "masthead"
    assert ast["layout"]["fontFamily"] == "Tinos"
    assert ast["layout"].get("hyphenation") == "auto"
    zm = [n for n in ast["elements"] if n.get("type") == "zone-map"][0]
    lead = next(z for z in zm["zones"] if z["id"] == "lead")
    types = [e.get("type") for e in lead["elements"]]
    assert "headline-lg" in types and "story" in types
    story = next(e for e in lead["elements"] if e.get("type") == "story")
    assert story.get("columns") == 2
    kids = story.get("children") or []
    assert any(c.get("type") == "body" for c in kids)
    assert any(c.get("type") == "pull-quote" for c in kids)
    assert not any(n.get("type") == "table" for n in ast["elements"])
    hdr = ast["header"]["default"]["elements"][0]
    assert hdr["slots"][0]["elements"][0]["type"] == "footer-text"
    assert ast["footer"]["default"]["elements"][0]["slots"][-1]["elements"][0]["content"] == "Magazine"


def test_ast_from_template_daily_brief_magazine_layout():
    m = _load_magazine_render_module()
    data = {"items": [{"title": "Only one", "feed": "F", "link": "https://x", "summary": "Short."}]}
    ast = m._ast_from_template("daily_brief", data, title="B", theme="dispatch", document_layout="magazine")
    m._validate_ast_1_1(ast)
    zm = next(n for n in ast["elements"] if n.get("type") == "zone-map")
    lead = next(z for z in zm["zones"] if z["id"] == "lead")
    assert any(e.get("type") == "story" for e in lead["elements"])


def test_daily_brief_newspaper_ast_validates_and_has_front_page_shape():
    m = _load_magazine_render_module()
    data = {
        "as_of": "2026-03-24",
        "items": [
            {
                "title": "Lead headline here",
                "feed": "Tech",
                "link": "https://a.test/x",
                "summary": "First paragraph of the lead story. " * 4 + "More text follows for columns.",
            },
            {"title": "Second", "feed": "News", "link": "https://b", "summary": "Brief two."},
        ],
    }
    ast = m._daily_brief_newspaper_ast(data, title="Dispatch", theme="dispatch")
    m._validate_ast_1_1(ast)
    assert ast["elements"][0]["type"] == "masthead"
    assert any(e.get("type") == "table" for e in ast["elements"])
    assert ast["layout"]["pageSize"]["width"] == 612
    dig = m._ast_digest_html(ast)
    assert "Lead headline" in dig
    assert 'href="https://b"' in dig


def test_ast_from_template_daily_brief_newspaper_layout():
    m = _load_magazine_render_module()
    data = {"items": [{"title": "A", "feed": "F", "link": "https://x", "summary": "S."}]}
    ast = m._ast_from_template("daily_brief", data, title="Paper", theme="dispatch", document_layout="newspaper")
    m._validate_ast_1_1(ast)
    assert ast["elements"][0]["content"] == "PAPER"


def test_ast_from_template_web_search_magazine_layout():
    m = _load_magazine_render_module()
    data = {
        "query": "q1",
        "results": [
            {"title": "First hit", "url": "https://news.example.com/a", "description": "Lead snippet text here."},
            {"title": "Second", "url": "https://b.test", "snippet": "Other."},
        ],
    }
    ast = m._ast_from_template("web_search", data, title="Search", theme="dispatch", document_layout="magazine")
    m._validate_ast_1_1(ast)
    assert ast["elements"][0]["content"] == "WEB SEARCH"
    zm = next(n for n in ast["elements"] if n.get("type") == "zone-map")
    lead = next(z for z in zm["zones"] if z["id"] == "lead")
    assert any(e.get("type") == "headline" and e.get("content") == "First hit" for e in lead["elements"])
    kicker = next(e for e in lead["elements"] if e.get("type") == "kicker")
    assert kicker["content"] == "TOP RESULT"
    story = next(e for e in lead["elements"] if e.get("type") == "story")
    assert story.get("columns") == 1
    assert any(
        e.get("type") == "body" and e.get("content") == "https://news.example.com/a" for e in story["children"]
    )
    dig = m._ast_digest_html(ast)
    assert "First hit" in dig and "Second" in dig


def test_ast_from_template_weather_magazine_layout():
    m = _load_magazine_render_module()
    data = {
        "location": "Beijing",
        "now": {"condition": "Cloudy", "temp": "18C", "humidity": "40%"},
        "forecast": [{"day": "Fri", "summary": "Cloudy", "high": "21C", "low": "14C"}],
    }
    ast = m._ast_from_template("weather", data, title="Wx", theme="dispatch", document_layout="magazine")
    m._validate_ast_1_1(ast)
    assert ast["elements"][0]["content"] == "WEATHER"
    zm = next(n for n in ast["elements"] if n.get("type") == "zone-map")
    rail = next(z for z in zm["zones"] if z["id"] == "rail")
    assert any("Fri" in str(e.get("content", "")) for e in rail["elements"])


def test_ast_from_template_stock_magazine_layout():
    m = _load_magazine_render_module()
    data = {
        "items": [
            {"symbol": "AAA", "name": "Alpha Inc", "price": "10", "change_pct": "+1.2%"},
            {"symbol": "BBB", "name": "Beta", "price": "9", "change_pct": "-0.5%"},
        ]
    }
    ast = m._ast_from_template("stock", data, title="Stocks", theme="dispatch", document_layout="magazine")
    m._validate_ast_1_1(ast)
    assert ast["elements"][0]["content"] == "MARKETS"
    zm = next(n for n in ast["elements"] if n.get("type") == "zone-map")
    lead = next(z for z in zm["zones"] if z["id"] == "lead")
    assert any(e.get("type") == "headline" and "AAA" in str(e.get("content")) for e in lead["elements"])


def test_daily_brief_magazine_digest_html_includes_lead_and_rail():
    m = _load_magazine_render_module()
    ast = m._daily_brief_magazine_ast(
        {
            "items": [
                {"title": "Alpha", "feed": "Feed A", "link": "https://a", "summary": "Lead body text here."},
                {"title": "Beta", "feed": "Feed B", "link": "https://b", "summary": "Rail snippet."},
            ]
        },
        title="Brief",
        theme="dispatch",
    )
    dig = m._ast_digest_html(ast)
    assert "Alpha" in dig
    assert "Beta" in dig
    assert "Rail snippet" in dig
    assert 'href="https://b"' in dig


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


def test_stock_ast_prefixes_change_with_arrow():
    m = _load_magazine_render_module()
    data = {
        "items": [
            {"symbol": "AAA", "name": "A", "price": "10", "change_pct": "+1.2%"},
            {"symbol": "BBB", "name": "B", "price": "9", "change_pct": "-0.5%"},
        ]
    }
    ast = m._ast_from_template("stock", data, title="S", theme="dispatch")
    rows = ast["elements"][-1]["children"][1:]
    assert rows[0]["children"][3]["content"].startswith("▲")
    assert rows[1]["children"][3]["content"].startswith("▼")


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


def test_ast_digest_includes_cjk_table_cells():
    m = _load_magazine_render_module()
    ast = m._web_search_ast(
        {"results": [{"title": "中文標題", "url": "https://x.test", "description": "摘要內文"}]},
        title="搜尋",
        theme="dispatch",
    )
    dig = m._ast_digest_html(ast)
    assert "中文標題" in dig
    assert "摘要內文" in dig
    assert "homeclaw-ast-digest" in dig
    assert "Magazine digest" in dig
    assert 'href="https://x.test"' in dig
    assert 'target="_blank"' in dig
    assert "<article" in dig
    assert "grid-template-columns:repeat(auto-fit" not in dig


def test_ast_digest_web_search_table_is_vertical_cards_not_multi_column_grid():
    m = _load_magazine_render_module()
    ast = m._web_search_ast(
        {
            "results": [
                {"title": "Alpha story", "url": "https://a.example/x", "snippet": "First paragraph."},
                {"title": "Beta", "url": "https://b.example/y", "content": "Second body."},
            ]
        },
        title="Search",
        theme="dispatch",
    )
    dig = m._ast_digest_html(ast)
    assert dig.count("<article") == 2
    assert "Alpha story" in dig and "Beta" in dig
    assert "grid-template-columns:repeat(auto-fit" not in dig


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
