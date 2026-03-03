"""
User-to-user message inbox: store and list messages for a user (single HomeClaw social network).
Messages are stored under data_path()/user_inbox/{user_id}.json. Used by POST /api/user-message and GET /api/user-inbox.
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from base.util import Util


def _inbox_dir() -> Path:
    """Return user_inbox directory under data path. Never raises (falls back to cwd/user_inbox on error)."""
    try:
        return Path(Util().data_path()) / "user_inbox"
    except Exception:
        return Path("user_inbox")


def _inbox_path(user_id: str) -> Path:
    """Safe path for one user's inbox file. Never raises."""
    try:
        raw = (user_id or "").strip() if user_id is not None else ""
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw)[:200] or "_unknown"
        return _inbox_dir() / f"{safe}.json"
    except Exception:
        return _inbox_dir() / "_unknown.json"


def append_message(
    to_user_id: str,
    from_user_id: str,
    from_user_name: str,
    text: str,
    images: Optional[List[str]] = None,
    audios: Optional[List[str]] = None,
    videos: Optional[List[str]] = None,
    file_links: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Append a user-to-user message to the recipient's inbox. Returns message id or None on failure.
    """
    try:
        to_user_id = (to_user_id or "").strip()
        from_user_id = (from_user_id or "").strip()
        from_user_name = (from_user_name or from_user_id or "").strip()
        text = (text or "").strip()
        if not to_user_id or not from_user_id:
            return None
        path = _inbox_path(to_user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        messages: List[Dict[str, Any]] = []
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    messages = data.get("messages") if isinstance(data, dict) else []
                    if not isinstance(messages, list):
                        messages = []
            except Exception as e:
                logger.debug("user_inbox: read failed {}: {}", path, e)
        msg_id = str(uuid.uuid4())
        entry = {
            "id": msg_id,
            "from_user_id": from_user_id,
            "from_user_name": from_user_name,
            "text": text,
            "created_at": time.time(),
        }
        if images and isinstance(images, (list, tuple)):
            entry["images"] = list(images)[:20]
        if audios and isinstance(audios, (list, tuple)):
            entry["audios"] = list(audios)[:10]
        if videos and isinstance(videos, (list, tuple)):
            entry["videos"] = list(videos)[:5]
        if file_links and isinstance(file_links, (list, tuple)):
            entry["file_links"] = list(file_links)[:20]
        messages.append(entry)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"messages": messages[-500:]}, f, ensure_ascii=False, indent=2)
        return msg_id
    except Exception as e:
        logger.warning("user_inbox append_message failed: {}", e)
        return None


def get_messages(
    user_id: str,
    limit: int = 50,
    after_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return the most recent messages for user_id (newest last). Optionally after_id to get only newer."""
    try:
        user_id = (user_id or "").strip()
        if not user_id:
            return []
        path = _inbox_path(user_id)
        if not path.is_file():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        messages = data.get("messages") if isinstance(data, dict) else []
        if not isinstance(messages, list):
            return []
        if after_id:
            seen = False
            filtered = []
            for m in messages:
                if not isinstance(m, dict):
                    continue
                if m.get("id") == after_id:
                    seen = True
                    continue
                if seen:
                    filtered.append(m)
            messages = filtered
        return messages[-limit:] if limit > 0 else messages
    except Exception as e:
        logger.debug("user_inbox get_messages failed: {}", e)
        return []
