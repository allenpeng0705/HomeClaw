"""
User-to-user message inbox: store and list messages for a user (single HomeClaw social network).
Messages are stored under data_path()/user_inbox/{user_id}.json. Used by POST /api/user-message and GET /api/user-inbox.
"""

import json
import os
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from loguru import logger

from base.util import Util
from core.result_viewer import file_absolute_path_to_view_url, file_view_url_to_core_relative

_INBOX_LOCKS: Dict[str, Lock] = {}
_INBOX_LOCKS_GUARD = Lock()


def _inbox_dir() -> Path:
    """Return user_inbox directory under data path. Never raises (falls back to cwd/user_inbox on error)."""
    try:
        return Path(Util().data_path()) / "user_inbox"
    except Exception:
        return Path("user_inbox")


def _absolute_path_ref_to_client_url(ref: str) -> Optional[str]:
    """Turn a server-only absolute path into a /files/... or https://... URL clients can load."""
    url, _err = file_absolute_path_to_view_url(ref)
    if not url:
        return None
    return file_view_url_to_core_relative(url)


def sanitize_media_ref_list_for_client(refs: Any, max_each_bytes: int = 0) -> Any:
    """Replace absolute sandbox paths with file-view URLs; pass through data:, http(s):, /files/...

    ``max_each_bytes`` is ignored (kept for API compatibility); media is served via /files/... not base64.
    """
    _ = max_each_bytes
    if not isinstance(refs, list):
        return refs
    out: List[str] = []
    for it in refs:
        if not isinstance(it, str):
            continue
        s = it.strip()
        if not s:
            continue
        lower = s.lower()
        if lower.startswith("data:") or lower.startswith("http://") or lower.startswith("https://"):
            out.append(s)
            continue
        if lower.startswith("/files/") or lower.startswith("/files/out"):
            out.append(s)
            continue
        mapped = _absolute_path_ref_to_client_url(s)
        out.append(mapped if mapped else s)
    return out


def sanitize_message_dict_for_client(msg: Dict[str, Any], max_each_bytes: int = 0) -> Dict[str, Any]:
    """Copy of one inbox message with upload-dir paths expanded for clients (Companion)."""
    if not isinstance(msg, dict):
        return msg
    out = dict(msg)
    for key in ("images", "audios", "videos", "file_links"):
        if key in out:
            out[key] = sanitize_media_ref_list_for_client(out.get(key), max_each_bytes=max_each_bytes)
    return out


def sanitize_messages_list_for_client(messages: List[Any], max_each_bytes: int = 0) -> List[Any]:
    return [sanitize_message_dict_for_client(dict(m), max_each_bytes=max_each_bytes) if isinstance(m, dict) else m for m in messages]


def _inbox_path(user_id: str) -> Path:
    """Safe path for one user's inbox file. Never raises."""
    try:
        raw = (user_id or "").strip() if user_id is not None else ""
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in raw)[:200] or "_unknown"
        return _inbox_dir() / f"{safe}.json"
    except Exception:
        return _inbox_dir() / "_unknown.json"


def _get_inbox_lock(user_id: str) -> Lock:
    """Return a per-user lock so append operations are process-local serialized."""
    key = str(_inbox_path(user_id))
    with _INBOX_LOCKS_GUARD:
        lock = _INBOX_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _INBOX_LOCKS[key] = lock
        return lock


