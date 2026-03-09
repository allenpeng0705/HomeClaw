"""
Encrypt/decrypt auth_api_key at rest. When HOMECLAW_AUTH_KEY env is set, Core can store
auth_api_key in config as "encrypted:<base64>" and decrypt on load. Plain values remain
supported for backward compatibility.

Uses Fernet (AES-128-CBC + HMAC). Key derived from env: SHA256(HOMECLAW_AUTH_KEY), then
base64url-encoded (32 bytes → Fernet key). Never raises; returns None or plain value on failure.
"""

import base64
import hashlib
import os
from typing import Optional

_ENV_KEY = "HOMECLAW_AUTH_KEY"
_PREFIX = "encrypted:"


def _get_fernet_key() -> Optional[bytes]:
    """Derive a Fernet key from HOMECLAW_AUTH_KEY. Returns None if env not set or empty."""
    try:
        raw = (os.environ.get(_ENV_KEY) or "").strip()
        if not raw:
            return None
        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest)
    except Exception:
        return None


def decrypt_auth_api_key(value: Optional[str]) -> str:
    """
    If value is "encrypted:<base64>", decrypt and return plain auth_api_key.
    Otherwise return value as-is (plain text). Never raises; on decrypt failure returns "".
    """
    if not value or not isinstance(value, str):
        return (value or "").strip()
    val = value.strip()
    if not val.startswith(_PREFIX):
        return val
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return ""
    key = _get_fernet_key()
    if not key:
        return ""
    try:
        f = Fernet(key)
        token = val[len(_PREFIX) :].encode("ascii")
        plain = f.decrypt(token)
        return plain.decode("utf-8", errors="replace")
    except Exception:
        return ""


def encrypt_auth_api_key(plain: Optional[str]) -> str:
    """
    If HOMECLAW_AUTH_KEY is set and plain is non-empty, return "encrypted:<base64>".
    Otherwise return plain as-is. Never raises; on encrypt failure returns plain.
    """
    if not plain or not isinstance(plain, str):
        return (plain or "").strip()
    plain = plain.strip()
    if not plain:
        return ""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return plain
    key = _get_fernet_key()
    if not key:
        return plain
    try:
        f = Fernet(key)
        token = f.encrypt(plain.encode("utf-8"))
        return _PREFIX + token.decode("ascii")
    except Exception:
        return plain


def is_encryption_available() -> bool:
    """Return True if HOMECLAW_AUTH_KEY is set and cryptography.fernet is available."""
    if not _get_fernet_key():
        return False
    try:
        from cryptography.fernet import Fernet
        return True
    except ImportError:
        return False
