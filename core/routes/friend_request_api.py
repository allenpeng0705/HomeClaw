"""
Friend request API: list users (for Add Friend), send request, list pending requests, accept, reject.
Auth: Bearer token (Companion session). Design: docs_design/FriendRequestAndOfflineMessaging.md.
"""

from typing import Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

from base.base import User
from base.util import Util

from core import companion_auth
from core.friend_requests_store import (
    create_request,
    find_request,
    get_pending_for_user,
    has_pending,
    set_status,
)


def _get_user_by_id(user_id: str) -> Optional[User]:
    users = Util().get_users() or []
    uid = (user_id or "").strip()
    for u in users:
        if (getattr(u, "id", None) or "").strip() == uid or (getattr(u, "name", None) or "").strip() == uid:
            return u
    return None


def _sender_has_recipient_as_user_friend(user: User, other_user_id: str) -> bool:
    friends = getattr(user, "friends", None) or []
    other_id = (other_user_id or "").strip()
    for f in friends:
        if getattr(f, "type", None) and str(getattr(f, "type", "")).strip().lower() == "user":
            if (getattr(f, "user_id", None) or "").strip() == other_id:
                return True
    return False


class FriendRequestSendBody(BaseModel):
    to_user_id: str = Field(..., description="Recipient user id")
    message: Optional[str] = Field(None, description="Optional short message with the request")


class FriendRequestAcceptRejectBody(BaseModel):
    request_id: str = Field(..., description="Id of the friend request to accept or reject")


