"""
Tests for multi-instance peer registry (merge, import payload, rate limits).

Run from project root:
  python -m pytest tests/test_peer_registry.py -v
"""

import os
import tempfile


def test_peer_dict_from_import_payload_top_level_peer():
    from base.peer_registry import peer_dict_from_import_payload

    d = peer_dict_from_import_payload(
        {
            "peer": {
                "instance_id": "b",
                "base_url": "https://b.example:9000",
                "inbound_user_id": "u1",
            },
            "recipient_import_peer": {"peer": {"instance_id": "a", "base_url": "http://a:1", "inbound_user_id": "u2"}},
        }
    )
    assert d is not None
    assert d["instance_id"] == "b"


def test_peer_dict_from_import_payload_recipient_only():
    from base.peer_registry import peer_dict_from_import_payload

    d = peer_dict_from_import_payload(
        {
            "recipient_import_peer": {
                "peer": {
                    "instance_id": "a",
                    "base_url": "http://127.0.0.1:9001",
                    "inbound_user_id": "peer_bot",
                }
            }
        }
    )
    assert d is not None
    assert d["instance_id"] == "a"


def test_peer_dict_from_import_payload_flat():
    from base.peer_registry import peer_dict_from_import_payload

    d = peer_dict_from_import_payload(
        {"instance_id": "x", "base_url": "http://x", "inbound_user_id": "u"}
    )
    assert d is not None
    assert d["instance_id"] == "x"


def test_merge_peer_entry_replaces_same_id():
    from base.peer_registry import merge_peer_entry

    with tempfile.TemporaryDirectory() as td:
        yml = os.path.join(td, "peers.yml")
        with open(yml, "w", encoding="utf-8") as f:
            f.write(
                "peers:\n"
                "  - instance_id: a\n"
                "    base_url: http://old\n"
                "    inbound_user_id: u\n"
            )
        raw_before = open(yml, encoding="utf-8").read()
        assert "http://old" in raw_before
        ok, msg = merge_peer_entry(
            {
                "instance_id": "a",
                "base_url": "http://new",
                "inbound_user_id": "u",
                "display_name": "A2",
            },
            config_dir_path=td,
        )
        assert ok
        raw_after = open(yml, encoding="utf-8").read()
        assert "http://new" in raw_after
        assert "http://old" not in raw_after


def test_peer_invite_rate_limits_reset_and_buckets():
    from base import peer_registry as pr

    pr.reset_peer_invite_rate_limits_for_testing()
    ip = "10.0.0.1"
    assert not pr.peer_invite_consume_all_attempts_exceeded(ip)
    for _ in range(pr.CONSUME_ALL_MAX_PER_WINDOW):
        assert not pr.peer_invite_consume_all_attempts_exceeded(ip)
        pr.peer_invite_consume_record_attempt(ip)
    assert pr.peer_invite_consume_all_attempts_exceeded(ip)

    pr.reset_peer_invite_rate_limits_for_testing()
    for _ in range(pr.CONSUME_FAIL_MAX_PER_WINDOW):
        assert not pr.peer_invite_consume_record_failed_verify(ip)
    assert pr.peer_invite_consume_record_failed_verify(ip)

    pr.reset_peer_invite_rate_limits_for_testing()
