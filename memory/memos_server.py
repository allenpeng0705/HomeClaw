"""
Ensure MemOS standalone server is running when memory_backend is memos or composite with memos.

When memos.url points to localhost and memos.auto_start is true (default), this module
starts the MemOS server (vendor/memos) as a subprocess if it is not already responding.
Core calls ensure_memos_server_started() before creating MemosMemoryAdapter.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from loguru import logger

# Windows-only; avoid AttributeError on non-Windows where it may be missing
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _is_local_url(url: str) -> bool:
    """Return True if url is 127.0.0.1 or localhost."""
    if not (url or "").strip():
        return False
    try:
        parsed = urlparse((url or "").strip())
        host = (parsed.hostname or "").strip().lower()
        return host in ("127.0.0.1", "localhost", "")
    except Exception:
        return False


def _check_memos_health(base_url: str, timeout_sec: float = 2.0) -> bool:
    """Return True if GET base_url/health returns 200."""
    try:
        import httpx
        url = (base_url.rstrip("/") + "/health")
        r = httpx.get(url, timeout=timeout_sec)
        return r.status_code == 200
    except Exception:
        return False


def _start_memos_process(memos_dir: str) -> Optional[subprocess.Popen]:
    """Start MemOS standalone server (npm run standalone or npx tsx server-standalone.ts). Return Popen or None."""
    if not memos_dir or not os.path.isdir(memos_dir):
        return None
    standalone_ts = os.path.join(memos_dir, "server-standalone.ts")
    package_json = os.path.join(memos_dir, "package.json")
    if not os.path.isfile(standalone_ts):
        return None

    # Prefer npm run standalone (uses local tsx from node_modules)
    cmd = None
    if os.path.isfile(package_json):
        try:
            import json
            with open(package_json, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            scripts = (pkg.get("scripts") or {})
            if (scripts.get("standalone") or "").strip():
                cmd = ["npm", "run", "standalone"]
        except Exception:
            pass
    if not cmd:
        cmd = ["npx", "tsx", "server-standalone.ts"]

    try:
        env = os.environ.copy()
        # MemOS standalone reads PORT from env; default in server is 39201
        proc = subprocess.Popen(
            cmd,
            cwd=memos_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=_CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        logger.info("MemOS standalone server started (PID {}). See vendor/memos for logs.", proc.pid)
        return proc
    except FileNotFoundError:
        logger.debug("MemOS: npm/npx not found; start server manually: cd vendor/memos && npm run standalone")
        return None
    except Exception as e:
        logger.warning("MemOS: failed to start server: {}", e)
        return None


def ensure_memos_server_started(config: Any) -> bool:
    """
    If memos.url is local and auto_start is true, ensure the MemOS server is running:
    probe /health; if not 200, start the server subprocess and wait until healthy or timeout.
    Returns True if the server is (or was) running, False otherwise.
    Never raises; logs and returns False on any error.
    """
    try:
        if config is None or not isinstance(config, dict):
            return False
        url = (config.get("url") or "").strip()
        if not url:
            return False
        auto_start = config.get("auto_start", True)
        if auto_start is False:
            return False
        if isinstance(auto_start, str) and (auto_start.strip().lower() in ("false", "0", "no")):
            return False
        if not _is_local_url(url):
            return False

        if _check_memos_health(url):
            return True

        root = _find_project_root()
        if not root:
            return False
        memos_dir = os.path.join(root, "vendor", "memos")
        proc = _start_memos_process(memos_dir)
        if not proc:
            return False

        # Wait for server to become ready (up to 15s)
        for _ in range(15):
            time.sleep(1)
            if _check_memos_health(url):
                return True
            if proc.poll() is not None:
                break
        logger.warning("MemOS server did not become ready in time. Start manually: cd vendor/memos && npm run standalone")
        return False
    except Exception as e:
        logger.debug("ensure_memos_server_started: {}", e)
        return False


def _find_project_root() -> Optional[str]:
    """Return project root (directory containing main.py and vendor/memos)."""
    try:
        from base.util import Util
        root = Util().root_path()
        if root and os.path.isdir(os.path.join(root, "vendor", "memos")):
            return root
    except Exception:
        pass
    # Fallback: walk up from this file
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        if d and os.path.isfile(os.path.join(d, "main.py")) and os.path.isdir(os.path.join(d, "vendor", "memos")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None
