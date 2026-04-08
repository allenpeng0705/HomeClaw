from __future__ import annotations

from pathlib import Path
from typing import List


def _load_normalizer():
    root = Path(__file__).resolve().parents[1]
    src = (root / "tools" / "builtin.py").read_text(encoding="utf-8")
    start = src.index("def _normalize_daily_brief_args(")
    end = src.index("\n\nasync def _run_skill_executor", start)
    fn_src = src[start:end]
    ns = {"List": List}
    exec(fn_src, ns)
    return ns["_normalize_daily_brief_args"]


def _load_deriver():
    root = Path(__file__).resolve().parents[1]
    src = (root / "tools" / "builtin.py").read_text(encoding="utf-8")
    start = src.index("def _daily_brief_document_layout_from_user_query(")
    start_drv = src.index("def _derive_daily_brief_args_from_query(")
    end_drv = src.index("\n\nasync def _run_skill_executor", start_drv)
    fn_src = src[start:end_drv]
    ns = {"List": List, "Optional": __import__("typing").Optional, "re": __import__("re")}
    exec(fn_src, ns)
    return ns["_derive_daily_brief_args_from_query"]


def _load_merge_and_layout():
    root = Path(__file__).resolve().parents[1]
    src = (root / "tools" / "builtin.py").read_text(encoding="utf-8")
    start = src.index("def _daily_brief_document_layout_from_user_query(")
    end = src.index("def _derive_daily_brief_args_from_query(", start)
    fn_src = src[start:end]
    ns = {"List": List, "Optional": __import__("typing").Optional}
    exec(fn_src, ns)
    return ns["_merge_fetch_vmprint_document_layout"], ns["_normalize_daily_brief_args"], ns["_daily_brief_document_layout_from_user_query"]


def test_daily_brief_normalizer_list_drops_noise():
    fn = _load_normalizer()
    out = fn(["list", "--max", "999", "--lang", "cn"])
    assert out == ["list"]


def test_daily_brief_normalizer_fetch_vmprint_defaults_and_clamps():
    fn = _load_normalizer()
    out = fn(["fetch-vmprint", "--max", "500", "--lang", "jp", "--theme", "x", "--output_format", "txt"])
    assert out == [
        "fetch-vmprint",
        "--max",
        "100",
        "--lang",
        "all",
        "--theme",
        "dispatch",
        "--output_format",
        "browser_preview_html",
        "--document-layout",
        "digest_table",
    ]


def test_daily_brief_normalizer_supports_equals_style_flags():
    fn = _load_normalizer()
    out = fn(["fetch-vmprint", "--max=12", "--lang=cn", "--filter=AI", "--theme=minimal", "--output_format=pdf"])
    assert out == [
        "fetch-vmprint",
        "--max",
        "12",
        "--lang",
        "cn",
        "--filter",
        "AI",
        "--theme",
        "minimal",
        "--output_format",
        "pdf",
        "--document-layout",
        "digest_table",
    ]


def test_daily_brief_normalizer_markdown_fetch_keeps_no_vmprint_flags():
    fn = _load_normalizer()
    out = fn(["fetch", "--lang", "en", "--max", "20", "--theme", "minimal"])
    assert out == ["fetch", "--max", "20", "--lang", "en"]


def test_daily_brief_query_deriver_defaults_to_vmprint():
    fn = _load_deriver()
    out = fn("今日新闻（20条，中文）", False)
    assert out == [
        "fetch-vmprint",
        "--max",
        "20",
        "--lang",
        "cn",
        "--theme",
        "dispatch",
        "--output_format",
        "browser_preview_html",
        "--document-layout",
        "digest_table",
    ]


def test_daily_brief_query_deriver_杂志排版_selects_magazine_layout():
    fn = _load_deriver()
    out = fn("今日新闻 20条 中文 杂志排版", False)
    assert "--document-layout" in out
    assert out[out.index("--document-layout") + 1] == "magazine"


def test_daily_brief_query_deriver_杂志格式_selects_magazine():
    fn = _load_deriver()
    out = fn("今日新闻 （中文，10条）杂志格式", False)
    assert out[out.index("--document-layout") + 1] == "magazine"


def test_merge_fetch_vmprint_layout_overrides_digest_table():
    merge, norm, layout_fn = _load_merge_and_layout()
    assert layout_fn("今日新闻 杂志格式") == "magazine"
    base = norm(["fetch-vmprint", "--max", "10", "--lang", "cn"])
    assert base[base.index("--document-layout") + 1] == "digest_table"
    merged = merge(base, "magazine")
    assert merged[merged.index("--document-layout") + 1] == "magazine"


def test_daily_brief_query_deriver_newspaper_layout_keyword():
    fn = _load_deriver()
    out = fn("今日新闻 20条 中文 头版", False)
    assert out[out.index("--document-layout") + 1] == "newspaper"


def test_daily_brief_normalizer_accepts_newspaper_layout():
    fn = _load_normalizer()
    out = fn(["fetch-vmprint", "--max", "10", "--lang", "cn", "--document-layout", "newspaper"])
    assert out[out.index("--document-layout") + 1] == "newspaper"


def test_daily_brief_query_deriver_markdown_override():
    fn = _load_deriver()
    out = fn("今日新闻 15条 中文，纯Markdown输出", True)
    assert out == ["fetch", "--max", "15", "--lang", "cn"]
