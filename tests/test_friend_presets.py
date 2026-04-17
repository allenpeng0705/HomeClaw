"""
Tests for friend presets (Step 1): Friend.preset, User parse/serialize, load_friend_presets, get_tool_names_for_preset.

Run from project root:
  python -m pytest tests/test_friend_presets.py -v
"""

import pytest


def test_user_parse_friends_with_preset():
    """User._parse_friends parses preset from friend dict; friend has preset attribute."""
    from base.base import User, Friend

    raw = [
        {"name": "HomeClaw"},
        {"name": "Reminder", "preset": "reminder"},
        {"name": "Knowledge", "preset": " knowledge "},
    ]
    friends = User._parse_friends(raw)
    assert len(friends) >= 2
    # HomeClaw is first
    assert (friends[0].name or "").strip().lower() == "homeclaw"
    assert getattr(friends[0], "preset", None) is None
    # Find Reminder and Knowledge
    by_name = {(getattr(f, "name", "") or "").strip(): f for f in friends}
    assert "Reminder" in by_name
    assert getattr(by_name["Reminder"], "preset", None) == "reminder"
    assert "Knowledge" in by_name
    assert getattr(by_name["Knowledge"], "preset", None) == "knowledge"  # stripped


def test_user_friends_to_dict_list_includes_preset():
    """_friends_to_dict_list serializes preset when set."""
    from base.base import User, Friend

    friends = [
        Friend(name="HomeClaw", relation=None, who=None, identity=None, preset=None),
        Friend(name="Reminder", relation=None, who=None, identity=None, preset="reminder"),
    ]
    out = User._friends_to_dict_list(friends)
    assert len(out) == 2
    assert out[0].get("name") == "HomeClaw"
    assert "preset" not in out[0] or out[0].get("preset") is None or out[0].get("preset") == ""
    assert out[1].get("name") == "Reminder"
    assert out[1].get("preset") == "reminder"


def test_load_friend_presets_missing_file_returns_empty():
    """load_friend_presets with non-existent path returns {}."""
    from base.friend_presets import load_friend_presets

    result = load_friend_presets("/nonexistent/path/friend_presets.yml")
    assert result == {}


def test_load_friend_presets_from_config():
    """load_friend_presets loads config/friend_presets.yml when path not given or points to project config."""
    from base.friend_presets import load_friend_presets
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    config_path = str(root / "config" / "friend_presets.yml")
    result = load_friend_presets(config_path)
    assert isinstance(result, dict)
    # May be empty if file not in test env; if present, check structure
    if result:
        assert "reminder" in result or "knowledge" in result or "finder" in result
        for key, cfg in result.items():
            assert isinstance(cfg, dict)
            if "tools_preset" in cfg:
                assert isinstance(cfg["tools_preset"], str)


def test_get_tool_names_for_preset_reminder():
    """get_tool_names_for_preset('reminder') returns list including remind_me, cron_schedule, route_to_tam."""
    from base.friend_presets import get_tool_names_for_preset

    names = get_tool_names_for_preset("reminder")
    assert names is not None
    assert "remind_me" in names
    assert "cron_schedule" in names
    assert "route_to_tam" in names
    assert "record_date" in names


def test_get_tool_names_for_preset_knowledge():
    """get_tool_names_for_preset('knowledge') returns KB tools + time only."""
    from base.friend_presets import get_tool_names_for_preset

    names = get_tool_names_for_preset("knowledge")
    assert names is not None
    assert "knowledge_base_search" in names
    assert "knowledge_base_add" in names
    assert "knowledge_base_remove" in names
    assert "knowledge_base_list" in names
    assert "time" in names
    assert "document_read" not in names
    assert "web_search" not in names


def test_get_tool_names_for_preset_finder():
    """get_tool_names_for_preset('finder') returns list including file_find, folder_list."""
    from base.friend_presets import get_tool_names_for_preset

    names = get_tool_names_for_preset("finder")
    assert names is not None
    assert "file_find" in names
    assert "folder_list" in names


def test_format_preset_display_name():
    """format_preset_display_name uses YAML display_name/friend_display_name or capitalizes id."""
    from base.friend_presets import format_preset_display_name

    assert format_preset_display_name("finder") == "Finder"
    assert format_preset_display_name("knowledge", {"display_name": "知识库"}) == "知识库"
    assert format_preset_display_name("knowledge", {"friend_display_name": "KB"}) == "KB"
    assert format_preset_display_name("reminder", {}) == "Reminder"


