"""
Media helpers: image resize, image/audio/video item to data URL or base64+format.
Extracted from core/core.py (Phase 7 refactor). Takes core as first argument; no import of core.core.
"""

import base64
import os
from typing import Any, Optional, Tuple

from loguru import logger

from base.util import Util


def resize_image_data_url_if_needed(core: Any, data_url: str, max_dimension: int) -> str:
    """If max_dimension > 0 and Pillow is available, resize image so max(w,h) <= max_dimension; return data URL. Else return original."""
    if not data_url or not isinstance(data_url, str) or max_dimension <= 0:
        return data_url or ""
    try:
        from PIL import Image
        import io
    except ImportError:
        return data_url
    try:
        idx = data_url.find(";base64,")
        if idx <= 0:
            return data_url
        b64 = data_url[idx + 8:]
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if w <= max_dimension and h <= max_dimension:
            return data_url
        if w >= h:
            new_w, new_h = max_dimension, max(1, int(h * max_dimension / w))
        else:
            new_w, new_h = max(1, int(w * max_dimension / h)), max_dimension
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        out_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{out_b64}"
    except Exception as e:
        logger.debug("Image resize skipped: {}", e)
        return data_url


def image_item_to_data_url(core: Any, item: str) -> str:
    """Convert image item (data URL, file path, or raw base64) to a data URL for vision API. Optionally resizes if completion.image_max_dimension is set."""
    if not item or not isinstance(item, str):
        return ""
    item = item.strip()
    if item.lower().replace("data: ", "data:", 1).startswith("data:image/"):
        # Normalize so URL is always "data:image/...;base64,..." (some clients send "data: image/...")
        data_url = item.replace("data: ", "data:", 1) if item.startswith("data: ") else item
    elif item.startswith("data:"):
        data_url = item.replace("data: ", "data:", 1) if item.startswith("data: ") else item
    elif os.path.isfile(item):
        try:
            with open(item, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            data_url = f"data:image/jpeg;base64,{b64}"
        except Exception as e:
            logger.warning("Failed to read image file {}: {}", item, e)
            return ""
    else:
        # Path-like but file not found: do not treat as base64
        if ("/" in item or "\\" in item) and not os.path.isfile(item):
            logger.warning("Image file not found (path not readable): {}", item[:200])
            return ""
        data_url = f"data:image/jpeg;base64,{item}"
    max_dim = 0
    try:
        comp = getattr(Util().get_core_metadata(), "completion", None) or {}
        max_dim = int(comp.get("image_max_dimension") or 0)
    except (TypeError, ValueError):
        pass
    return resize_image_data_url_if_needed(core, data_url, max_dim)


def audio_item_to_base64_and_format(core: Any, item: str) -> Optional[Tuple[str, str]]:
    """Convert audio item (data URL or file path) to (base64_string, format) for input_audio. Format: wav, mp3, etc."""
    if not item or not isinstance(item, str):
        return None
    item = item.strip()
    if item.startswith("data:"):
        # data:audio/wav;base64,... or data:audio/mpeg;base64,...
        try:
            header, _, b64 = item.partition(",")
            if not b64:
                return None
            mime = header.replace("data:", "").split(";")[0].strip().lower()
            if "wav" in mime or "wave" in mime:
                return (b64, "wav")
            if "mpeg" in mime or "mp3" in mime:
                return (b64, "mp3")
            if "ogg" in mime:
                return (b64, "ogg")
            if "webm" in mime:
                return (b64, "webm")
            return (b64, "wav")
        except Exception:
            return None
    if os.path.isfile(item):
        try:
            with open(item, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            ext = (os.path.splitext(item)[1] or "").lower()
            fmt = "wav"
            if ext in (".mp3", ".mpeg"):
                fmt = "mp3"
            elif ext == ".ogg":
                fmt = "ogg"
            elif ext == ".webm":
                fmt = "webm"
            elif ext == ".wav":
                fmt = "wav"
            return (b64, fmt)
        except Exception as e:
            logger.warning("Failed to read audio file {}: {}", item, e)
            return None
    return None


def video_item_to_base64_and_format(core: Any, item: str) -> Optional[Tuple[str, str]]:
    """Convert video item (data URL or file path) to (base64_string, format) for input_video. Format: mp4, webm, etc."""
    if not item or not isinstance(item, str):
        return None
    item = item.strip()
    if item.startswith("data:"):
        try:
            header, _, b64 = item.partition(",")
            if not b64:
                return None
            mime = header.replace("data:", "").split(";")[0].strip().lower()
            if "mp4" in mime:
                return (b64, "mp4")
            if "webm" in mime:
                return (b64, "webm")
            return (b64, "mp4")
        except Exception:
            return None
    if os.path.isfile(item):
        try:
            with open(item, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            ext = (os.path.splitext(item)[1] or "").lower()
            fmt = "mp4"
            if ext == ".webm":
                fmt = "webm"
            elif ext in (".mp4", ".m4v"):
                fmt = "mp4"
            return (b64, fmt)
        except Exception as e:
            logger.warning("Failed to read video file {}: {}", item, e)
            return None
    return None
