"""
Portal admin credentials: one username + password.
Storage in config/portal_admin.yml (username + salt + hash). Env override for dev.
Never raises; all functions return False or None on error.
"""
import base64
import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import Optional, Tuple

from portal.config import get_config_dir

_log = logging.getLogger(__name__)

# Env: if set, bypass file and use these for verification (dev). Do not set in production.
_ENV_USERNAME = os.environ.get("PORTAL_ADMIN_USERNAME", "").strip()
_ENV_PASSWORD = os.environ.get("PORTAL_ADMIN_PASSWORD", "").strip()


def _admin_path() -> Path:
    return Path(get_config_dir()) / "portal_admin.yml"


def _hash_password(salt: bytes, password: str) -> str:
    return hashlib.sha256(salt + password.encode("utf-8")).hexdigest()


def admin_is_configured() -> bool:
    """True if admin credentials exist (file or env). Never raises."""
    if _ENV_USERNAME and _ENV_PASSWORD:
        return True
    p = _admin_path()
    try:
        if not p.exists() or p.stat().st_size == 0:
            return False
        # Quick check: file has content (proper load is in load_admin_credentials)
        return True
    except Exception:
        return False


def load_admin_credentials() -> Tuple[Optional[str], Optional[bytes], Optional[str]]:
    """Return (username, salt_bytes, hash_hex) or (None, None, None). Never raises."""
    if _ENV_USERNAME and _ENV_PASSWORD:
        # Env mode: no stored hash; verify by comparing to env. Return a sentinel so verify uses env.
        return (_ENV_USERNAME, None, None)
    p = _admin_path()
    try:
        if not p.exists():
            return (None, None, None)
        import yaml
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or not isinstance(data, dict):
            return (None, None, None)
        username = (data.get("admin_username") or "").strip()
        salt_b64 = (data.get("admin_password_salt") or "").strip()
        hash_hex = (data.get("admin_password_hash") or "").strip()
        if not username or not salt_b64 or not hash_hex:
            return (None, None, None)
        salt = base64.b64decode(salt_b64)
        return (username, salt, hash_hex)
    except Exception as e:
        _log.debug("load_admin_credentials: %s", e)
        return (None, None, None)


def verify_portal_admin(username: str, password: str) -> bool:
    """Return True if username and password match stored or env credentials. Never raises."""
    if not username or not password:
        return False
    username = username.strip()
    password = password.strip()
    if not username or not password:
        return False
    u, salt, hash_hex = load_admin_credentials()
    if u is None and salt is None and hash_hex is None:
        return False
    if _ENV_USERNAME and _ENV_PASSWORD:
        return username == _ENV_USERNAME and password == _ENV_PASSWORD
    if u is None or salt is None or hash_hex is None:
        return False
    if username != u:
        return False
    return _hash_password(salt, password) == hash_hex


def set_admin(username: str, password: str) -> bool:
    """Store admin username and hashed password in config/portal_admin.yml. Never raises."""
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return False
    p = _admin_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        salt = secrets.token_bytes(32)
        hash_hex = _hash_password(salt, password)
        import yaml
        data = {
            "admin_username": username,
            "admin_password_salt": base64.b64encode(salt).decode("ascii"),
            "admin_password_hash": hash_hex,
        }
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        _log.info("Portal admin account set for username %s", username)
        return True
    except Exception as e:
        _log.warning("set_admin: %s", e)
        return False
