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
    start_norm = src.index("def _normalize_daily_brief_args(")
    start_drv = src.index("def _derive_daily_brief_args_from_query(")
    end_drv = src.index("\n\nasync def _run_skill_executor", start_drv)
    fn_src = src[start_norm:end_drv]
    ns = {"List": List, "re": __import__("re")}
    exec(fn_src, ns)
    return ns["_derive_daily_brief_args_from_query"]


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
    ]


def test_daily_brief_query_deriver_markdown_override():
    fn = _load_deriver()
    out = fn("今日新闻 15条 中文，纯Markdown输出", True)
    assert out == ["fetch", "--max", "15", "--lang", "cn"]
