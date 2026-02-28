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
        {"name": "Note", "preset": " note "},
    ]
    friends = User._parse_friends(raw)
    assert len(friends) >= 2
    # HomeClaw is first
    assert (friends[0].name or "").strip().lower() == "homeclaw"
    assert getattr(friends[0], "preset", None) is None
    # Find Reminder and Note
    by_name = {(getattr(f, "name", "") or "").strip(): f for f in friends}
    assert "Reminder" in by_name
    assert getattr(by_name["Reminder"], "preset", None) == "reminder"
    assert "Note" in by_name
    assert getattr(by_name["Note"], "preset", None) == "note"  # stripped


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
        assert "reminder" in result or "note" in result or "finder" in result
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


def test_get_tool_names_for_preset_note():
    """get_tool_names_for_preset('note') returns list with file/save tools; no append_agent_memory/append_daily_memory (Note uses Cognee only)."""
    from base.friend_presets import get_tool_names_for_preset

    names = get_tool_names_for_preset("note")
    assert names is not None
    assert "file_write" in names
    assert "document_read" in names
    assert "save_result_page" in names
    assert "append_agent_memory" not in names
    assert "append_daily_memory" not in names


def test_get_tool_names_for_preset_finder():
    """get_tool_names_for_preset('finder') returns list including file_find, folder_list."""
    from base.friend_presets import get_tool_names_for_preset

    names = get_tool_names_for_preset("finder")
    assert names is not None
    assert "file_find" in names
    assert "folder_list" in names


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
    # No duplicates (e.g. document_read in both note and finder)
    note_finder = get_tool_names_for_preset_value(["note", "finder"])
    assert note_finder is not None
    doc_read_count = sum(1 for t in note_finder if t == "document_read")
    assert doc_read_count == 1


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


def test_note_preset_has_model_routing_and_save_policy():
    """Step 5: note preset has model_routing local_only and save_policy full for Core to enforce."""
    from base.friend_presets import get_friend_preset_config

    cfg = get_friend_preset_config("note")
    assert cfg is not None and isinstance(cfg, dict)
    assert str(cfg.get("model_routing") or "").strip().lower() == "local_only"
    assert str(cfg.get("save_policy") or "").strip().lower() == "full"


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
    """Preset can have history as integer (last N turns) or 'full'; reminder/note/finder use a number."""
    from base.friend_presets import get_friend_preset_config

    for name in ("reminder", "note", "finder"):
        cfg = get_friend_preset_config(name)
        assert cfg is not None
        hist = cfg.get("history")
        assert hist == "full" or (isinstance(hist, int) and hist > 0), f"preset {name} should have history: full or positive integer"
