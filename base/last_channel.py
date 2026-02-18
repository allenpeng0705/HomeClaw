"""
Last-channel store for send_response_to_latest_channel.
Persists the last request (channel) to SQLite and an atomic file so we can deliver
follow-up messages to the right channel after restart or when in-memory is missing.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

_DEFAULT_KEY = "default"


def _file_path() -> Path:
    from base.util import Util
    return Path(Util().data_path()) / "latest_channel.json"


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON to path atomically (write to .tmp then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        tmp.replace(path)
    except Exception as e:
        logger.warning("last_channel: atomic write failed: {}", e)
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def _atomic_read(path: Path) -> Optional[Dict[str, Any]]:
    """Read JSON from path; returns None on error or missing."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("last_channel: read failed: {}", e)
        return None


def save_last_channel(
    request_id: str,
    host: str,
    port: int,
    channel_name: str,
    request_metadata: Dict[str, Any],
    key: str = _DEFAULT_KEY,
    app_id: Optional[str] = None,
) -> None:
    """Persist last channel to DB and atomic file. Call on every incoming request."""
    # Atomic file (always, so we have fallback)
    payload = {
        "key": key,
        "request_id": request_id,
        "host": host,
        "port": port,
        "channel_name": channel_name,
        "request_metadata": request_metadata,
        "app_id": app_id or "",
    }
    _atomic_write(_file_path(), payload)

    # SQLite (if available)
    try:
        from memory.database.database import DatabaseManager
        from memory.database.models import LastChannelModel

        session = DatabaseManager().get_session()
        meta_json = json.dumps(request_metadata, ensure_ascii=False, default=str)
        row = session.query(LastChannelModel).filter(LastChannelModel.key == key).first()
        if row:
            row.request_id = request_id
            row.host = host
            row.port = int(port)
            row.channel_name = channel_name
            row.request_metadata = meta_json
            row.app_id = app_id or ""
        else:
            session.add(
                LastChannelModel(
                    key=key,
                    request_id=request_id,
                    host=host,
                    port=int(port),
                    channel_name=channel_name,
                    app_id=app_id or "",
                    request_metadata=meta_json,
                )
            )
        session.commit()
    except Exception as e:
        logger.debug("last_channel: DB save failed (file fallback used): %s", e)
        try:
            session.rollback()
        except Exception:
            pass


def get_last_channel(key: str = _DEFAULT_KEY) -> Optional[Dict[str, Any]]:
    """Load last channel from DB or file. Returns dict with request_id, host, port, channel_name, request_metadata."""
    # Try DB first
    try:
        from memory.database.database import DatabaseManager
        from memory.database.models import LastChannelModel

        session = DatabaseManager().get_session()
        row = session.query(LastChannelModel).filter(LastChannelModel.key == key).first()
        if row:
            meta = {}
            if row.request_metadata:
                try:
                    meta = json.loads(row.request_metadata)
                except Exception:
                    pass
            return {
                "request_id": row.request_id,
                "host": row.host,
                "port": row.port,
                "channel_name": row.channel_name,
                "app_id": getattr(row, "app_id", None) or "",
                "request_metadata": meta,
            }
    except Exception as e:
        logger.debug("last_channel: DB get failed: {}", e)

    # File fallback
    data = _atomic_read(_file_path())
    if data and data.get("key") == key:
        return {
            "request_id": data.get("request_id", ""),
            "host": data.get("host", ""),
            "port": int(data.get("port", 0)),
            "channel_name": data.get("channel_name", ""),
            "app_id": data.get("app_id", ""),
            "request_metadata": data.get("request_metadata") or {},
        }
    if data:
        # File has different key; still return it for "default" single-channel use
        return {
            "request_id": data.get("request_id", ""),
            "host": data.get("host", ""),
            "port": int(data.get("port", 0)),
            "channel_name": data.get("channel_name", ""),
            "app_id": data.get("app_id", ""),
            "request_metadata": data.get("request_metadata") or {},
        }
    return None
