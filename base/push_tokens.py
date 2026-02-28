"""
Push token store for Companion (FCM/APNs). Persists (user_id, device_id) -> {token, platform, updated_at}
under database/push_tokens.json so Core can send remote push when deliver_to_user runs.
When the same user_id and device_id register again, the token is updated (not added); one device = one token per user.
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


def load_push_tokens() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Load user_id -> { device_id: { token, platform, updated_at } }.
    Migrates old format (user_id -> list of entries) to new format on read.
    Returns {} on error or missing. Never raises.
    """
    try:
        path = _file_path()
        if path is None or not path.is_file():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for uid, raw in data.items():
            if not isinstance(raw, dict):
                if isinstance(raw, list):
                    for i, e in enumerate(raw):
                        if isinstance(e, dict) and str(e.get("token") or "").strip():
                            dev_id = str(e.get("device_id") or "").strip() or f"_legacy_{i}"
                            if uid not in out:
                                out[uid] = {}
                            out[uid][dev_id] = {
                                "token": str(e.get("token") or "").strip(),
                                "platform": str(e.get("platform") or "android").strip().lower() or "android",
                                "updated_at": str(e.get("updated_at") or ""),
                            }
                continue
            out[uid] = {}
            for dev_id, entry in raw.items():
                if isinstance(entry, dict) and str(entry.get("token") or "").strip():
                    out[uid][dev_id] = {
                        "token": str(entry.get("token") or "").strip(),
                        "platform": str(entry.get("platform") or "android").strip().lower() or "android",
                        "updated_at": str(entry.get("updated_at") or ""),
                    }
        return out
    except Exception as e:
        logger.debug("push_tokens load failed: {}", e)
        return {}


def save_push_tokens(data: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    """Persist user_id -> { device_id: { token, platform, updated_at } }. Never raises (logs on failure)."""
    try:
        path = _file_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("push_tokens save failed: {}", e)


def register_push_token(
    user_id: str,
    token: str,
    platform: str = "android",
    device_id: Optional[str] = None,
) -> None:
    """
    Register or update push token for (user_id, device_id).
    If the same user_id and device_id already exist, the token is updated to the latest (not added).
    device_id empty/None is treated as a single default device (one entry per user for legacy clients).
    Never raises.
    """
    try:
        user_id = (user_id or "").strip() or "companion"
        token = str(token or "").strip()
        if not token:
            return
        platform = str(platform or "android").strip().lower() or "android"
        if platform not in ("android", "ios", "macos"):
            platform = "android"
        device_id = (str(device_id or "").strip() or "") or "_default"
        from datetime import datetime
        entry = {"token": token, "platform": platform, "updated_at": datetime.utcnow().isoformat() + "Z"}
        data = load_push_tokens()
        if not isinstance(data, dict):
            data = {}
        if user_id not in data:
            data[user_id] = {}
        data[user_id][device_id] = entry
        save_push_tokens(data)
    except Exception as e:
        logger.debug("push_tokens register failed: {}", e)


def unregister_push_token(
    user_id: str,
    token: Optional[str] = None,
    device_id: Optional[str] = None,
) -> None:
    """
    Remove token(s) for user_id.
    If device_id is set, remove that device only.
    If token is set, remove the entry with that token (any device).
    If both None, remove all devices for that user.
    Never raises.
    """
    try:
        user_id = (user_id or "").strip() or "companion"
        data = load_push_tokens()
        if not isinstance(data, dict) or user_id not in data:
            return
        devices = data[user_id]
        if not isinstance(devices, dict):
            data[user_id] = {}
            save_push_tokens(data)
            return
        if device_id is not None and str(device_id).strip():
            devices.pop(str(device_id).strip(), None)
        elif token is not None and str(token).strip():
            token_s = str(token).strip()
            to_remove = [d for d, e in devices.items() if isinstance(e, dict) and str(e.get("token") or "").strip() == token_s]
            for d in to_remove:
                devices.pop(d, None)
        else:
            devices.clear()
        if not devices:
            del data[user_id]
        save_push_tokens(data)
    except Exception as e:
        logger.debug("push_tokens unregister failed: {}", e)


def get_tokens_for_user(user_id: str) -> List[Dict[str, Any]]:
    """Return list of {token, platform, updated_at} for all devices of user_id. Never raises; returns [] on error."""
    try:
        user_id = (user_id or "").strip() or "companion"
        data = load_push_tokens()
        if not isinstance(data, dict):
            return []
        devices = data.get(user_id)
        if not isinstance(devices, dict):
            return []
        return [
            {"token": e["token"], "platform": e["platform"], "updated_at": e.get("updated_at") or ""}
            for e in devices.values()
            if isinstance(e, dict) and str(e.get("token") or "").strip()
        ]
    except Exception as e:
        logger.debug("push_tokens get_tokens_for_user failed: {}", e)
        return []
