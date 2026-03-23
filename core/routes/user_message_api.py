"""
User-to-user message API (single HomeClaw social network).

POST /api/user-message — send a message to another user (Companion only; Core forwards, no LLM).
GET /api/user-inbox — list messages for the current user.

Auth: same as /inbound (X-API-Key or Bearer when auth_enabled).
Design: docs_design/UserToUserMessagingViaCompanion.md, SocialNetworkDesign.md.
"""

from typing import Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.base import User
from base.federation import format_fid
from base.peer_registry import find_peer_by_instance_id, load_instance_identity, post_federation_user_message_sync, resolve_peer_api_key
from base.util import Util

from core.federation_e2e import validate_e2e_envelope
from core.routes import auth
from core.routes.federation_api import FederationE2EEnvelopeIn
from core.user_inbox import append_message as inbox_append, get_messages as inbox_get_messages, get_thread as inbox_get_thread


def _get_user_by_id(user_id: str) -> Optional[User]:
    users = Util().get_users() or []
    uid = (user_id or "").strip()
    for u in users:
        if (getattr(u, "id", None) or "").strip() == uid or (getattr(u, "name", None) or "").strip() == uid:
            return u
    return None


def _friend_match_for_recipient(from_user: User, to_user_id: str):
    """Return the user/remote_user friend entry matching to_user_id, or None."""
    friends = getattr(from_user, "friends", None) or []
    to_id = (to_user_id or "").strip()
    for f in friends:
        ftype = (getattr(f, "type", None) or "").strip().lower()
        if ftype not in ("user", "remote_user"):
            continue
        uid = (getattr(f, "user_id", None) or "").strip()
        if uid == to_id:
            return f
    return None


class UserMessageRequest(BaseModel):
    from_user_id: str = Field(..., description="Sender user id (must exist in user.yml)")
    to_user_id: str = Field(..., description="Recipient user id")
    text: str = Field("", description="Message text")
    images: Optional[list] = None  # data URLs (data:image/...;base64,...) or file paths Core can read; forwarded to recipient via WebSocket + stored in inbox
    audios: Optional[list] = None  # voice/audio: data URLs (data:audio/...;base64,...) or file paths; push-to-talk; forwarded to recipient via WebSocket + stored in inbox
    videos: Optional[list] = None  # short video (e.g. 10s): data URLs (data:video/...;base64,...) or file paths; forwarded to recipient via WebSocket + stored in inbox
    file_links: Optional[list] = None  # URLs or paths; stored in inbox for recipient
    e2e: Optional[FederationE2EEnvelopeIn] = None  # P5: hc-e2e-v1 for federated friends only


