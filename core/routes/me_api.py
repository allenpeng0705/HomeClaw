"""
Me API: avatar upload/read, add/update/delete AI friends, set identity content.
Auth: Bearer token (Companion session). Design: docs_design/UserThumbnailAndFriendIconsDesign.md.
"""
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Depends, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from base.util import Util
from core.avatar_store import (
    get_friend_avatar_path,
    get_user_avatar_path,
    save_friend_avatar,
    save_user_avatar,
)
from core.routes.companion_auth import get_companion_token_user
from base.base import User
from base.workspace import write_friend_identity_file


def get_api_me_avatar_get_handler(core):  # noqa: ARG001
    """GET /api/me/avatar. Returns current user's avatar image or 404."""

    async def handler(
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            path = get_user_avatar_path(user_id)
            if not path.is_file():
                return JSONResponse(status_code=404, content={"detail": "No avatar"})
            suffix = (path.suffix or "").strip().lower()
            media_type = "image/png" if suffix == ".png" else "image/jpeg"
            return FileResponse(path, media_type=media_type)
        except Exception as e:
            logger.debug("GET /api/me/avatar failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_password_put_handler(core):  # noqa: ARG001
    """PUT /api/me/password. Body: { old_password, new_password }. Verify current password, then update. 400 on wrong old or invalid new."""

    async def handler(
        request: Request,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, user = token_user
            body = {}
            try:
                if (request.headers.get("content-type") or "").strip().lower().startswith("application/json"):
                    raw = await request.json()
                    if isinstance(raw, dict):
                        body = raw
            except Exception:
                pass
            raw_old = body.get("old_password")
            old_password = (str(raw_old).strip() if raw_old is not None else "") or ""
            raw_new = body.get("new_password")
            new_password = (str(raw_new).strip() if raw_new is not None else "") if raw_new is not None else ""
            stored = (getattr(user, "password", None) or "").strip()
            if stored != old_password:
                return JSONResponse(status_code=400, content={"detail": "Current password is incorrect"})
            if not new_password:
                return JSONResponse(status_code=400, content={"detail": "New password cannot be empty"})
            if len(new_password) > 512:
                return JSONResponse(status_code=400, content={"detail": "New password too long"})
            util = Util()
            if not util.update_user_password(user_id, new_password):
                return JSONResponse(status_code=500, content={"detail": "Failed to update password"})
            return JSONResponse(content={"ok": True})
        except Exception as e:
            logger.debug("PUT /api/me/password failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_avatar_put_handler(core):  # noqa: ARG001
    """PUT /api/me/avatar. Upload current user's profile picture (multipart file)."""

    async def handler(
        token_user: tuple = Depends(get_companion_token_user),
        file: UploadFile = File(..., description="Image file (PNG/JPEG, max 1MB)"),
    ):
        try:
            user_id, _ = token_user
            content = await file.read()
            if not content:
                return JSONResponse(status_code=400, content={"detail": "No image data"})
            if len(content) > 1024 * 1024:
                return JSONResponse(status_code=400, content={"detail": "Image too large (max 1MB)"})
            content_type = getattr(file, "content_type", None)
            if save_user_avatar(user_id, content, content_type):
                return JSONResponse(content={"ok": True})
            return JSONResponse(status_code=500, content={"detail": "Save failed"})
        except Exception as e:
            logger.debug("PUT /api/me/avatar failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_users_avatar_handler(core):  # noqa: ARG001
    """GET /api/users/{user_id}/avatar. Returns that user's avatar (for friend list). 404 if none."""

    async def handler(
        user_id: str,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            path = get_user_avatar_path(user_id)
            if not path.is_file():
                return JSONResponse(status_code=404, content={"detail": "No avatar"})
            suffix = (path.suffix or "").strip().lower()
            media_type = "image/png" if suffix == ".png" else "image/jpeg"
            return FileResponse(path, media_type=media_type)
        except Exception as e:
            logger.debug("GET /api/users/.../avatar failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_friends_post_handler(core):  # noqa: ARG001
    """POST /api/me/friends. Body: { name, relation?, who?, identity_filename? }. Add custom AI friend to user.yml."""

    async def handler(
        request: Request,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            try:
                body = await request.json()
            except Exception:
                return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})
            if not isinstance(body, dict):
                return JSONResponse(status_code=400, content={"detail": "JSON object required"})
            name = (body.get("name") or "").strip()
            if not name:
                return JSONResponse(status_code=400, content={"detail": "name required"})
            relation = body.get("relation")
            who = body.get("who") if isinstance(body.get("who"), dict) else None
            identity_filename = (body.get("identity_filename") or "identity.md").strip() or "identity.md"
            if Util().add_ai_friend(user_id, name, relation=relation, who=who, identity_filename=identity_filename):
                return JSONResponse(content={"ok": True, "friend_id": name})
            return JSONResponse(status_code=400, content={"detail": "Duplicate name or invalid"})
        except Exception as e:
            logger.debug("POST /api/me/friends failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_friends_patch_handler(core):  # noqa: ARG001
    """PATCH /api/me/friends/{friend_id}. Body: { name?, relation?, who? }. Update AI friend."""

    async def handler(
        friend_id: str,
        request: Request,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            fid = (friend_id or "").strip()
            if not fid or fid.lower() == "homeclaw":
                return JSONResponse(status_code=400, content={"detail": "Cannot update HomeClaw"})
            try:
                body = await request.json()
            except Exception:
                body = {}
            if not isinstance(body, dict):
                body = {}
            name = (body.get("name") or "").strip() or None
            relation = body.get("relation")
            who = body.get("who") if isinstance(body.get("who"), dict) else None
            identity_filename = (body.get("identity_filename") or "").strip() or None
            preset = (body.get("preset") or "").strip() or None
            if Util().update_ai_friend(user_id, fid, name=name, relation=relation, who=who, identity_filename=identity_filename, preset=preset):
                return JSONResponse(content={"ok": True})
            return JSONResponse(status_code=404, content={"detail": "Friend not found or not AI"})
        except Exception as e:
            logger.debug("PATCH /api/me/friends/... failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_friends_delete_handler(core):  # noqa: ARG001
    """DELETE /api/me/friends/{friend_id}. Remove AI friend (friend_id=name) or user friend (friend_id=other user's id). Cannot remove HomeClaw."""

    async def handler(
        friend_id: str,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            fid = (friend_id or "").strip()
            if not fid:
                return JSONResponse(status_code=400, content={"detail": "friend_id required"})
            if Util().remove_ai_friend(user_id, fid):
                return JSONResponse(content={"ok": True})
            if Util().remove_user_friend(user_id, fid):
                return JSONResponse(content={"ok": True})
            return JSONResponse(status_code=400, content={"detail": "Not found or cannot remove HomeClaw"})
        except Exception as e:
            logger.debug("DELETE /api/me/friends/... failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_friends_identity_put_handler(core):  # noqa: ARG001
    """PUT /api/me/friends/{friend_id}/identity. Body: { content: "..." } or raw text. Writes identity file."""

    async def handler(
        friend_id: str,
        request: Request,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            fid = (friend_id or "").strip()
            if not fid:
                return JSONResponse(status_code=400, content={"detail": "friend_id required"})
            try:
                body = await request.body()
                text = body.decode("utf-8", errors="replace")
                if text.strip().startswith("{"):
                    import json
                    try:
                        data = json.loads(text)
                        if isinstance(data, dict):
                            text = (data.get("content") or "").strip()
                    except Exception:
                        pass
            except Exception:
                text = ""
            try:
                meta = Util().get_core_metadata()
                homeclaw_root = (getattr(meta, "homeclaw_root", None) or "").strip() if meta else ""
            except Exception:
                homeclaw_root = ""
            if not homeclaw_root:
                return JSONResponse(status_code=503, content={"detail": "homeclaw_root not configured"})
            if write_friend_identity_file(homeclaw_root, user_id, fid, text or "", "identity.md"):
                return JSONResponse(content={"ok": True})
            return JSONResponse(status_code=500, content={"detail": "Write failed"})
        except Exception as e:
            logger.debug("PUT /api/me/friends/.../identity failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_friends_avatar_get_handler(core):  # noqa: ARG001
    """GET /api/me/friends/{friend_id}/avatar. Returns avatar for that (custom AI) friend. 404 if none."""

    async def handler(
        friend_id: str,
        token_user: tuple = Depends(get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            path = get_friend_avatar_path(user_id, friend_id)
            if not path.is_file():
                return JSONResponse(status_code=404, content={"detail": "No avatar"})
            suffix = (path.suffix or "").strip().lower()
            media_type = "image/png" if suffix == ".png" else "image/jpeg"
            return FileResponse(path, media_type=media_type)
        except Exception as e:
            logger.debug("GET /api/me/friends/.../avatar failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler


def get_api_me_friends_avatar_put_handler(core):  # noqa: ARG001
    """PUT /api/me/friends/{friend_id}/avatar. Upload avatar for that AI friend."""

    async def handler(
        friend_id: str,
        token_user: tuple = Depends(get_companion_token_user),
        file: Optional[UploadFile] = File(None),
    ):
        try:
            user_id, _ = token_user
            fid = (friend_id or "").strip()
            if not fid:
                return JSONResponse(status_code=400, content={"detail": "friend_id required"})
            if not file or not file.filename:
                return JSONResponse(status_code=400, content={"detail": "No file"})
            content = await file.read()
            if len(content) > 1024 * 1024:
                return JSONResponse(status_code=400, content={"detail": "Image too large (max 1MB)"})
            if save_friend_avatar(user_id, fid, content, getattr(file, "content_type", None)):
                return JSONResponse(content={"ok": True})
            return JSONResponse(status_code=500, content={"detail": "Save failed"})
        except Exception as e:
            logger.debug("PUT /api/me/friends/.../avatar failed: {}", e)
            return JSONResponse(status_code=500, content={"detail": "Failed"})

    return handler
