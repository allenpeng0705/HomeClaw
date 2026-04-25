"""Unit tests for daily-brief argument normalization and derivation (from tools.builtin)."""

import pytest

from tools.builtin import (
    _normalize_daily_brief_args,
    _derive_daily_brief_args_from_query,
    _daily_brief_document_layout_from_user_query,
    _merge_fetch_vmprint_document_layout,
    _get_tools_config,
)


def _set_tools_config(cfg):
    """Temporarily override _get_tools_config for tests that need specific config."""
    import tools.builtin as bi
    original = bi._get_tools_config
    bi._get_tools_config = lambda: cfg
    try:
        yield
    finally:
        bi._get_tools_config = original


def test_daily_brief_normalizer_list_drops_noise():
    out = _normalize_daily_brief_args(["list", "--max", "999", "--lang", "cn"])
    assert out == ["list"]


def test_daily_brief_normalizer_fetch_vmprint_defaults_and_clamps():
    out = _normalize_daily_brief_args(["fetch-vmprint", "--max", "500", "--lang", "jp", "--theme", "x", "--output_format", "txt"])
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
    out = _normalize_daily_brief_args(["fetch-vmprint", "--max=12", "--lang=cn", "--filter=AI", "--theme=minimal", "--output_format=pdf"])
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
    out = _normalize_daily_brief_args(["fetch", "--lang", "en", "--max", "20", "--theme", "minimal"])
    assert out == ["fetch", "--max", "20", "--lang", "en"]


def test_daily_brief_query_deriver_defaults_to_markdown_fetch():
    out = _derive_daily_brief_args_from_query("今日新闻（20条，中文）")
    assert out == ["fetch", "--max", "20", "--lang", "cn"]


def test_daily_brief_query_deriver_vmprint_when_config():
    import tools.builtin as bi
    original = bi._get_tools_config
    bi._get_tools_config = lambda: {"long_document_output": "vmprint"}
    try:
        out = _derive_daily_brief_args_from_query("今日新闻（20条，中文）")
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
    finally:
        bi._get_tools_config = original


def test_daily_brief_query_deriver_杂志排版_selects_magazine_layout():
    out = _derive_daily_brief_args_from_query("今日新闻 20条 中文 杂志排版")
    assert "--document-layout" in out
    assert out[out.index("--document-layout") + 1] == "magazine"


def test_daily_brief_query_deriver_杂志格式_selects_magazine():
    out = _derive_daily_brief_args_from_query("今日新闻 （中文，10条）杂志格式")
    assert out[out.index("--document-layout") + 1] == "magazine"


def test_merge_fetch_vmprint_layout_overrides_digest_table():
    assert _daily_brief_document_layout_from_user_query("今日新闻 杂志格式") == "magazine"
    base = _normalize_daily_brief_args(["fetch-vmprint", "--max", "10", "--lang", "cn"])
    assert base[base.index("--document-layout") + 1] == "digest_table"
    merged = _merge_fetch_vmprint_document_layout(base, "magazine")
    assert merged[merged.index("--document-layout") + 1] == "magazine"


def test_daily_brief_query_deriver_newspaper_layout_keyword():
    out = _derive_daily_brief_args_from_query("今日新闻 20条 中文 头版")
    assert out[out.index("--document-layout") + 1] == "newspaper"


def test_daily_brief_normalizer_accepts_newspaper_layout():
    out = _normalize_daily_brief_args(["fetch-vmprint", "--max", "10", "--lang", "cn", "--document-layout", "newspaper"])
    assert out[out.index("--document-layout") + 1] == "newspaper"


def test_daily_brief_query_deriver_markdown_override():
    import tools.builtin as bi
    original = bi._get_tools_config
    bi._get_tools_config = lambda: {"long_document_output": "vmprint"}
    try:
        out = _derive_daily_brief_args_from_query("今日新闻 15条 中文，纯Markdown输出")
        assert out == ["fetch", "--max", "15", "--lang", "cn"]
    finally:
        bi._get_tools_config = original
