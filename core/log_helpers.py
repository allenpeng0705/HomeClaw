"""
Logging and string helpers for Core. Extracted from core/core.py (Phase 1 refactor).
No dependency on core.core; safe to import from core. Never raises; defensive.
"""
import logging
import re

from loguru import logger

from base.util import Util


def _component_log(component: str, message: str) -> None:
    """Log component activity when core is not silent (silent: false in core.yml). Toggle via config/core.yml silent: true/false."""
    try:
        if not Util().is_silent():
            logger.info(f"[{component}] {message}")
    except Exception:
        pass


def _truncate_for_log(s: str, max_len: int = 2000) -> str:
    """Truncate string for logging; append ... if truncated."""
    if not s or len(s) <= max_len:
        return s or ""
    return s[:max_len] + "\n... (truncated)"


def _strip_leading_route_label(s: str) -> str:
    """Remove leading [Local], [Cloud], or [Local · ...] / [Cloud · ...] so we don't duplicate labels."""
    if not s or not isinstance(s, str):
        return s or ""
    t = s.strip()
    # Match [Local], [Cloud], or [Local · heuristic], [Cloud · semantic], etc.
    if re.match(r"^\[(?:Local|Cloud)(?:\s*·\s*[^\]]*)?\]\s*", t):
        return re.sub(r"^\[(?:Local|Cloud)(?:\s*·\s*[^\]]*)?\]\s*", "", t, count=1).strip()
    return s


class _SuppressConfigCoreAccessFilter(logging.Filter):
    """Filter out uvicorn access log lines for GET /api/config/core (Companion connection checks)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage() if hasattr(record, "getMessage") else (getattr(record, "msg", "") or "")
            if "/api/config/core" in str(msg) and " 200 " in str(msg):
                return False
        except Exception:
            pass
        return True
