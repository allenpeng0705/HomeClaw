"""P3: clawcode profile alias, run_skill in coding, clawcode.yml addendum."""

from __future__ import annotations

from unittest.mock import patch

from base.tool_profiles import (
    VALID_PROFILES,
    filter_tools_by_profile,
    get_tool_names_for_profile,
)
from base.tools import ToolDefinition


async def _noop_exec(*_a, **_k):
    return ""


def test_clawcode_in_valid_profiles():
    assert "clawcode" in VALID_PROFILES


def test_clawcode_profile_same_tool_set_as_coding():
    a = set(get_tool_names_for_profile("coding"))
    b = set(get_tool_names_for_profile("clawcode"))
    assert a == b
    assert "run_skill" in a
    assert "exec" in a


def test_filter_clawcode_union():
    tools = [
        ToolDefinition(name="exec", description="", parameters={}, execute_async=_noop_exec),
        ToolDefinition(name="remind_me", description="", parameters={}, execute_async=_noop_exec),
    ]
    out = filter_tools_by_profile(tools, ["clawcode"])
    names = {t.name for t in out}
    assert "exec" in names
    assert "remind_me" not in names


def test_load_system_prompt_addendum_from_repo():
    from core.clawcode_prompt import load_system_prompt_addendum

    text = load_system_prompt_addendum()
    assert "Claw-Code" in text or "coding agent" in text.lower()


@patch("core.clawcode_prompt.load_clawcode_yaml", return_value={})
def test_load_system_prompt_addendum_when_yaml_has_no_key(_mock):
    from core.clawcode_prompt import load_system_prompt_addendum

    assert load_system_prompt_addendum() == ""
