"""
Download media from LINE Messaging API (Get content).
Never raises; returns None on failure. Saves to channels/line/docs/.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import httpx
from loguru import logger

# Default max size 10MB
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


def _content_type_to_ext(content_type: str) -> str:
    if not content_type:
        return ".bin"
    ct = (content_type or "").lower()
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    if "mp4" in ct or "video" in ct:
        return ".mp4"
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "m4a" in ct or "audio" in ct:
        return ".m4a"
    if "pdf" in ct:
        return ".pdf"
    return ".bin"


def download_line_media(
    message_id: str,
    channel_access_token: str,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str | None:
    """
    Download media from LINE Get content API. Saves to channels/line/docs/.
    Returns file path or None on failure. Never raises.
    """
    if not message_id or not isinstance(message_id, str) or not channel_access_token:
        return None
    try:
        url = f"https://api-data.line.me/v2/bot/message/{message_id.strip()}/content"
        headers = {"Authorization": f"Bearer {channel_access_token.strip()}"}
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, headers=headers)
            if r.status_code != 200:
                logger.debug("LINE get content {}: status {}", message_id, r.status_code)
                return None
            content = r.content
            content_type = r.headers.get("content-type", "").split(";")[0].strip()
        total = len(content)
        if total > max_bytes:
            logger.debug("LINE media {} exceeds {} bytes", message_id, max_bytes)
            return None
        ext = _content_type_to_ext(content_type)
        root = Path(__file__).resolve().parent.parent.parent
        docs_dir = root / "channels" / "line" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        out_path = docs_dir / f"line_{message_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        out_path.write_bytes(content)
        return str(out_path.resolve())
    except Exception as e:
        logger.debug("LINE download media {}: {}", message_id, e)
        return None
