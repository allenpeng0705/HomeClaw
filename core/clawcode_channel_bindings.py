"""Map inbound identity (e.g. telegram_123) → clawcode_session_id for channel P5. JSON under database/."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from base.util import Util

_LOCK = threading.Lock()


def _path() -> Path:
    return Path(Util().root_path()) / "database" / "clawcode_channel_bindings.json"


def _load() -> Dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning("clawcode_channel_bindings: load failed: {}", e)
        return {}


def _save(data: Dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def get_binding(owner_user_id: str) -> Optional[str]:
    uid = (owner_user_id or "").strip()
    if not uid:
        return None
    with _LOCK:
        data = _load()
        row = data.get(uid)
        if not isinstance(row, dict):
            return None
        sid = str(row.get("clawcode_session_id") or "").strip()
        return sid or None


def set_binding(owner_user_id: str, clawcode_session_id: str) -> None:
    uid = (owner_user_id or "").strip()
    sid = (clawcode_session_id or "").strip()
    if not uid or not sid:
        return
    with _LOCK:
        data = _load()
        data[uid] = {
            "owner_user_id": uid,
            "clawcode_session_id": sid,
            "updated_at": time.time(),
        }
        _save(data)


def clear_binding(owner_user_id: str) -> None:
    uid = (owner_user_id or "").strip()
    if not uid:
        return
    with _LOCK:
        data = _load()
        data.pop(uid, None)
        _save(data)
