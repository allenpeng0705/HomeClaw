"""
Federated Companion user-to-user messaging helpers (cross-instance).

See docs_design/FederatedCompanionUserMessaging.md.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from base.base import User


def parse_fid(fid: str) -> Optional[Tuple[str, str]]:
    """Parse 'local_user_id@instance_id'. Returns (local_user_id, instance_id) or None."""
    s = (fid or "").strip()
    if "@" not in s:
        return None
    local, inst = s.rsplit("@", 1)
    local = local.strip()
    inst = inst.strip()
    if not local or not inst:
        return None
    return (local, inst)


def format_fid(local_user_id: str, instance_id: str) -> str:
    return f"{(local_user_id or '').strip()}@{(instance_id or '').strip()}"


def recipient_accepts_federated_sender(recipient_user: User, sender_local_id: str, sender_instance_id: str) -> bool:
    """True if recipient has a user/remote_user friend with matching user_id and peer_instance_id."""
    sl = (sender_local_id or "").strip()
    si = (sender_instance_id or "").strip()
    if not sl or not si:
        return False
    for f in getattr(recipient_user, "friends", None) or []:
        ftype = (getattr(f, "type", None) or "").strip().lower()
        if ftype not in ("user", "remote_user"):
            continue
        uid = (getattr(f, "user_id", None) or "").strip()
        pinst = (getattr(f, "peer_instance_id", None) or "").strip()
        if uid == sl and pinst == si:
            return True
    return False


def federation_sender_instance_allowed(trusted_list: List[Any], sender_instance_id: str) -> bool:
    """If trusted_list is empty, any instance is allowed (subject to mutual friend). Otherwise sender must be listed."""
    si = (sender_instance_id or "").strip()
    if not si:
        return False
    if not trusted_list:
        return True
    norm = {str(x).strip() for x in trusted_list if x is not None and str(x).strip()}
    return si in norm
