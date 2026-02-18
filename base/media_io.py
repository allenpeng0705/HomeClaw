"""
Save plugin media (photo, video, audio) from data URLs to a media folder.
Used when node_camera_snap / node_camera_clip return metadata.media so we can
1) send the file to the user via the channel and 2) keep a copy under media/images, media/videos, media/audio.
"""
import base64
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Project root: parent of base/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _media_type_from_data_url(data_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (mime_subtype, media_kind) e.g. ('jpeg', 'image') or ('webm', 'video'). media_kind is 'image'|'video'|'audio'."""
    if not data_url or not isinstance(data_url, str) or not data_url.startswith("data:"):
        return None, None
    match = re.match(r"data:([^;,]+)", data_url)
    if not match:
        return None, None
    mime = match.group(1).strip().lower()
    if mime.startswith("image/"):
        return (mime.split("/", 1)[-1] or "png").split("+")[0], "image"
    if mime.startswith("video/"):
        return (mime.split("/", 1)[-1] or "webm").split("+")[0], "video"
    if mime.startswith("audio/"):
        return (mime.split("/", 1)[-1] or "webm").split("+")[0], "audio"
    return None, None


def save_data_url_to_media_folder(
    data_url: str,
    media_base_dir: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decode a data URL (e.g. from plugin metadata.media), save to media_base_dir/<images|videos|audio>/<timestamp>_<id>.<ext>.
    Returns (absolute_path_str, media_kind) where media_kind is 'image'|'video'|'audio', or (None, None) on failure.
    media_base_dir defaults to project_root/config/workspace/media.
    """
    if not data_url or not isinstance(data_url, str):
        return None, None
    mime_subtype, media_kind = _media_type_from_data_url(data_url)
    if not media_kind:
        return None, None
    # Extract base64 payload
    idx = data_url.find("base64,")
    if idx < 0:
        return None, None
    payload_b64 = data_url[idx + 7 :].strip()
    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception:
        return None, None
    if media_base_dir is None:
        media_base_dir = _PROJECT_ROOT / "config" / "workspace" / "media"
    base = Path(media_base_dir)
    subdir = base / "images" if media_kind == "image" else (base / "videos" if media_kind == "video" else base / "audio")
    ext = (mime_subtype or "bin").split("+")[0]
    if ext in ("jpeg", "jpg", "png", "gif", "webp", "webm", "mp4", "mp3", "ogg", "wav"):
        pass
    else:
        ext = "bin"
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    short_id = (uuid.uuid4().hex)[:8]
    fname = f"{stamp}_{short_id}.{ext}"
    out_path = subdir / fname
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw)
        return str(out_path.resolve()), media_kind
    except Exception:
        return None, None
