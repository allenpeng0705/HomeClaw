"""
Push token store for Companion (FCM). Persists user_id -> list of {token, platform, updated_at}
under database/push_tokens.json so Core can send remote push when deliver_to_user runs.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from base.util import Util


def _file_path() -> Optional[Path]:
    """Return path to push_tokens.json. Returns None on error (e.g. Util not ready). Never raises."""
    try:
        return Path(Util().data_path()) / "push_tokens.json"
    except Exception as e:
        logger.debug("push_tokens _file_path failed: {}", e)
        return None


def load_push_tokens() -> Dict[str, List[Dict[str, Any]]]:
    """Load user_id -> list of {token, platform, updated_at}. Returns {} on error or missing. Never raises."""
    try:
        path = _file_path()
        if path is None or not path.is_file():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        logger.debug("push_tokens load failed: {}", e)
        return {}


def save_push_tokens(data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Persist user_id -> list of token entries. Never raises (logs on failure)."""
    try:
        path = _file_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("push_tokens save failed: {}", e)


def register_push_token(user_id: str, token: str, platform: str = "android") -> None:
    """Register or update a push token for user_id. Replaces existing entry with same token. Never raises."""
    try:
        user_id = (user_id or "").strip() or "companion"
        token = str(token or "").strip()
        if not token:
            return
        platform = str(platform or "android").strip().lower() or "android"
        if platform not in ("android", "ios", "macos"):
            platform = "android"
        data = load_push_tokens()
        if not isinstance(data, dict):
            data = {}
        from datetime import datetime
        entry = {"token": token, "platform": platform, "updated_at": datetime.utcnow().isoformat() + "Z"}
        entries = data.get(user_id)
        if not isinstance(entries, list):
            entries = []
        entries = [e for e in entries if isinstance(e, dict) and str(e.get("token") or "").strip() != token]
        entries.append(entry)
        data[user_id] = entries
        save_push_tokens(data)
    except Exception as e:
        logger.debug("push_tokens register failed: {}", e)


def unregister_push_token(user_id: str, token: Optional[str] = None) -> None:
    """Remove token(s) for user_id. If token is None, remove all for that user. Never raises."""
    try:
        user_id = (user_id or "").strip() or "companion"
        data = load_push_tokens()
        if not isinstance(data, dict) or user_id not in data:
            return
        entries = data.get(user_id)
        if not isinstance(entries, list):
            entries = []
        if token is not None and str(token).strip():
            token_s = str(token).strip()
            entries = [e for e in entries if isinstance(e, dict) and str(e.get("token") or "").strip() != token_s]
        else:
            entries = []
        if entries:
            data[user_id] = entries
        else:
            del data[user_id]
        save_push_tokens(data)
    except Exception as e:
        logger.debug("push_tokens unregister failed: {}", e)


def get_tokens_for_user(user_id: str) -> List[Dict[str, Any]]:
    """Return list of {token, platform, updated_at} for user_id. Never raises; returns [] on error."""
    try:
        user_id = (user_id or "").strip() or "companion"
        data = load_push_tokens()
        if not isinstance(data, dict):
            return []
        entries = data.get(user_id)
        if not isinstance(entries, list):
            return []
        return [e for e in entries if isinstance(e, dict) and str(e.get("token") or "").strip()]
    except Exception as e:
        logger.debug("push_tokens get_tokens_for_user failed: {}", e)
        return []
