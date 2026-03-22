"""
Inbound federation API: cross-instance user-to-user messages (Companion).

POST /api/federation/user-message — called by a trusted peer Core; delivers to local user inbox.
See docs_design/FederatedCompanionUserMessaging.md.
"""

from typing import Any, List, Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.base import User
from base.federation import federation_sender_instance_allowed, parse_fid
from base.util import Util

from core.federated_friendships_store import create_or_refresh_pending, upsert_reciprocal_accepted
from core.federation_e2e import validate_e2e_envelope
from core.federation_gating import inbound_federated_delivery_allowed
from core.routes import auth
from core.user_inbox import append_message as inbox_append


def _get_user_by_id(user_id: str) -> Optional[User]:
    users = Util().get_users() or []
    uid = (user_id or "").strip()
    for u in users:
        if (getattr(u, "id", None) or "").strip() == uid or (getattr(u, "name", None) or "").strip() == uid:
            return u
    return None


class FederationE2EEnvelopeIn(BaseModel):
    algo: str = Field(default="hc-e2e-v1", description="hc-e2e-v1")
    ephemeral_public_key_b64: str = Field(..., description="Ephemeral X25519 public key, base64")
    nonce_b64: str = Field(..., description="AES-GCM nonce, 12 bytes base64")
    ciphertext_b64: str = Field(..., description="AES-GCM ciphertext + tag, base64")


class FederatedUserMessageRequest(BaseModel):
    from_fid: str = Field(..., description="Sender identity: local_user_id@remote_instance_id")
    to_local_user_id: str = Field(..., description="Recipient user id on this Core")
    text: str = Field("", description="Message text (empty when e2e envelope is used)")
    images: Optional[list] = None
    audios: Optional[list] = None
    videos: Optional[list] = None
    file_links: Optional[list] = None
    from_display_name: Optional[str] = None
    client_message_id: Optional[str] = None
    e2e: Optional[FederationE2EEnvelopeIn] = None


