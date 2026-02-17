"""
File-understanding module: detect file type (image, audio, video, document) and handle each correctly.
Stable and robust: all steps wrapped in try/except; failures are recorded and do not crash Core.
See docs_design/FileUnderstandingDesign.md.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from loguru import logger


FILE_TYPE_IMAGE = "image"
FILE_TYPE_AUDIO = "audio"
FILE_TYPE_VIDEO = "video"
FILE_TYPE_DOCUMENT = "document"
FILE_TYPE_UNKNOWN = "unknown"

# Extension -> category (lowercase)
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
_AUDIO_EXT = {".wav", ".mp3", ".ogg", ".webm", ".m4a", ".flac", ".aac", ".aiff"}
_VIDEO_EXT = {".mp4", ".webm", ".m4v", ".mov", ".avi", ".mkv"}
_DOCUMENT_EXT = {
    ".pdf", ".txt", ".docx", ".doc", ".xlsx", ".xls", ".md", ".html", ".htm",
    ".csv", ".json", ".xml", ".pptx", ".ppt", ".eml", ".msg", ".epub", ".rst", ".mdx",
}


@dataclass
class FileUnderstandingResult:
    """Result of process_files: classified media paths and extracted document texts."""
    images: List[str] = field(default_factory=list)
    audios: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    document_texts: List[str] = field(default_factory=list)
    document_paths: List[str] = field(default_factory=list)  # same order as document_texts; for KB source_id
    errors: List[str] = field(default_factory=list)


def detect_file_type(path: str) -> str:
    """
    Detect file type from path (extension and optional magic bytes).
    Returns FILE_TYPE_IMAGE | FILE_TYPE_AUDIO | FILE_TYPE_VIDEO | FILE_TYPE_DOCUMENT | FILE_TYPE_UNKNOWN.
    Never raises; returns FILE_TYPE_UNKNOWN on error or unknown extension.
    """
    try:
        if not path or not isinstance(path, str):
            return FILE_TYPE_UNKNOWN
        p = Path(path.strip())
        ext = p.suffix.lower()
        if ext in _IMAGE_EXT:
            return FILE_TYPE_IMAGE
        if ext in _AUDIO_EXT:
            return FILE_TYPE_AUDIO
        if ext in _VIDEO_EXT:
            return FILE_TYPE_VIDEO
        if ext in _DOCUMENT_EXT:
            return FILE_TYPE_DOCUMENT
        # Optional: magic bytes for PDF when extension missing
        if not ext and p.is_file():
            try:
                with open(p, "rb") as f:
                    head = f.read(8)
                if head.startswith(b"%PDF"):
                    return FILE_TYPE_DOCUMENT
            except Exception:
                pass
        return FILE_TYPE_UNKNOWN
    except Exception as e:
        logger.debug("file_understanding detect_file_type failed for %s: %s", path, e)
        return FILE_TYPE_UNKNOWN


def extract_document_text(path: str, base_dir: str, max_chars: int = 64000) -> Optional[str]:
    """
    Extract text from a document file (PDF, txt, Word, Excel, etc.).
    Uses Unstructured when available, then pypdf for PDF, then plain text.
    Returns None on failure. Never raises.
    """
    try:
        if not path or not isinstance(path, str):
            return None
        path = path.strip()
        if not base_dir or not isinstance(base_dir, str):
            base_dir = "."
        base = Path(base_dir).resolve()
        p = Path(path).resolve()
        if not p.is_file():
            return None
        # If path is relative, resolve against base and ensure under base
        if not p.is_absolute():
            p = (base / path).resolve()
        if not p.is_file():
            return None
        if base_dir and not str(p).startswith(str(base)):
            return None
        suffix = p.suffix.lower()
        try:
            max_chars = max(1000, min(500_000, int(max_chars)))
        except (TypeError, ValueError):
            max_chars = 64000

        # 1) Try Unstructured
        if suffix in _DOCUMENT_EXT:
            try:
                from unstructured.partition.auto import partition
                elements = partition(filename=str(p))
                parts = []
                total = 0
                for el in elements:
                    text = (getattr(el, "text", None) or "").strip()
                    if not text:
                        continue
                    remaining = max_chars - total
                    if remaining <= 0:
                        break
                    if len(text) > remaining:
                        parts.append(text[:remaining])
                        total = max_chars
                        break
                    parts.append(text)
                    total += len(text)
                out = "\n\n".join(parts) if parts else "(no text extracted)"
                if total >= max_chars:
                    out += "\n... (truncated)"
                return out
            except ImportError:
                pass
            except Exception as e:
                logger.debug("file_understanding Unstructured failed for %s: %s", p, e)

        # 2) PDF with pypdf
        if suffix == ".pdf":
            try:
                try:
                    from pypdf import PdfReader
                except ImportError:
                    from PyPDF2 import PdfReader  # type: ignore
                reader = PdfReader(str(p))
                parts = []
                total = 0
                for page in reader.pages:
                    if total >= max_chars:
                        break
                    text = (page.extract_text() or "").strip()
                    if text:
                        remaining = max_chars - total
                        if len(text) > remaining:
                            parts.append(text[:remaining])
                            total = max_chars
                            break
                        parts.append(text)
                        total += len(text)
                out = "\n\n".join(parts) if parts else "(no text extracted)"
                if total >= max_chars:
                    out += "\n... (truncated)"
                return out
            except Exception as e:
                logger.debug("file_understanding pypdf failed for %s: %s", p, e)
                return None

        # 3) Plain text (txt, md, etc.)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... (truncated)"
            return content
        except Exception as e:
            logger.debug("file_understanding read_text failed for %s: %s", p, e)
            return None
    except Exception as e:
        logger.debug("file_understanding extract_document_text failed for %s: %s", path, e)
        return None


def process_files(
    files: List[str],
    supported_media: List[str],
    base_dir: str,
    max_chars: int = 64000,
) -> FileUnderstandingResult:
    """
    Classify each file and either add to media lists (image/audio/video) or extract text (document).
    All steps are wrapped in try/except; failures are appended to result.errors and do not raise.
    """
    result = FileUnderstandingResult()
    if not files or not isinstance(files, list):
        return result
    try:
        base = Path(base_dir).resolve() if (base_dir and isinstance(base_dir, str)) else Path(".").resolve()
    except Exception:
        base = Path(".").resolve()
    try:
        max_chars = max(1000, min(500_000, int(max_chars))) if max_chars is not None else 64000
    except (TypeError, ValueError):
        max_chars = 64000
    try:
        supported_set = set(supported_media) if supported_media is not None else set()
    except (TypeError, ValueError):
        supported_set = set()

    for path in files:
        if not path or not isinstance(path, str):
            continue
        path = path.strip()
        try:
            # Resolve path (relative to base if not absolute)
            p = Path(path)
            if not p.is_absolute():
                p = (base / path).resolve()
            if not p.is_file():
                result.errors.append(f"{path}: not a file or not found")
                continue
            path_str = str(p)

            ftype = detect_file_type(path_str)
            if ftype == FILE_TYPE_IMAGE:
                result.images.append(path_str)
            elif ftype == FILE_TYPE_AUDIO:
                result.audios.append(path_str)
            elif ftype == FILE_TYPE_VIDEO:
                result.videos.append(path_str)
            elif ftype == FILE_TYPE_DOCUMENT:
                text = extract_document_text(path_str, str(base) if base else ".", max_chars)
                if text:
                    result.document_texts.append(text)
                    result.document_paths.append(path_str)
                else:
                    result.errors.append(f"{path}: could not extract text")
            else:
                result.errors.append(f"{path}: unknown file type")
        except Exception as e:
            logger.debug("file_understanding process_files failed for %s: %s", path, e)
            result.errors.append(f"{path}: {e!s}")

    return result
