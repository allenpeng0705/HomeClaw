"""
Portal session: signed cookie (no server-side store). Never raises.
"""
import base64
import hmac
import hashlib
import os
import time
from typing import Optional

# 24h
SESSION_TTL_SECONDS = 24 * 3600


def _secret() -> bytes:
    s = os.environ.get("PORTAL_SESSION_SECRET", "portal-dev-secret-change-me").strip()
    return (s or "portal-dev-secret-change-me").encode("utf-8")


def create_session_value(username: str) -> str:
    """Produce cookie value: base64(username:expiry_ts:signature)."""
    expiry = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{username}:{expiry}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def verify_session_value(value: str) -> Optional[str]:
    """Return username if cookie is valid and not expired, else None."""
    if not value or not value.strip():
        return None
    try:
        pad = 4 - len(value) % 4
        if pad != 4:
            value += "=" * pad
        raw = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
        parts = raw.split(":", 2)
        if len(parts) != 3:
            return None
        username, expiry_str, sig = parts
        expiry = int(expiry_str)
        if expiry < int(time.time()):
            return None
        payload = f"{username}:{expiry_str}"
        expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return username
    except Exception:
        return None