def _write_inbox_atomic(path: Path, messages: List[Dict[str, Any]]) -> None:
    """Write inbox JSON atomically to reduce corruption/loss on concurrent writes."""
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"messages": messages}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def append_message(
    to_user_id: str,
    from_user_id: str,
    from_user_name: str,
    text: str,
    images: Optional[List[str]] = None,
    audios: Optional[List[str]] = None,
    videos: Optional[List[str]] = None,
    file_links: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    e2e: Optional[Dict[str, Any]] = None,
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
        with _get_inbox_lock(to_user_id):
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
            if e2e and isinstance(e2e, dict):
                entry["e2e"] = dict(e2e)
            if metadata and isinstance(metadata, dict):
                for k, v in metadata.items():
                    if v is not None and k not in entry:
                        entry[k] = v
            messages.append(entry)
            _write_inbox_atomic(path, messages[-500:])
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


def get_thread(
    user_id: str,
    other_user_id: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Return the conversation thread between user_id and other_user_id.
    Merges messages from user_id's inbox (from other) and other_user_id's inbox (from user_id),
    sorted by created_at. Used so both sides see the full thread (sent + received).
    """
    try:
        user_id = (user_id or "").strip()
        other_user_id = (other_user_id or "").strip()
        if not user_id or not other_user_id or user_id == other_user_id:
            return []
        limit = max(1, min(200, limit))
        # Messages TO me FROM other (in my inbox)
        to_me = get_messages(user_id, limit=limit, after_id=None)
        from_other = [m for m in to_me if isinstance(m, dict) and (m.get("from_user_id") or "").strip() == other_user_id]
        # Messages TO other FROM me (in their inbox)
        to_other = get_messages(other_user_id, limit=limit, after_id=None)
        from_me = [m for m in to_other if isinstance(m, dict) and (m.get("from_user_id") or "").strip() == user_id]
        # Copy and set to_user_id so we don't mutate the original loaded dicts.
        result = []
        for m in from_other:
            if isinstance(m, dict):
                out = dict(m)
                out["to_user_id"] = user_id
                result.append(out)
        for m in from_me:
            if isinstance(m, dict):
                out = dict(m)
                out["to_user_id"] = other_user_id
                result.append(out)
        result.sort(key=lambda m: (m.get("created_at") or 0))
        return result[-limit:] if limit > 0 else result
    except Exception as e:
        logger.debug("user_inbox get_thread failed: {}", e)
        return []


def _is_under_upload_roots(full: Path) -> bool:
    """True if path is under project or homeclaw_root database/uploads (deletable Companion uploads)."""
    try:
        full = full.resolve()
        root = Path(Util().root_path()).expanduser().resolve()
        u1 = (root / "database" / "uploads").resolve()
        try:
            full.relative_to(u1)
            return True
        except ValueError:
            pass
        meta = Util().get_core_metadata()
        hc = str(getattr(meta, "homeclaw_root", None) or "").strip()
        if not hc:
            try:
                hc = str(meta.get_homeclaw_root() or "").strip()
            except Exception:
                hc = ""
        if hc:
            u2 = (Path(hc).expanduser().resolve() / "database" / "uploads").resolve()
            try:
                full.relative_to(u2)
                return True
            except ValueError:
                pass
    except Exception:
        return False
    return False


def _unlink_local_paths_from_message_dict(m: Dict[str, Any]) -> None:
    """Best-effort delete files for absolute paths in images/audios/videos/file_links (not http(s) or data:)."""
    for key in ("images", "audios", "videos", "file_links"):
        raw = m.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, str):
                continue
            s = item.strip()
            if not s or s.lower().startswith("data:") or s.lower().startswith("http://") or s.lower().startswith("https://"):
                continue
            if s.startswith("/files/") or s.startswith("/files/out"):
                continue
            try:
                p = Path(s)
                if not p.is_absolute():
                    continue
                if not p.is_file():
                    continue
                if not _is_under_upload_roots(p):
                    continue
                p.unlink()
                logger.debug("user_inbox: removed upload file {}", p)
            except Exception as e:
                logger.debug("user_inbox: unlink skip {}: {}", s, e)


def clear_thread(
    user_id: str,
    other_user_id: str,
) -> int:
    """
    Clear a user-to-user thread from local inbox storage.
    Removes:
      - messages in user_id inbox where from_user_id == other_user_id
      - mirrored outbound messages in other_user_id inbox where from_user_id == user_id
    Returns number of removed messages.
    """
    try:
        user_id = (user_id or "").strip()
        other_user_id = (other_user_id or "").strip()
        if not user_id or not other_user_id or user_id == other_user_id:
            return 0

        def _clear_side(owner_user_id: str, from_user_id_to_remove: str) -> int:
            path = _inbox_path(owner_user_id)
            if not path.is_file():
                return 0
            with _get_inbox_lock(owner_user_id):
                messages: List[Dict[str, Any]] = []
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        raw = data.get("messages") if isinstance(data, dict) else []
                        if isinstance(raw, list):
                            messages = [m for m in raw if isinstance(m, dict)]
                except Exception as e:
                    logger.debug("user_inbox clear_thread read failed {}: {}", path, e)
                    return 0
                removed_rows = [
                    m
                    for m in messages
                    if (m.get("from_user_id") or "").strip() == from_user_id_to_remove
                ]
                kept = [
                    m
                    for m in messages
                    if (m.get("from_user_id") or "").strip() != from_user_id_to_remove
                ]
                for m in removed_rows:
                    _unlink_local_paths_from_message_dict(m)
                removed = len(removed_rows)
                if removed > 0:
                    _write_inbox_atomic(path, kept[-500:])
                return removed

        removed_a = _clear_side(owner_user_id=user_id, from_user_id_to_remove=other_user_id)
        removed_b = _clear_side(owner_user_id=other_user_id, from_user_id_to_remove=user_id)
        return removed_a + removed_b
    except Exception as e:
        logger.warning("user_inbox clear_thread failed: {}", e)
        return 0
