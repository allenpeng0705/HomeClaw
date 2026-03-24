"""
Tests for Portal skills_and_plugins.yml handling in config_api.
"""


def test_skills_plugins_load_includes_bridge_defaults_and_redacts_keys(monkeypatch, tmp_path):
    import portal.config_api as api_mod

    monkeypatch.setattr(api_mod, "get_config_dir", lambda: tmp_path)
    (tmp_path / "skills_and_plugins.yml").write_text(
        "plugins_description_max_chars: 0\n"
        "cursor_bridge_auto_start: true\n"
        "cursor_bridge_cursor_api_key: secret_cursor\n"
        "cursor_bridge_bridge_api_key: secret_bridge\n"
        "claude_code_api_key: secret_claude\n",
        encoding="utf-8",
    )
    data = api_mod.load_config_for_api("skills_and_plugins")
    assert isinstance(data, dict)
    assert data.get("cursor_bridge_cursor_api_key") == "***"
    assert data.get("cursor_bridge_bridge_api_key") == "***"
    assert data.get("claude_code_api_key") == "***"
    # default field present even when absent from YAML
    assert "cursor_bridge_agent_path" in data


def test_skills_plugins_update_keeps_redacted_secret_placeholders(monkeypatch, tmp_path):
    import portal.config_api as api_mod
    import portal.config_backup as backup_mod

    monkeypatch.setattr(api_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(backup_mod, "get_config_dir", lambda: tmp_path)
    (tmp_path / "skills_and_plugins.yml").write_text(
        "cursor_bridge_cursor_api_key: old_cursor_secret\n"
        "claude_code_api_key: old_claude_secret\n"
        "cursor_bridge_auto_start: true\n",
        encoding="utf-8",
    )
    ok = api_mod.update_config(
        "skills_and_plugins",
        {
            "cursor_bridge_cursor_api_key": "***",
            "claude_code_api_key": "***",
            "cursor_bridge_auto_start": False,
        },
    )
    assert ok is True
    raw = (tmp_path / "skills_and_plugins.yml").read_text(encoding="utf-8")
    assert "old_cursor_secret" in raw
    assert "old_claude_secret" in raw
    assert "cursor_bridge_auto_start: false" in raw.lower()
