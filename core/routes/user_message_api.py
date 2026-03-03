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
from base.util import Util

from core import auth
from core.user_inbox import append_message as inbox_append, get_messages as inbox_get_messages


def _get_user_by_id(user_id: str) -> Optional[User]:
    users = Util().get_users() or []
    uid = (user_id or "").strip()
    for u in users:
        if (getattr(u, "id", None) or "").strip() == uid or (getattr(u, "name", None) or "").strip() == uid:
            return u
    return None


def _sender_has_recipient_as_user_friend(from_user: User, to_user_id: str) -> bool:
    """True if from_user has to_user_id as a friend with type user (and user_id match)."""
    friends = getattr(from_user, "friends", None) or []
    to_id = (to_user_id or "").strip()
    for f in friends:
        if getattr(f, "type", None) and str(getattr(f, "type", "")).strip().lower() == "user":
            uid = (getattr(f, "user_id", None) or "").strip()
            if uid == to_id:
                return True
    return False


class UserMessageRequest(BaseModel):
    from_user_id: str = Field(..., description="Sender user id (must exist in user.yml)")
    to_user_id: str = Field(..., description="Recipient user id")
    text: str = Field("", description="Message text")
    images: Optional[list] = None  # data URLs (data:image/...;base64,...) or file paths Core can read; forwarded to recipient via WebSocket + stored in inbox
    audios: Optional[list] = None  # voice/audio: data URLs (data:audio/...;base64,...) or file paths; push-to-talk; forwarded to recipient via WebSocket + stored in inbox
    videos: Optional[list] = None  # short video (e.g. 10s): data URLs (data:video/...;base64,...) or file paths; forwarded to recipient via WebSocket + stored in inbox
    file_links: Optional[list] = None  # URLs or paths; stored in inbox for recipient


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
            to_user = _get_user_by_id(to_user_id)
            if not from_user:
                return JSONResponse(status_code=403, content={"error": "from_user_id not found"})
            if not to_user:
                return JSONResponse(status_code=404, content={"error": "to_user_id not found"})
            if not _sender_has_recipient_as_user_friend(from_user, to_user_id):
                return JSONResponse(
                    status_code=403,
                    content={"error": "Recipient is not a user-type friend of the sender. Add them in user.yml (type: user, user_id: <id>)."},
                )
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
