"""
Chat history API: GET /api/chat-history for Companion to load Core↔user (AI) conversation.
When the app was offline, Core still stored the reply in chatDB; this endpoint lets the app fetch it so the "inbox" works for Core→user messages too.
Auth: Bearer token. Returns messages (role, content, timestamp) for (user_id, friend_id).
"""

from typing import Optional

from fastapi import Depends
from fastapi.responses import JSONResponse
from loguru import logger

from core.routes import companion_auth


def get_api_chat_history_handler(core):
    """GET /api/chat-history. Bearer required. Query: friend_id, limit (optional). user_id from token. Returns messages from Core's chatDB for that (user_id, friend_id)."""

    async def get_chat_history(
        friend_id: Optional[str] = None,
        limit: int = 100,
        token_user: tuple = Depends(companion_auth.get_companion_token_user),
    ):
        try:
            user_id, _ = token_user
            user_id = (user_id or "").strip()
            friend_id = (friend_id or "HomeClaw").strip() or "HomeClaw"
            limit = max(1, min(500, int(limit) if limit is not None else 100))
            sessions = core.get_sessions(user_id=user_id, friend_id=friend_id, num_rounds=1, fetch_all=True)
            if not sessions or not isinstance(sessions, list):
                return JSONResponse(content={"messages": []})
            row = sessions[0]
            if not isinstance(row, dict):
                return JSONResponse(content={"messages": []})
            app_id = (row.get("app_id") or "homeclaw").strip() or "homeclaw"
            user_name = (row.get("user_name") or user_id or "").strip() or user_id
            session_id = (row.get("session_id") or "").strip()
            if not session_id:
                return JSONResponse(content={"messages": []})
            transcript = core.get_session_transcript(
                app_id=app_id,
                user_name=user_name,
                user_id=user_id,
                session_id=session_id,
                limit=limit,
                fetch_all=False,
            )
            if not isinstance(transcript, list):
                transcript = []
            return JSONResponse(content={"messages": transcript})
        except Exception as e:
            logger.warning("GET /api/chat-history failed: {}", e)
            return JSONResponse(status_code=500, content={"error": "Internal server error"})

    return get_chat_history
