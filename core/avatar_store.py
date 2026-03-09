"""
Avatar storage for user and friend thumbnails.
Paths: data_path()/avatars/users/{user_id}.png, data_path()/avatars/friends/{user_id}/{friend_id}.png.
Preset thumbnails: config/preset_thumbnails/{filename} from friend_presets.yml thumbnail key.
Sanitizes user_id and friend_id for path safety. Max size 1MB; formats JPEG/PNG.
"""
import re
from pathlib import Path
from typing import Optional

from loguru import logger

from base.util import Util


def _sanitize_id(raw: Optional[str], max_len: int = 128) -> str:
    """Allow alphanumeric, underscore, hyphen. Never raises."""
    try:
        s = (str(raw or "").strip())[:max_len]
        s = re.sub(r"[^\w\-]", "_", s)
        return s or "_"
    except Exception:
        return "_"


def get_user_avatar_path(user_id: str, data_root: Optional[str] = None) -> Path:
    """Return path for user avatar file. Tries .png then .jpg. data_root defaults to Util().data_path(). Never raises."""
    try:
        root = (data_root or (Util().data_path() or "") or "").strip()
        if not root:
            return Path("/nonexistent")
        uid = _sanitize_id(user_id)
        base = Path(root) / "avatars" / "users"
        for ext in (".png", ".jpg", ".jpeg"):
            p = base / f"{uid}{ext}"
            if p.is_file():
                return p
        return base / f"{uid}.png"
    except Exception:
        return Path("/nonexistent")


def get_friend_avatar_path(user_id: str, friend_id: str, data_root: Optional[str] = None) -> Path:
    """Return path for friend (custom AI) avatar. Tries .png then .jpg. Never raises."""
    try:
        root = (data_root or (Util().data_path() or "") or "").strip()
        if not root:
            return Path("/nonexistent")
        uid = _sanitize_id(user_id)
        fid = _sanitize_id(friend_id)
        base = Path(root) / "avatars" / "friends" / uid
        for ext in (".png", ".jpg", ".jpeg"):
            p = base / f"{fid}{ext}"
            if p.is_file():
                return p
        return base / f"{fid}.png"
    except Exception:
        return Path("/nonexistent")


def get_preset_thumbnail_path(preset_name: str) -> Optional[Path]:
    """
    Return path to preset thumbnail image if it exists.
    preset_name: e.g. 'reminder', 'note', 'finder'.
    Reads friend_presets.yml for thumbnail filename (default {preset}.png under config/preset_thumbnails/).
    Returns None if file missing or config invalid. Never raises.
    """
    try:
        pn = (preset_name or "").strip()
        if not pn:
            return None
        from base.friend_presets import load_friend_presets
        presets = load_friend_presets()
        if not presets or not isinstance(presets, dict):
            return None
        cfg = presets.get(pn)
        if not isinstance(cfg, dict):
            return None
        filename = (cfg.get("thumbnail") or "").strip() or f"{pn}.png"
        # Path safety: only allow basename (no path traversal)
        filename = Path(filename).name or f"{pn}.png"
        # Try multiple roots so preset thumbnails work from repo, installed package, or custom root.
        roots = [
            (Util().root_path() or "").strip(),
            str(Path(__file__).resolve().parent.parent),  # core's parent = project root
        ]
        try:
            import base.friend_presets as _fp
            base_dir = Path(getattr(_fp, "__file__", "") or "").resolve().parent.parent
            if base_dir and str(base_dir):
                roots.append(str(base_dir))
        except Exception:
            pass
        for root in roots:
            if not root:
                continue
            path = Path(root) / "config" / "preset_thumbnails" / filename
            if path.is_file():
                return path
        return None
    except Exception:
        return None


def save_user_avatar(user_id: str, content: bytes, content_type: Optional[str] = None) -> bool:
    """Save user avatar. content_type hint: image/png, image/jpeg. Max 1MB. Returns True on success."""
    try:
        if len(content) > 1024 * 1024:
            return False
        root = (Util().data_path() or "").strip()
        if not root:
            return False
        uid = _sanitize_id(user_id)
        base = Path(root) / "avatars" / "users"
        base.mkdir(parents=True, exist_ok=True)
        ext = ".png"
        if content_type and "jpeg" in (content_type or "").lower():
            ext = ".jpg"
        path = base / f"{uid}{ext}"
        path.write_bytes(content)
        for other in (".png", ".jpg", ".jpeg"):
            if other != ext:
                (base / f"{uid}{other}").unlink(missing_ok=True)
        return True
    except Exception as e:
        logger.debug("save_user_avatar failed: {}", e)
        return False


def save_friend_avatar(user_id: str, friend_id: str, content: bytes, content_type: Optional[str] = None) -> bool:
    """Save friend (custom AI) avatar. Max 1MB. Returns True on success."""
    try:
        if len(content) > 1024 * 1024:
            return False
        root = (Util().data_path() or "").strip()
        if not root:
            return False
        uid = _sanitize_id(user_id)
        fid = _sanitize_id(friend_id)
        base = Path(root) / "avatars" / "friends" / uid
        base.mkdir(parents=True, exist_ok=True)
        ext = ".png"
        if content_type and "jpeg" in (content_type or "").lower():
            ext = ".jpg"
        path = base / f"{fid}{ext}"
        path.write_bytes(content)
        for other in (".png", ".jpg", ".jpeg"):
            if other != ext:
                (base / f"{fid}{other}").unlink(missing_ok=True)
        return True
    except Exception as e:
        logger.debug("save_friend_avatar failed: {}", e)
        return False
