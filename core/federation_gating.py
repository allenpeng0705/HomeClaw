"""Inbound federation authorization (YAML friend link + optional SQLite relationship)."""

from __future__ import annotations

from typing import Tuple

from base.base import User
from base.federation import recipient_accepts_federated_sender

from core.federated_friendships_store import get_state


def inbound_federated_delivery_allowed(
    require_accepted_only: bool,
    from_fid: str,
    sender_local_id: str,
    sender_instance_id: str,
    to_local_user_id: str,
    to_user: User,
) -> Tuple[bool, str]:
    """
    If require_accepted_only: only SQLite state accepted allows delivery (plus blocked/rejected deny always).
    Else: accepted in DB, or no blocking row and YAML mutual federated friend, allows delivery.
    """
    ff = (from_fid or "").strip()
    to_u = (to_local_user_id or "").strip()
    row_state = get_state(ff, to_u)
    if row_state in ("rejected", "blocked"):
        return False, "relationship_blocked"
    if row_state == "accepted":
        return True, ""
    if require_accepted_only:
        return False, "relationship_not_accepted"
    yaml_ok = recipient_accepts_federated_sender(to_user, sender_local_id, sender_instance_id)
    if yaml_ok:
        return True, ""
    return False, "no_friend_link"
