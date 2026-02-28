"""
Portal server configuration: host, port, paths.
Uses env and path resolution only; no dependency on base.util so portal can start with minimal imports.
"""
import os
from pathlib import Path
from typing import Optional

# Project root: parent of portal package directory.
_PORTAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = _PORTAL_DIR.parent

def get_host() -> str:
    """Bind host. Always 127.0.0.1 for local-only access."""
    return os.environ.get("PORTAL_HOST", "127.0.0.1")

def get_port() -> int:
    """Portal server port. Default 18472 to avoid common ports (8000, 8080, etc.)."""
    try:
        return int(os.environ.get("PORTAL_PORT", "18472"))
    except (TypeError, ValueError):
        return 18472

def get_config_dir() -> Path:
    """Path to config directory (e.g. config/)."""
    return ROOT_DIR / "config"


def get_portal_secret() -> Optional[str]:
    """Shared secret for API auth (Core→Portal). From PORTAL_SECRET env or config/portal_secret.txt (first line).
    When None, API routes under /api/ are not protected by secret (session or no auth). Same value must be in Core's portal_secret (core.yml or env)."""
    try:
        s = os.environ.get("PORTAL_SECRET", "").strip()
        if s:
            return s
        secret_file = get_config_dir() / "portal_secret.txt"
        if secret_file.is_file():
            with open(secret_file, "r", encoding="utf-8") as f:
                line = f.readline()
                if line:
                    return line.strip() or None
    except Exception:
        pass
    return None
