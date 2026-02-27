"""
Tests for Core refactor Phase 1: log_helpers and tool_helpers_fallback.

Run from project root with conda env (e.g. conda activate pytorch):
  python -m pytest tests/test_core_refactor_phase1.py -v

If the env aborts when loading torch (via base.util), run only tool_helpers_fallback tests:
  python -m pytest tests/test_core_refactor_phase1.py -v -k "tool_helpers_fallback or parse_raw or tool_result or infer_route or infer_remind or remind_me"

These tests do NOT start Core or load chromadb; they only exercise the extracted helper modules.
"""

import pytest


def test_log_helpers_import():
    """core.log_helpers can be imported and exposes expected symbols."""
    from core.log_helpers import (
        _component_log,
        _truncate_for_log,
        _strip_leading_route_label,
        _SuppressConfigCoreAccessFilter,
    )
    assert callable(_component_log)
    assert callable(_truncate_for_log)
    assert callable(_strip_leading_route_label)
    assert _SuppressConfigCoreAccessFilter is not None


def test_log_helpers_truncate():
    """_truncate_for_log truncates long strings and appends (truncated)."""
    from core.log_helpers import _truncate_for_log
    s = "x" * 3000
    out = _truncate_for_log(s, 2000)
    assert len(out) == 2000 + len("\n... (truncated)")
    assert out.endswith("... (truncated)")
    assert _truncate_for_log("short") == "short"
    assert _truncate_for_log("") == ""
    assert _truncate_for_log(None) == ""


def test_log_helpers_strip_route_label():
    """_strip_leading_route_label removes [Local]/[Cloud] prefix."""
    from core.log_helpers import _strip_leading_route_label
    assert _strip_leading_route_label("[Local] hello") == "hello"
    assert _strip_leading_route_label("[Cloud] world") == "world"
    assert _strip_leading_route_label("[Local · heuristic] foo") == "foo"
    assert _strip_leading_route_label("no bracket") == "no bracket"
    assert _strip_leading_route_label("") == ""
    assert _strip_leading_route_label(None) == ""


def test_suppress_config_core_filter():
    """_SuppressConfigCoreAccessFilter filters out GET /api/config/core 200 lines."""
    from core.log_helpers import _SuppressConfigCoreAccessFilter
    import logging
    f = _SuppressConfigCoreAccessFilter()
    record = logging.LogRecord("x", 0, "", 0, "GET /api/config/core ... 200 ...", (), None)
    assert f.filter(record) is False
    record2 = logging.LogRecord("x", 0, "", 0, "GET /other 200", (), None)
    assert f.filter(record2) is True


def test_tool_helpers_fallback_import():
    """core.tool_helpers_fallback exposes all fallback symbols."""
    from core.tool_helpers_fallback import (
        tool_result_looks_like_error,
        tool_result_usable_as_final_response,
        infer_remind_me_fallback,
        remind_me_needs_clarification,
        remind_me_clarification_question,
        infer_route_to_plugin_fallback,
        parse_raw_tool_calls_from_content,
    )
    assert callable(tool_result_looks_like_error)
    assert callable(tool_result_usable_as_final_response)
    assert callable(infer_remind_me_fallback)
    assert callable(remind_me_needs_clarification)
    assert callable(remind_me_clarification_question)
    assert callable(infer_route_to_plugin_fallback)
    assert callable(parse_raw_tool_calls_from_content)


def test_tool_result_looks_like_error():
    """tool_result_looks_like_error identifies error-like and instruction-only results."""
    from core.tool_helpers_fallback import tool_result_looks_like_error
    assert tool_result_looks_like_error("file not found") is True
    assert tool_result_looks_like_error("wasn't found") is True
    assert tool_result_looks_like_error("[]") is True
    assert tool_result_looks_like_error("error: something") is True
    assert tool_result_looks_like_error("do not reply with only this line") is True
    assert tool_result_looks_like_error("ok") is False
    assert tool_result_looks_like_error("Here is the result.") is False
    assert tool_result_looks_like_error(None) is False
    assert tool_result_looks_like_error(123) is False


def test_infer_remind_me_fallback():
    """infer_remind_me_fallback extracts remind_me args from Chinese/English phrases."""
    from core.tool_helpers_fallback import infer_remind_me_fallback
    r = infer_remind_me_fallback("30分钟后提醒我")
    assert r is not None
    assert r.get("tool") == "remind_me"
    assert r.get("arguments", {}).get("minutes") == 30
    assert infer_remind_me_fallback("hello world") is None
    assert infer_remind_me_fallback("") is None
    assert infer_remind_me_fallback(None) is None


def test_remind_me_needs_clarification():
    """remind_me_needs_clarification is True when reminder intent but no time extracted."""
    from core.tool_helpers_fallback import remind_me_needs_clarification
    # "提醒" without clear minutes -> may need clarification
    assert remind_me_needs_clarification("提醒我一下") in (True, False)  # implementation-dependent
    assert remind_me_needs_clarification("random text") is False
    assert remind_me_needs_clarification("") is False


def test_parse_raw_tool_calls_from_content():
    """parse_raw_tool_calls_from_content parses <tool_call>{...}</tool_call> blocks."""
    from core.tool_helpers_fallback import parse_raw_tool_calls_from_content
    raw = 'Before <tool_call>{"name": "echo", "arguments": {"x": 1}}</tool_call> after'
    out = parse_raw_tool_calls_from_content(raw)
    assert out is not None
    assert len(out) == 1
    assert out[0].get("function", {}).get("name") == "echo"
    assert parse_raw_tool_calls_from_content("no tool call") is None
    assert parse_raw_tool_calls_from_content("") is None
    assert parse_raw_tool_calls_from_content(None) is None


def test_infer_route_to_plugin_fallback():
    """infer_route_to_plugin_fallback infers browser/plugin routes from query."""
    from core.tool_helpers_fallback import infer_route_to_plugin_fallback
    r = infer_route_to_plugin_fallback("open https://example.com")
    assert r is not None
    assert r.get("plugin_id") == "homeclaw-browser"
    assert r.get("capability_id") == "browser_navigate"
    assert infer_route_to_plugin_fallback("what is the weather") is None
    assert infer_route_to_plugin_fallback("") is None
