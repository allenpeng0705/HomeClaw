"""
Friend request store: pending requests (from_user_id, to_user_id, message?, created_at).
Stored under data_path()/friend_requests.json. Used by Add Friend flow: send, list, accept, reject.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from base.util import Util


def _store_path() -> Path:
    """Path to friend_requests.json. Never raises."""
    try:
        return Path(Util().data_path()) / "friend_requests.json"
    except Exception:
        return Path("friend_requests.json")


def _load_all() -> List[Dict[str, Any]]:
    """Load all requests (pending and resolved). Never raises."""
    try:
        path = _store_path()
        if not path.is_file():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("requests") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return items
    except Exception as e:
        logger.debug("friend_requests load failed: {}", e)
        return []


def _save_all(items: List[Dict[str, Any]]) -> bool:
    """Save list of requests. Never raises; returns False on failure."""
    try:
        path = _store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"requests": items}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("friend_requests save failed: {}", e)
        return False


def create_request(from_user_id: str, to_user_id: str, message: Optional[str] = None) -> Optional[str]:
    """
    Create a pending friend request. Returns request_id or None.
    Does not check if already friends or duplicate request; caller should check.
    """
    try:
        from_user_id = (from_user_id or "").strip()
        to_user_id = (to_user_id or "").strip()
        if not from_user_id or not to_user_id or from_user_id == to_user_id:
            return None
        items = _load_all()
        request_id = str(uuid.uuid4())
        entry = {
            "id": request_id,
            "from_user_id": from_user_id,
            "to_user_id": to_user_id,
            "message": (message or "").strip() or None,
            "status": "pending",
            "created_at": time.time(),
        }
        items.append(entry)
        if _save_all(items):
            return request_id
        return None
    except Exception as e:
        logger.warning("friend_requests create failed: {}", e)
        return None


def get_pending_for_user(to_user_id: str) -> List[Dict[str, Any]]:
    """Return pending requests where to_user_id == to_user_id. Newest first."""
    try:
        to_user_id = (to_user_id or "").strip()
        if not to_user_id:
            return []
        items = _load_all()
        out = [
            {k: v for k, v in item.items() if k in ("id", "from_user_id", "to_user_id", "message", "created_at")}
            for item in items
            if isinstance(item, dict)
            and (item.get("to_user_id") or "").strip() == to_user_id
            and (item.get("status") or "pending") == "pending"
        ]
        out.sort(key=lambda x: (x.get("created_at") or 0), reverse=True)
        return out
    except Exception as e:
        logger.debug("friend_requests get_pending failed: {}", e)
        return []


def find_request(request_id: Optional[str] = None, from_user_id: Optional[str] = None, to_user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Find one request by id or by (from_user_id, to_user_id). Returns full entry or None."""
    try:
        items = _load_all()
        for item in items:
            if not isinstance(item, dict):
                continue
            if request_id and (item.get("id") or "").strip() == (request_id or "").strip():
                return item
            if from_user_id and to_user_id:
                if (item.get("from_user_id") or "").strip() == (from_user_id or "").strip() and (item.get("to_user_id") or "").strip() == (to_user_id or "").strip():
                    return item
        return None
    except Exception:
        return None


def set_status(request_id: str, status: str) -> bool:
    """Set request status to accepted or rejected. Returns True if updated."""
    try:
        request_id = (request_id or "").strip()
        status = (status or "").strip().lower()
        if status not in ("accepted", "rejected"):
            return False
        items = _load_all()
        for i, item in enumerate(items):
            if isinstance(item, dict) and (item.get("id") or "").strip() == request_id:
                items[i] = {**item, "status": status}
                return _save_all(items)
        return False
    except Exception as e:
        logger.warning("friend_requests set_status failed: {}", e)
        return False


def has_pending(from_user_id: str, to_user_id: str) -> bool:
    """True if there is a pending request from from_user_id to to_user_id."""
    entry = find_request(from_user_id=from_user_id, to_user_id=to_user_id)
    return entry is not None and (entry.get("status") or "pending") == "pending"
