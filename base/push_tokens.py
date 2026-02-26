"""
Push token store for Companion (FCM). Persists user_id -> list of {token, platform, updated_at}
under database/push_tokens.json so Core can send remote push when deliver_to_user runs.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from base.util import Util


def _file_path() -> Path:
    return Path(Util().data_path()) / "push_tokens.json"


def load_push_tokens() -> Dict[str, List[Dict[str, Any]]]:
    """Load user_id -> list of {token, platform, updated_at}. Returns {} on error or missing."""
    path = _file_path()
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as e:
        logger.debug("push_tokens load failed: {}", e)
        return {}


def save_push_tokens(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Persist user_id -> list of token entries."""
    path = _file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("push_tokens save failed: {}", e)


def register_push_token(user_id: str, token: str, platform: str = "android") -> None:
    """Register or update a push token for user_id. Replaces existing entry with same token."""
    user_id = (user_id or "").strip() or "companion"
    token = (token or "").strip()
    if not token:
        return
    platform = (platform or "android").strip().lower() or "android"
    if platform not in ("android", "ios"):
        platform = "android"
    data = load_push_tokens()
    from datetime import datetime
    entry = {"token": token, "platform": platform, "updated_at": datetime.utcnow().isoformat() + "Z"}
    entries = data.get(user_id) or []
    entries = [e for e in entries if isinstance(e, dict) and (e.get("token") or "").strip() != token]
    entries.append(entry)
    data[user_id] = entries
    save_push_tokens(data)


def unregister_push_token(user_id: str, token: Optional[str] = None) -> None:
    """Remove token(s) for user_id. If token is None, remove all for that user."""
    user_id = (user_id or "").strip() or "companion"
    data = load_push_tokens()
    if user_id not in data:
        return
    if token:
        token = token.strip()
        entries = [e for e in data[user_id] if isinstance(e, dict) and (e.get("token") or "").strip() != token]
    else:
        entries = []
    if entries:
        data[user_id] = entries
    else:
        del data[user_id]
    save_push_tokens(data)


def get_tokens_for_user(user_id: str) -> List[Dict[str, Any]]:
    """Return list of {token, platform, updated_at} for user_id."""
    user_id = (user_id or "").strip() or "companion"
    data = load_push_tokens()
    entries = data.get(user_id) or []
    return [e for e in entries if isinstance(e, dict) and (e.get("token") or "").strip()]
