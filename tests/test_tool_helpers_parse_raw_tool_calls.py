"""Tests for parse_raw_tool_calls_from_content (JSON, XML, call-style, case-insensitive tags)."""
from __future__ import annotations

import json

import pytest

from core.services.tool_helpers import parse_raw_tool_calls_from_content


def test_json_closed_block():
    raw = '<tool_call>{"name":"run_skill","arguments":{"skill_name":"weather-1.0.0","script":"x.py","args":["a"]}}</tool_call>'
    out = parse_raw_tool_calls_from_content(raw)
    assert out and len(out) == 1
    args = json.loads(out[0]["function"]["arguments"])
    assert args["skill_name"] == "weather-1.0.0"


def test_case_insensitive_tool_call_tags():
    raw = '<Tool_Call>{"name":"time","arguments":{}}</Tool_Call>'
    out = parse_raw_tool_calls_from_content(raw)
    assert out and out[0]["function"]["name"] == "time"


def test_run_skill_call_style_truncated():
    sample = (
        '<tool_call>run_skill(skill_name="daily-brief", script=None, args=["--language=zh","count\n\n'
        "## Architectural junk"
    )
    out = parse_raw_tool_calls_from_content(sample)
    assert out and len(out) == 1
    assert out[0]["function"]["name"] == "run_skill"
    args = json.loads(out[0]["function"]["arguments"])
    assert args["skill_name"] == "daily-brief"
    assert "args" not in args


def test_run_skill_keeps_valid_fetch_args():
    raw = '<tool_call>run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch", "--max", "5"])</tool_call>'
    out = parse_raw_tool_calls_from_content(raw)
    assert out
    args = json.loads(out[0]["function"]["arguments"])
    assert args["args"] == ["fetch", "--max", "5"]


def test_web_search_call_style():
    raw = '<tool_call>web_search(query="weather tokyo", count=5)</tool_call>'
    out = parse_raw_tool_calls_from_content(raw)
    assert out
    args = json.loads(out[0]["function"]["arguments"])
    assert args["query"] == "weather tokyo"
    assert args.get("count") == 5


def test_web_search_positional_query():
    raw = '<tool_call>web_search("plain query")'
    out = parse_raw_tool_calls_from_content(raw)
    assert out
    args = json.loads(out[0]["function"]["arguments"])
    assert args["query"] == "plain query"


def test_oversized_skill_name_rejected():
    huge = "a" * 400
    raw = f'<tool_call>run_skill(skill_name="{huge}", script=None)</tool_call>'
    assert parse_raw_tool_calls_from_content(raw) is None


def test_no_tool_call_returns_none():
    assert parse_raw_tool_calls_from_content("hello") is None
    assert parse_raw_tool_calls_from_content("") is None
    assert parse_raw_tool_calls_from_content(None) is None  # type: ignore[arg-type]


def test_xml_run_skill_without_skill_name_rejected():
    """Broken Qwen-style XML must not become run_skill with junk keys only (avoids repeated failed execute)."""
    raw = (
        '<tool_call><function=run_skill>\n</parameter><script_name></skill-name>>daily-brief, '
        "script='render.py'</tool_call>"
    )
    assert parse_raw_tool_calls_from_content(raw) is None


def test_json_run_skill_without_skill_name_rejected():
    raw = '<tool_call>{"name":"run_skill","arguments":{"script_name":""}}</tool_call>'
    assert parse_raw_tool_calls_from_content(raw) is None