def test_should_skip_intent_router_for_friend():
    """Product presets with tools_preset skip router when listed; empty list disables; unknown preset False."""
    from base.friend_presets import should_skip_intent_router_for_friend

    assert should_skip_intent_router_for_friend("reminder", {}) is True
    assert should_skip_intent_router_for_friend("finder", {}) is True
    assert should_skip_intent_router_for_friend("knowledge", {}) is True
    assert should_skip_intent_router_for_friend("cursor", {}) is False
    assert should_skip_intent_router_for_friend("", {}) is False
    assert should_skip_intent_router_for_friend("reminder", {"skip_for_friend_presets": []}) is False
    assert should_skip_intent_router_for_friend("reminder", {"skip_for_friend_presets": ["reminder"]}) is True
    assert should_skip_intent_router_for_friend("reminder", {"skip_for_friend_presets": ["finder"]}) is False
    # Only blank entries → must not skip router for all presets (regression guard)
    assert should_skip_intent_router_for_friend("reminder", {"skip_for_friend_presets": ["", "  "]}) is False
    assert should_skip_intent_router_for_friend("reminder", {"skip_for_friend_presets": "reminder, finder"}) is True
    assert should_skip_intent_router_for_friend("knowledge", {"skip_for_friend_presets": "knowledge"}) is True


def test_get_tool_names_for_preset_unknown_returns_none():
    """get_tool_names_for_preset('unknown') returns None."""
    from base.friend_presets import get_tool_names_for_preset

    assert get_tool_names_for_preset("unknown") is None
    assert get_tool_names_for_preset("") is None
    assert get_tool_names_for_preset(None) is None


def test_get_friend_preset_config():
    """get_friend_preset_config returns dict for known preset when YAML is loaded."""
    from base.friend_presets import get_friend_preset_config, load_friend_presets
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    config_path = str(root / "config" / "friend_presets.yml")
    presets = load_friend_presets(config_path)
    if not presets:
        pytest.skip("config/friend_presets.yml not found or empty")
    cfg = get_friend_preset_config("reminder", config_path)
    assert cfg is not None
    assert cfg.get("tools_preset") == "reminder"
    assert "system_prompt" in cfg


def test_get_tool_names_for_preset_value_array():
    """get_tool_names_for_preset_value accepts array of preset names and returns union of tool names."""
    from base.friend_presets import get_tool_names_for_preset_value

    # Single string: same as get_tool_names_for_preset
    single = get_tool_names_for_preset_value("reminder")
    assert single is not None
    assert "remind_me" in single
    # Array: union of reminder + finder
    combined = get_tool_names_for_preset_value(["reminder", "finder"])
    assert combined is not None
    assert "remind_me" in combined
    assert "file_find" in combined
    assert "folder_list" in combined
    # No duplicates (e.g. time in both reminder and knowledge)
    reminder_knowledge = get_tool_names_for_preset_value(["reminder", "knowledge"])
    assert reminder_knowledge is not None
    time_count = sum(1 for t in reminder_knowledge if t == "time")
    assert time_count == 1
    assert "knowledge_base_search" in reminder_knowledge
    assert "remind_me" in reminder_knowledge


def test_filter_tools_by_preset_logic():
    """Step 2: filtering all_tools by preset allowed list keeps only allowed tool names."""
    from base.friend_presets import get_tool_names_for_preset

    allowed_names = get_tool_names_for_preset("reminder")
    assert allowed_names is not None
    allowed_set = set(allowed_names)
    mock_tools = [
        {"function": {"name": "remind_me"}},
        {"function": {"name": "run_skill"}},
        {"function": {"name": "cron_schedule"}},
    ]
    filtered = [t for t in mock_tools if ((t.get("function") or {}).get("name")) in allowed_set]
    assert len(filtered) == 2
    names = [t["function"]["name"] for t in filtered]
    assert "remind_me" in names
    assert "cron_schedule" in names
    assert "run_skill" not in names


def test_knowledge_preset_has_tools_and_history():
    """knowledge preset defines tools_preset and history for Companion KB friend."""
    from base.friend_presets import get_friend_preset_config

    cfg = get_friend_preset_config("knowledge")
    assert cfg is not None and isinstance(cfg, dict)
    assert str(cfg.get("tools_preset") or "").strip().lower() == "knowledge"
    hist = cfg.get("history")
    assert hist == "full" or (isinstance(hist, int) and hist > 0)


def test_trim_messages_to_last_n_turns():
    """Friend preset history: trim to last N turns (N user messages + their replies)."""
    from base.friend_presets import trim_messages_to_last_n_turns

    msgs = [
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "c"},
    ]
    out = trim_messages_to_last_n_turns(msgs, 2)
    assert len(out) == 4
    assert out[0]["content"] == "2" and out[-1]["content"] == "c"
    out_all = trim_messages_to_last_n_turns(msgs, 10)
    assert len(out_all) == 6
    out_one = trim_messages_to_last_n_turns(msgs, 1)
    assert len(out_one) == 2 and out_one[0]["content"] == "3"


def test_preset_history_integer_from_config():
    """Preset can have history as integer (last N turns) or 'full'; reminder/knowledge/finder use a number."""
    from base.friend_presets import get_friend_preset_config

    for name in ("reminder", "knowledge", "finder"):
        cfg = get_friend_preset_config(name)
        assert cfg is not None
        hist = cfg.get("history")
        assert hist == "full" or (isinstance(hist, int) and hist > 0), f"preset {name} should have history: full or positive integer"