def get_user_message_post_handler(core):
    """Return handler for POST /api/user-message. Sender must have recipient as user-type friend."""

    async def post_user_message(
        body: UserMessageRequest,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            from_user_id = (body.from_user_id or "").strip()
            to_user_id = (body.to_user_id or "").strip()
            text = (body.text or "").strip()
            if not from_user_id or not to_user_id:
                return JSONResponse(status_code=400, content={"error": "from_user_id and to_user_id required"})
            from_user = _get_user_by_id(from_user_id)
            if not from_user:
                return JSONResponse(status_code=403, content={"error": "from_user_id not found"})
            friend_match = _friend_match_for_recipient(from_user, to_user_id)
            if not friend_match:
                return JSONResponse(
                    status_code=403,
                    content={"error": "Recipient is not a user-type friend of the sender. Add them in user.yml (type: user, user_id: <id>)."},
                )
            if body.e2e is not None:
                peer_chk = (getattr(friend_match, "peer_instance_id", None) or "").strip()
                if not peer_chk:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "e2e_only_for_federated_friends", "hint": "E2E envelopes are only for friends with peer_instance_id."},
                    )
            peer_inst = (getattr(friend_match, "peer_instance_id", None) or "").strip()
            if peer_inst:
                meta = Util().get_core_metadata()
                if not bool(getattr(meta, "federation_enabled", False)):
                    return JSONResponse(
                        status_code=403,
                        content={"error": "federation_disabled", "hint": "Set federation_enabled: true in config/core.yml to message friends on another instance."},
                    )
                ident = load_instance_identity()
                my_iid = (ident.get("instance_id") or "").strip()
                if not my_iid:
                    return JSONResponse(
                        status_code=503,
                        content={"error": "Local instance_id missing", "hint": "Set instance_id in config/instance_identity.yml for federated messaging."},
                    )
                peer = find_peer_by_instance_id(peer_inst)
                if not peer:
                    return JSONResponse(
                        status_code=502,
                        content={"error": "peer_not_configured", "hint": f"No peers.yml entry for instance_id {peer_inst}."},
                    )
                api_key = resolve_peer_api_key(peer)
                base_url = (peer.get("base_url") or "").strip().rstrip("/")
                if not base_url:
                    return JSONResponse(status_code=502, content={"error": "peer base_url missing"})
                e2e_on = bool(getattr(meta, "federation_e2e_enabled", False))
                e2e_req = bool(getattr(meta, "federation_e2e_require_encrypted", False))
                has_e2e = body.e2e is not None
                if e2e_req and not has_e2e:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "e2e_required", "hint": "This Core requires hc-e2e-v1 for federated user messages."},
                    )
                if has_e2e and not e2e_on:
                    return JSONResponse(status_code=403, content={"error": "federation_e2e_disabled"})
                if has_e2e:
                    ed = body.e2e.model_dump() if body.e2e else {}
                    ok_e, err_e = validate_e2e_envelope(ed)
                    if not ok_e:
                        return JSONResponse(status_code=400, content={"error": "invalid_e2e_envelope", "detail": err_e})
                    if body.images or body.audios or body.videos or body.file_links:
                        return JSONResponse(
                            status_code=400,
                            content={"error": "e2e_media_not_supported"},
                        )
                from_name = (getattr(from_user, "name", None) or from_user_id or "").strip()
                from_fid = format_fid(from_user_id, my_iid)
                payload = {
                    "from_fid": from_fid,
                    "to_local_user_id": to_user_id,
                    "text": "" if has_e2e else text,
                    "images": None if has_e2e else body.images,
                    "audios": None if has_e2e else body.audios,
                    "videos": None if has_e2e else body.videos,
                    "file_links": None if has_e2e else body.file_links,
                    "from_display_name": from_name,
                }
                if has_e2e and body.e2e:
                    payload["e2e"] = body.e2e.model_dump()
                remote = post_federation_user_message_sync(base_url, payload, api_key=api_key)
                sc = int(remote.get("status_code") or 0)
                if remote.get("ok") and sc == 200:
                    mid = remote.get("message_id")
                    return JSONResponse(status_code=200, content={"ok": True, "message_id": mid, "federated": True})
                err = (remote.get("error") or "federation_failed") if isinstance(remote, dict) else "federation_failed"
                if sc <= 0:
                    sc = 502
                return JSONResponse(status_code=sc, content={"error": err, "detail": remote if isinstance(remote, dict) else {}})
            to_user = _get_user_by_id(to_user_id)
            if not to_user:
                return JSONResponse(status_code=404, content={"error": "to_user_id not found"})
            if body.e2e is not None:
                return JSONResponse(status_code=400, content={"error": "e2e_only_for_federated_friends"})
            from_name = (getattr(from_user, "name", None) or from_user_id or "").strip()
            msg_id = inbox_append(
                to_user_id=to_user_id,
                from_user_id=from_user_id,
                from_user_name=from_name,
                text=text,
                images=body.images,
                audios=body.audios,
                videos=body.videos,
                file_links=body.file_links,
            )
            if not msg_id:
                return JSONResponse(status_code=500, content={"error": "Failed to store message"})
            try:
                if hasattr(core, "deliver_to_user"):
                    await core.deliver_to_user(
                        to_user_id,
                        text or "(no text)",
                        images=body.images,
                        audios=body.audios,
                        videos=body.videos,
                        source="user_message",
                        from_friend=from_name,
                        from_user_id=from_user_id,
                    )
            except Exception as e:
                logger.debug("user-message: deliver_to_user failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True, "message_id": msg_id})
        except Exception as e:
            logger.warning("user-message POST failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return post_user_message


def get_user_inbox_handler(core):  # noqa: ARG001
    """Return handler for GET /api/user-inbox."""

    async def get_user_inbox(
        user_id: str = "",
        limit: int = 50,
        after_id: Optional[str] = None,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            user_id = (user_id or "").strip()
            if not user_id:
                return JSONResponse(status_code=400, content={"error": "user_id required"})
            try:
                limit = int(limit) if limit is not None else 50
            except (TypeError, ValueError):
                limit = 50
            limit = max(1, min(100, limit))
            messages = inbox_get_messages(user_id, limit=limit, after_id=after_id)
            # Recipient of all inbox messages is user_id; add to_user_id so Companion can filter threads.
            for m in messages:
                if isinstance(m, dict):
                    m["to_user_id"] = user_id
            return JSONResponse(status_code=200, content={"user_id": user_id, "messages": messages})
        except Exception as e:
            logger.warning("user-inbox GET failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_user_inbox


def get_user_inbox_thread_handler(core):  # noqa: ARG001
    """Return handler for GET /api/user-inbox/thread. Returns full conversation between user_id and other_user_id (both directions)."""

    async def get_user_inbox_thread(
        user_id: str = "",
        other_user_id: str = "",
        limit: int = 100,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            user_id = (user_id or "").strip()
            other_user_id = (other_user_id or "").strip()
            if not user_id or not other_user_id:
                return JSONResponse(status_code=400, content={"error": "user_id and other_user_id required"})
            try:
                limit = int(limit) if limit is not None else 100
            except (TypeError, ValueError):
                limit = 100
            limit = max(1, min(200, limit))
            messages = inbox_get_thread(user_id, other_user_id, limit=limit)
            return JSONResponse(status_code=200, content={"user_id": user_id, "other_user_id": other_user_id, "messages": messages})
        except Exception as e:
            logger.warning("user-inbox thread GET failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_user_inbox_thread
