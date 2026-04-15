"""Routing debug footer (response suffix) for intent/skills/tools — formatting and memory strip."""

from core.log_helpers import format_routing_debug_response_suffix, strip_routing_debug_footer_for_memory


def test_strip_routing_debug_footer_for_memory():
    body = "Hello."
    suffix = format_routing_debug_response_suffix(
        intent_enabled=True,
        categories=["weather"],
        skills_folders=["weather-1.0.0"],
        skills_note="semantic",
        llm_exposed_tool_names=["web_search", "run_skill"],
        execution_path="react",
        main_llm_mode="mix",
        mix_route="local",
        mix_layer="heuristic",
        effective_model="local_models/x",
        react_trace=[{"react_round": 0, "tool": "web_search", "args_preview": "{}", "llm": "local_models/x"}],
        include_react_trace=True,
    )
    full = body + suffix
    stripped = strip_routing_debug_footer_for_memory(full)
    assert stripped == body
    assert "**[HomeClaw routing debug]**" in suffix
    assert "Execution path:** react" in suffix


def test_format_routing_debug_omits_react_when_not_react_path():
    s = format_routing_debug_response_suffix(
        intent_enabled=False,
        categories=[],
        skills_folders=[],
        skills_note="",
        llm_exposed_tool_names=[],
        execution_path="dag",
        main_llm_mode="cloud",
        mix_route=None,
        mix_layer=None,
        effective_model=None,
        react_trace=[{"react_round": 0, "tool": "x", "args_preview": "{}", "llm": ""}],
        include_react_trace=True,
    )
    assert "ReAct trace" not in s
