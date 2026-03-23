"""
Companion APIs for cross-instance federated friend requests (Bearer session).

Sends POST to peer Core /api/federation/friend-request; lists and accepts local inbound rows in SQLite.
"""

from typing import Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.federation import format_fid, parse_fid
from base.peer_registry import find_peer_by_instance_id, load_instance_identity, post_federation_json_sync, resolve_peer_api_key
from base.util import Util

from core.federated_friendships_store import get_by_id_for_recipient, list_pending_for_local_user, set_state_by_id
from core.routes import companion_auth


class FederatedFriendRequestSendBody(BaseModel):
    to_user_id: str = Field(..., description="Target user's local id on the peer instance")
    peer_instance_id: str = Field(..., description="Peer Core instance_id (peers.yml)")
    message: Optional[str] = Field(None, description="Optional note")


class FederatedFriendRequestIdBody(BaseModel):
    request_id: str = Field(..., description="Row id from GET /api/federated-friend-requests")


def get_api_federated_friend_request_send_handler(core):  # noqa: ARG001
    """POST /api/federated-friend-request — Bearer; forward to remote Core."""

    async def send_req(
        body: FederatedFriendRequestSendBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            from_uid, from_user = token_user
            from_uid = (from_uid or "").strip()
            to_uid = (body.to_user_id or "").strip()
            peer_inst = (body.peer_instance_id or "").strip()
            if not from_uid or not to_uid or not peer_inst:
                return JSONResponse(status_code=400, content={"error": "to_user_id and peer_instance_id required"})
            meta = Util().get_core_metadata()
            if not bool(getattr(meta, "federation_enabled", False)):
                return JSONResponse(status_code=403, content={"error": "federation_disabled"})
            ident = load_instance_identity()
            my_iid = (ident.get("instance_id") or "").strip()
            if not my_iid:
                return JSONResponse(status_code=503, content={"error": "Local instance_id missing"})
            peer = find_peer_by_instance_id(peer_inst)
            if not peer:
                return JSONResponse(status_code=404, content={"error": "peer_not_configured"})
            base_url = (peer.get("base_url") or "").strip().rstrip("/")
            if not base_url:
                return JSONResponse(status_code=502, content={"error": "peer base_url missing"})
            api_key = resolve_peer_api_key(peer)
            from_name = (getattr(from_user, "name", None) or from_uid or "").strip()
            from_fid = format_fid(from_uid, my_iid)
            payload = {
                "from_fid": from_fid,
                "to_local_user_id": to_uid,
                "message": (body.message or "").strip() or None,
                "from_display_name": from_name,
            }
            remote = post_federation_json_sync(base_url, "/api/federation/friend-request", payload, api_key=api_key)
            sc = int(remote.get("status_code") or 0)
            if remote.get("ok") and sc == 200:
                return JSONResponse(
                    status_code=200,
                    content={
                        "ok": True,
                        "remote": {k: remote.get(k) for k in ("request_id", "status") if remote.get(k) is not None},
                    },
                )
            err = (remote.get("error") or "forward_failed") if isinstance(remote, dict) else "forward_failed"
            return JSONResponse(status_code=sc if sc else 502, content={"error": err})
        except Exception as e:
            logger.warning("POST /api/federated-friend-request failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return send_req


def get_api_federated_friend_requests_list_handler(core):  # noqa: ARG001
    """GET /api/federated-friend-requests — Bearer; pending inbound federated requests."""

    async def list_req(
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            rows = list_pending_for_local_user(user_id)
            return JSONResponse(content={"requests": rows})
        except Exception as e:
            logger.warning("GET /api/federated-friend-requests failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return list_req


def get_api_federated_friend_request_accept_handler(core):
    """POST /api/federated-friend-request/accept — Bearer."""

    async def accept(
        body: FederatedFriendRequestIdBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            rid = (body.request_id or "").strip()
            if not rid:
                return JSONResponse(status_code=400, content={"error": "request_id required"})
            row = get_by_id_for_recipient(rid, user_id)
            if not row or (row.get("state") or "").strip().lower() != "pending":
                return JSONResponse(status_code=404, content={"error": "Request not found or not pending"})
            updated = set_state_by_id(rid, user_id, "accepted")
            if not updated:
                return JSONResponse(status_code=500, content={"error": "Failed to accept"})
            from_fid = (updated.get("from_fid") or "").strip()
            parsed = parse_fid(from_fid)
            if parsed:
                requester_local, requester_inst = parsed
                peer = find_peer_by_instance_id(requester_inst)
                if peer:
                    base_url = (peer.get("base_url") or "").strip().rstrip("/")
                    api_key = resolve_peer_api_key(peer)
                    ident = load_instance_identity()
                    my_iid = (ident.get("instance_id") or "").strip()
                    if my_iid and base_url:
                        recip_fid = format_fid(user_id, my_iid)
                        sync_body = {"from_fid": recip_fid, "to_local_user_id": requester_local}
                        sync_res = post_federation_json_sync(
                            base_url,
                            "/api/federation/friend-relationship-reciprocal",
                            sync_body,
                            api_key=api_key,
                        )
                        if not sync_res.get("ok"):
                            logger.warning("federated accept: reciprocal sync failed: {}", sync_res)
                else:
                    logger.warning("federated accept: no peer row for instance {}", requester_inst)
            # Do not call local deliver_to_user(requester_local_id) here:
            # requester_local_id belongs to the remote Core and may collide with a local user id.
            return JSONResponse(status_code=200, content={"ok": True})
        except Exception as e:
            logger.warning("POST /api/federated-friend-request/accept failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return accept


def get_api_federated_friend_request_reject_handler(core):  # noqa: ARG001
    """POST /api/federated-friend-request/reject — Bearer."""

    async def reject(
        body: FederatedFriendRequestIdBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            rid = (body.request_id or "").strip()
            if not rid:
                return JSONResponse(status_code=400, content={"error": "request_id required"})
            row = get_by_id_for_recipient(rid, user_id)
            if not row or (row.get("state") or "").strip().lower() != "pending":
                return JSONResponse(status_code=404, content={"error": "Request not found or not pending"})
            if not set_state_by_id(rid, user_id, "rejected"):
                return JSONResponse(status_code=500, content={"error": "Failed to reject"})
            return JSONResponse(status_code=200, content={"ok": True})
        except Exception as e:
            logger.warning("POST /api/federated-friend-request/reject failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return reject
