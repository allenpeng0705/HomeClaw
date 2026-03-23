"""
Tests for federated user messaging helpers and inbox metadata.

Run: python -m pytest tests/test_federation_user_message.py -v
"""

import json
import os
import tempfile

from base.base import Friend, User
from base.federation import (
    federation_sender_instance_allowed,
    format_fid,
    parse_fid,
    recipient_accepts_federated_sender,
)


def test_parse_fid_and_format():
    assert parse_fid("alice@inst-a") == ("alice", "inst-a")
    assert parse_fid("bad") is None
    assert parse_fid("@x") is None
    assert format_fid("alice", "inst-a") == "alice@inst-a"


def test_recipient_accepts_federated_sender():
    u = User(
        name="Bob",
        email=[],
        im=[],
        phone=[],
        permissions=[],
        id="bob",
        type="normal",
        friends=[
            Friend(
                name="AliceRemote",
                relation=None,
                who=None,
                identity=None,
                preset=None,
                type="user",
                user_id="alice",
                peer_instance_id="core-a",
            )
        ],
    )
    assert recipient_accepts_federated_sender(u, "alice", "core-a")
    assert not recipient_accepts_federated_sender(u, "alice", "other")
    assert not recipient_accepts_federated_sender(u, "carol", "core-a")


def test_federation_sender_instance_allowed():
    assert federation_sender_instance_allowed([], "any")
    assert federation_sender_instance_allowed(["a", "b"], "a")
    assert not federation_sender_instance_allowed(["a"], "x")


def test_user_inbox_append_metadata():
    from core.user_inbox import append_message

    with tempfile.TemporaryDirectory() as td:
        from unittest.mock import patch

        with patch("core.user_inbox.Util") as mock_u:
            inst = mock_u.return_value
            inst.data_path.return_value = td
            mid = append_message(
                "u1",
                "u2",
                "Two",
                "hi",
                metadata={"from_instance_id": "remote", "source": "federation"},
            )
            assert mid
            path = os.path.join(td, "user_inbox", "u1.json")
            assert os.path.isfile(path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            msgs = data.get("messages") or []
            assert msgs
            last = msgs[-1]
            assert last.get("from_instance_id") == "remote"
            assert last.get("source") == "federation"


def _bob_user_yaml_friend_alice():
    return User(
        name="Bob",
        email=[],
        im=[],
        phone=[],
        permissions=[],
        id="bob",
        type="normal",
        friends=[
            Friend(
                name="AliceRemote",
                relation=None,
                who=None,
                identity=None,
                preset=None,
                type="user",
                user_id="alice",
                peer_instance_id="core-a",
            )
        ],
    )


def test_inbound_federation_gating_yaml_ok_without_row():
    from core.federation_gating import inbound_federated_delivery_allowed

    u = _bob_user_yaml_friend_alice()
    ok, reason = inbound_federated_delivery_allowed(
        False,
        "alice@core-a",
        "alice",
        "core-a",
        "bob",
        u,
    )
    assert ok
    assert reason == ""


def test_inbound_federation_gating_require_accepted_without_row():
    from core.federation_gating import inbound_federated_delivery_allowed

    u = _bob_user_yaml_friend_alice()
    ok, reason = inbound_federated_delivery_allowed(
        True,
        "alice@core-a",
        "alice",
        "core-a",
        "bob",
        u,
    )
    assert not ok
    assert reason == "relationship_not_accepted"


def test_federated_friendships_store_pending_accept():
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as td:
        with patch("core.federated_friendships_store.Util") as mock_u:
            mock_u.return_value.data_path.return_value = td
            from core.federated_friendships_store import (
                create_or_refresh_pending,
                is_accepted,
                set_state_by_id,
            )

            rid, tag = create_or_refresh_pending("alice@core-a", "bob", "hi")
            assert tag == "created"
            assert rid
            row = set_state_by_id(rid, "bob", "accepted")
            assert row
            assert is_accepted("alice@core-a", "bob")