def get_federation_user_message_post_handler(core):
    """Return handler for POST /api/federation/user-message."""

    async def post_federation_user_message(
        body: FederatedUserMessageRequest,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            parsed = parse_fid(body.from_fid or "")
            if not parsed:
                return JSONResponse(status_code=400, content={"error": "Invalid from_fid (expected user_id@instance_id)"})
            sender_local_id, sender_instance_id = parsed
            to_uid = (body.to_local_user_id or "").strip()
            text = (body.text or "").strip()
            if not to_uid:
                return JSONResponse(status_code=400, content={"error": "to_local_user_id required"})
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_disabled", "hint": "Set federation_enabled: true in config/core.yml"})
            trusted: List[Any] = list(getattr(meta, "federation_trusted_instances", None) or [])
            if not federation_sender_instance_allowed(trusted, sender_instance_id):
                return JSONResponse(
                    status_code=403,
                    content={"error": "sender_instance_not_trusted", "hint": "Add instance_id to federation_trusted_instances or clear the list to allow any mutual friend."},
                )
            to_user = _get_user_by_id(to_uid)
            if not to_user:
                return JSONResponse(status_code=404, content={"error": "to_local_user_id not found"})
            require_acc = bool(getattr(meta, "federation_require_accepted_relationship", False))
            ok_deliver, deny_reason = inbound_federated_delivery_allowed(
                require_acc,
                (body.from_fid or "").strip(),
                sender_local_id,
                sender_instance_id,
                to_uid,
                to_user,
            )
            if not ok_deliver:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": deny_reason,
                        "hint": "Accept a federated friend request, configure user.yml friend with peer_instance_id, or set federation_require_accepted_relationship: false.",
                    },
                )
            e2e_on = bool(getattr(meta, "federation_e2e_enabled", False))
            e2e_req = bool(getattr(meta, "federation_e2e_require_encrypted", False))
            has_e2e = body.e2e is not None
            if e2e_req and not has_e2e:
                return JSONResponse(
                    status_code=400,
                    content={"error": "e2e_required", "hint": "Set federation_e2e_require_encrypted: false or send hc-e2e-v1 envelope."},
                )
            if has_e2e and not e2e_on:
                return JSONResponse(status_code=403, content={"error": "federation_e2e_disabled"})
            e2e_dict = None
            if has_e2e:
                e2e_dict = body.e2e.model_dump() if body.e2e else None
                ok_e, err_e = validate_e2e_envelope(e2e_dict)
                if not ok_e:
                    return JSONResponse(status_code=400, content={"error": "invalid_e2e_envelope", "detail": err_e})
                if body.images or body.audios or body.videos or body.file_links:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "e2e_media_not_supported", "hint": "Encrypted federated messages support text only in this version."},
                    )
            from_name = (body.from_display_name or "").strip() or sender_local_id
            extra_meta: dict = {
                "from_instance_id": sender_instance_id,
                "source": "federation",
                "from_fid": body.from_fid.strip(),
            }
            if body.client_message_id and str(body.client_message_id).strip():
                extra_meta["client_message_id"] = str(body.client_message_id).strip()
            store_text = "" if has_e2e else text
            msg_id = inbox_append(
                to_user_id=to_uid,
                from_user_id=sender_local_id,
                from_user_name=from_name,
                text=store_text,
                images=None if has_e2e else body.images,
                audios=None if has_e2e else body.audios,
                videos=None if has_e2e else body.videos,
                file_links=None if has_e2e else body.file_links,
                metadata=extra_meta,
                e2e=e2e_dict,
            )
            if not msg_id:
                return JSONResponse(status_code=500, content={"error": "Failed to store message"})
            try:
                if hasattr(core, "deliver_to_user"):
                    await core.deliver_to_user(
                        to_uid,
                        "" if has_e2e else (text or "(no text)"),
                        images=None if has_e2e else body.images,
                        audios=None if has_e2e else body.audios,
                        videos=None if has_e2e else body.videos,
                        source="user_message",
                        from_friend=from_name,
                        from_user_id=sender_local_id,
                        e2e_encrypted=bool(has_e2e),
                    )
            except Exception as e:
                logger.debug("federation user-message: deliver_to_user failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True, "message_id": msg_id})
        except Exception as e:
            logger.warning("federation user-message POST failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return post_federation_user_message


class FederatedFriendRequestInbound(BaseModel):
    from_fid: str = Field(..., description="Requester FID (user_id@instance_id)")
    to_local_user_id: str = Field(..., description="Target local user on this Core")
    message: Optional[str] = Field(None, description="Optional note")
    from_display_name: Optional[str] = None


class FederatedFriendRelationshipReciprocal(BaseModel):
    """Peer Core installs reciprocal accepted row so return messaging works."""

    from_fid: str = Field(..., description="The user@instance who may message to_local_user_id")
    to_local_user_id: str = Field(..., description="Local user on this Core who is allowed to receive from from_fid")


def get_federation_friend_request_post_handler(core):
    """POST /api/federation/friend-request — inbound friend request from peer Core."""

    async def post_federation_friend_request(
        body: FederatedFriendRequestInbound,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            parsed = parse_fid(body.from_fid or "")
            if not parsed:
                return JSONResponse(status_code=400, content={"error": "Invalid from_fid"})
            _sender_local, sender_instance_id = parsed
            to_uid = (body.to_local_user_id or "").strip()
            if not to_uid:
                return JSONResponse(status_code=400, content={"error": "to_local_user_id required"})
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_disabled"})
            trusted: List[Any] = list(getattr(meta, "federation_trusted_instances", None) or [])
            if not federation_sender_instance_allowed(trusted, sender_instance_id):
                return JSONResponse(status_code=403, content={"error": "sender_instance_not_trusted"})
            if not _get_user_by_id(to_uid):
                return JSONResponse(status_code=404, content={"error": "to_local_user_id not found"})
            req_id, tag = create_or_refresh_pending(
                (body.from_fid or "").strip(),
                to_uid,
                body.message,
            )
            if tag == "blocked":
                return JSONResponse(status_code=403, content={"error": "relationship_blocked"})
            if tag == "already_accepted":
                return JSONResponse(status_code=200, content={"ok": True, "request_id": req_id, "status": "already_accepted"})
            if tag == "already_pending":
                return JSONResponse(status_code=200, content={"ok": True, "request_id": req_id, "status": "already_pending"})
            if tag == "error" or not req_id:
                return JSONResponse(status_code=500, content={"error": "Failed to store request"})
            from_name = (body.from_display_name or "").strip() or _sender_local
            try:
                if hasattr(core, "deliver_to_user"):
                    note = (body.message or "").strip() or "wants to connect (federated)."
                    await core.deliver_to_user(
                        to_uid,
                        f"{from_name} ({body.from_fid.strip()}) {note}",
                        source="federated_friend_request",
                        from_friend=from_name,
                    )
            except Exception as e:
                logger.debug("federation friend-request: deliver_to_user failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True, "request_id": req_id, "status": tag})
        except Exception as e:
            logger.warning("federation friend-request POST failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return post_federation_friend_request


def get_federation_friend_relationship_reciprocal_post_handler(core):  # noqa: ARG001
    """POST /api/federation/friend-relationship-reciprocal — peer callback after accept."""

    async def post_reciprocal(
        body: FederatedFriendRelationshipReciprocal,
        _: None = Depends(auth.verify_inbound_auth),
    ):
        try:
            parsed = parse_fid(body.from_fid or "")
            if not parsed:
                return JSONResponse(status_code=400, content={"error": "Invalid from_fid"})
            _sl, sender_instance_id = parsed
            to_uid = (body.to_local_user_id or "").strip()
            if not to_uid:
                return JSONResponse(status_code=400, content={"error": "to_local_user_id required"})
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_disabled"})
            trusted: List[Any] = list(getattr(meta, "federation_trusted_instances", None) or [])
            if not federation_sender_instance_allowed(trusted, sender_instance_id):
                return JSONResponse(status_code=403, content={"error": "sender_instance_not_trusted"})
            if not _get_user_by_id(to_uid):
                return JSONResponse(status_code=404, content={"error": "to_local_user_id not found"})
            if not upsert_reciprocal_accepted((body.from_fid or "").strip(), to_uid):
                return JSONResponse(status_code=500, content={"error": "Failed to update relationship"})
            return JSONResponse(status_code=200, content={"ok": True})
        except Exception as e:
            logger.warning("federation reciprocal POST failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return post_reciprocal
