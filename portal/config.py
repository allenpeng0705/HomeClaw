"""
Portal server configuration: host, port, paths.
Uses env and path resolution only; no dependency on base.util so portal can start with minimal imports.
"""
import os
from pathlib import Path

# Project root: parent of portal package directory.
_PORTAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = _PORTAL_DIR.parent

def get_host() -> str:
    """Bind host. Always 127.0.0.1 for local-only access."""
    return os.environ.get("PORTAL_HOST", "127.0.0.1")

def get_port() -> int:
    """Portal server port."""
    try:
        return int(os.environ.get("PORTAL_PORT", "8000"))
    except (TypeError, ValueError):
        return 8000

def get_config_dir() -> Path:
    """Path to config directory (e.g. config/)."""
    return ROOT_DIR / "config"