def get_api_users_handler(core):  # noqa: ARG001
    """GET /api/users. Bearer required. Returns list of users (id, name) excluding the authenticated user."""

    async def get_users(
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            users = Util().get_users() or []
            out = []
            my_id = (user_id or "").strip()
            for u in users:
                uid = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if not uid or uid == my_id:
                    continue
                name = (getattr(u, "name", None) or uid or "").strip()
                out.append({"id": uid, "name": name})
            return JSONResponse(content={"users": out})
        except Exception as e:
            logger.warning("GET /api/users failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_users


def get_api_friend_request_post_handler(core):
    """POST /api/friend-request. Bearer required. from_user_id = token user; body has to_user_id, optional message."""

    async def post_friend_request(
        body: FriendRequestSendBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            from_user_id, from_user = token_user
            from_user_id = (from_user_id or "").strip()
            to_user_id = (body.to_user_id or "").strip()
            if not from_user_id or not to_user_id:
                return JSONResponse(status_code=400, content={"error": "to_user_id required"})
            if from_user_id == to_user_id:
                return JSONResponse(status_code=400, content={"error": "Cannot send request to yourself"})
            to_user = _get_user_by_id(to_user_id)
            if not to_user:
                return JSONResponse(status_code=404, content={"error": "User not found"})
            if _sender_has_recipient_as_user_friend(from_user, to_user_id):
                return JSONResponse(status_code=400, content={"error": "Already friends"})
            if has_pending(from_user_id, to_user_id):
                return JSONResponse(status_code=400, content={"error": "Friend request already sent"})
            request_id = create_request(from_user_id, to_user_id, body.message)
            if not request_id:
                return JSONResponse(status_code=500, content={"error": "Failed to create request"})
            from_name = (getattr(from_user, "name", None) or from_user_id or "").strip()
            try:
                if hasattr(core, "deliver_to_user"):
                    await core.deliver_to_user(
                        to_user_id,
                        f"{from_name} wants to add you as a friend.",
                        source="friend_request",
                        from_friend=from_name,
                    )
            except Exception as e:
                logger.debug("friend_request: deliver_to_user (push) failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True, "request_id": request_id})
        except Exception as e:
            logger.warning("POST /api/friend-request failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return post_friend_request


def get_api_friend_requests_handler(core):  # noqa: ARG001
    """GET /api/friend-requests. Bearer required. Returns pending requests for the authenticated user."""

    async def get_requests(
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            if not user_id:
                return JSONResponse(status_code=400, content={"error": "user_id required"})
            pending = get_pending_for_user(user_id)
            users = Util().get_users() or []
            by_id = {}
            for u in users:
                uid = (getattr(u, "id", None) or getattr(u, "name", None) or "").strip()
                if uid:
                    by_id[uid] = (getattr(u, "name", None) or uid or "").strip()
            for p in pending:
                fid = (p.get("from_user_id") or "").strip()
                p["from_user_name"] = by_id.get(fid) or fid
            return JSONResponse(content={"requests": pending})
        except Exception as e:
            logger.warning("GET /api/friend-requests failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_requests


def get_api_friend_request_accept_handler(core):
    """POST /api/friend-request/accept. Bearer required. Caller must be the to_user of the request."""

    async def accept(
        body: FriendRequestAcceptRejectBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            request_id = (body.request_id or "").strip()
            if not request_id:
                return JSONResponse(status_code=400, content={"error": "request_id required"})
            entry = find_request(request_id=request_id)
            if not entry:
                return JSONResponse(status_code=404, content={"error": "Request not found"})
            if (entry.get("status") or "pending") != "pending":
                return JSONResponse(status_code=400, content={"error": "Request already handled"})
            to_id = (entry.get("to_user_id") or "").strip()
            if to_id != user_id:
                return JSONResponse(status_code=403, content={"error": "Only the recipient can accept"})
            from_user_id = (entry.get("from_user_id") or "").strip()
            if not Util().add_friend_bidirectional(from_user_id, to_id):
                return JSONResponse(status_code=500, content={"error": "Failed to add friends"})
            set_status(request_id, "accepted")
            from_user = _get_user_by_id(from_user_id)
            from_name = (getattr(from_user, "name", None) or from_user_id or "").strip() if from_user else from_user_id
            to_name = (getattr(token_user[1], "name", None) or user_id or "").strip() if token_user[1] else user_id
            try:
                if hasattr(core, "deliver_to_user"):
                    await core.deliver_to_user(
                        from_user_id,
                        f"{to_name} accepted your friend request.",
                        source="friend_request",
                        from_friend=to_name,
                    )
            except Exception as e:
                logger.debug("friend_request accept: deliver_to_user failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True})
        except Exception as e:
            logger.warning("POST /api/friend-request/accept failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return accept


def get_api_friend_request_reject_handler(core):
    """POST /api/friend-request/reject. Bearer required. Caller must be the to_user of the request."""

    async def reject(
        body: FriendRequestAcceptRejectBody,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            request_id = (body.request_id or "").strip()
            if not request_id:
                return JSONResponse(status_code=400, content={"error": "request_id required"})
            entry = find_request(request_id=request_id)
            if not entry:
                return JSONResponse(status_code=404, content={"error": "Request not found"})
            if (entry.get("status") or "pending") != "pending":
                return JSONResponse(status_code=400, content={"error": "Request already handled"})
            to_id = (entry.get("to_user_id") or "").strip()
            if to_id != user_id:
                return JSONResponse(status_code=403, content={"error": "Only the recipient can reject"})
            from_user_id = (entry.get("from_user_id") or "").strip()
            set_status(request_id, "rejected")
            from_user = _get_user_by_id(from_user_id)
            from_name = (getattr(from_user, "name", None) or from_user_id or "").strip() if from_user else from_user_id
            to_name = (getattr(token_user[1], "name", None) or user_id or "").strip() if token_user[1] else user_id
            try:
                if hasattr(core, "deliver_to_user"):
                    await core.deliver_to_user(
                        from_user_id,
                        f"{to_name} declined your friend request.",
                        source="friend_request",
                        from_friend=to_name,
                    )
            except Exception as e:
                logger.debug("friend_request reject: deliver_to_user failed: {}", e)
            return JSONResponse(status_code=200, content={"ok": True})
        except Exception as e:
            logger.warning("POST /api/friend-request/reject failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return reject
