"""
Tests for Portal peers.yml handling in config_api (no TestClient dependency).
"""
from pathlib import Path


def test_peers_load_redacts_inline_api_key(monkeypatch, tmp_path):
    import portal.config_api as api_mod

    monkeypatch.setattr(api_mod, "get_config_dir", lambda: tmp_path)
    (tmp_path / "peers.yml").write_text(
        "peers:\n"
        "  - instance_id: a\n"
        "    base_url: https://example.com\n"
        "    api_key: secret123\n",
        encoding="utf-8",
    )
    data = api_mod.load_config_for_api("peers")
    assert isinstance(data, dict)
    peers = data.get("peers") or []
    assert isinstance(peers, list) and peers
    assert peers[0].get("api_key") == "***"


def test_peers_update_keeps_redacted_api_key(monkeypatch, tmp_path):
    import portal.config_api as api_mod
    import portal.config_backup as backup_mod

    monkeypatch.setattr(api_mod, "get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(backup_mod, "get_config_dir", lambda: tmp_path)
    (tmp_path / "peers.yml").write_text(
        "peers:\n"
        "  - instance_id: keep-me\n"
        "    base_url: https://old.example.com\n"
        "    api_key: original_secret\n",
        encoding="utf-8",
    )

    ok = api_mod.update_config(
        "peers",
        {
            "peers": [
                {
                    "instance_id": "keep-me",
                    "base_url": "https://new.example.com",
                    "api_key": "***",
                }
            ]
        },
    )
    assert ok is True
    raw = Path(tmp_path / "peers.yml").read_text(encoding="utf-8")
    assert "https://new.example.com" in raw
    assert "original_secret" in raw
