"""
System plugins startup: discover, wait for Core ready, run plugin processes and register.
Extracted from core/core.py (Phase 7 refactor). Takes core as first argument; no import of core.core.
"""

import asyncio
import json
import os
import time
from typing import Any, Dict, List

import httpx
from loguru import logger

from base.util import Util
from core.log_helpers import _component_log


def _discover_system_plugins(core: Any) -> List[Dict]:
    """Discover plugins in system_plugins/ that have register.js and a server (server.js or package.json start). Returns list of {id, cwd, start_argv, register_argv}."""
    root = Util().root_path()
    base = getattr(Util(), "system_plugins_path", lambda: os.path.join(root, "system_plugins"))()
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if name.startswith("."):
            continue
        folder = os.path.join(base, name)
        if not os.path.isdir(folder):
            continue
        register_js = os.path.join(folder, "register.js")
        server_js = os.path.join(folder, "server.js")
        pkg_json = os.path.join(folder, "package.json")
        if not os.path.isfile(register_js):
            continue
        start_argv = None
        if os.path.isfile(server_js):
            start_argv = ["node", "server.js"]
        elif os.path.isfile(pkg_json):
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                scripts = (pkg.get("scripts") or {})
                start_script = (scripts.get("start") or "").strip()
                if start_script:
                    # "node server.js" -> ["node", "server.js"]; "npm run x" -> ["npm", "run", "x"]
                    parts = start_script.split()
                    if parts and parts[0] == "node" and len(parts) >= 2:
                        start_argv = parts
                    elif parts and parts[0] == "npm":
                        start_argv = ["npm", "start"]
            except Exception:
                pass
        if not start_argv:
            continue
        out.append({
            "id": name,
            "cwd": folder,
            "start_argv": start_argv,
            "register_argv": ["node", "register.js"],
        })
    return out


async def _wait_for_core_ready(core: Any, base_url: str, timeout_sec: float = 60.0, interval_sec: float = 0.5) -> bool:
    """Poll GET {base_url}/ready until Core responds 200 or timeout. Uses /ready (lightweight) so DB/plugins don't delay readiness."""
    url = (base_url.rstrip("/") + "/ready")
    deadline = time.monotonic() + timeout_sec
    last_err = None
    logged_non200 = False
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return True
                last_err = f"status {r.status_code}"
                # 503 = Core still initializing (expected). Log WARNING only for unexpected codes (e.g. 502).
                if r.status_code != 503 and not logged_non200:
                    logged_non200 = True
                    try:
                        body_preview = (r.text or "")[:200]
                    except Exception:
                        body_preview = ""
                    logger.warning(
                        "system_plugins: GET {} returned {} (body: {}). If timeout, something else may be handling this URL.",
                        url, r.status_code, body_preview or "(empty)",
                    )
        except Exception as e:
            last_err = e
        await asyncio.sleep(interval_sec)
    if last_err is not None:
        logger.debug("system_plugins: last ready probe failed: {}", last_err)
    return False


async def _run_system_plugins_startup(core: Any) -> None:
    """Start each discovered system plugin (server process) then run register. Waits for Core to be ready first.
    Called via asyncio.create_task() so it runs in the background and does not block Core or the HTTP server.
    Each plugin runs in a separate OS process (node server.js)."""
    meta = Util().get_core_metadata()
    allowlist = getattr(meta, "system_plugins", None) or []
    candidates = _discover_system_plugins(core)
    if not candidates:
        return
    to_start = [c for c in candidates if not allowlist or c["id"] in allowlist]
    if not to_start:
        return
    core_url = f"http://{meta.host}:{meta.port}"
    base_env = os.environ.copy()
    base_env["CORE_URL"] = core_url
    if getattr(meta, "auth_enabled", False) and getattr(meta, "auth_api_key", ""):
        base_env["CORE_API_KEY"] = getattr(meta, "auth_api_key", "")
    plugin_env_config = getattr(meta, "system_plugins_env", None) or {}
    # Give the HTTP server a moment to bind (avoids "Core did not become ready" on Windows where the task can poll before server.serve() is listening).
    await asyncio.sleep(2)
    # Wait for Core to be ready so registration succeeds (poll GET /ready until 200).
    # Use 127.0.0.1 for the probe when host is 0.0.0.0 so readiness works on Windows (connecting to 0.0.0.0 often fails there).
    ready_host = "127.0.0.1" if (getattr(meta, "host", None) or "").strip() in ("0.0.0.0", "") else meta.host
    ready_url = f"http://{ready_host}:{meta.port}"
    timeout_ready = max(30.0, float(getattr(meta, "system_plugins_ready_timeout", 90) or 90))
    ready = await _wait_for_core_ready(core, ready_url, timeout_sec=timeout_ready)
    if not ready:
        logger.warning("system_plugins: Core did not become ready in time; starting plugins anyway.")
    else:
        _component_log("system_plugins", "Core ready, starting plugin(s)")
    for item in to_start:
        cwd = item["cwd"]
        start_argv = item["start_argv"]
        env = {**base_env}
        for k, v in plugin_env_config.get(item["id"], {}).items():
            env[k] = v
        try:
            proc = await asyncio.create_subprocess_exec(
                start_argv[0],
                *start_argv[1:],
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            core._system_plugin_processes.append(proc)
            _component_log("system_plugins", f"started {item['id']} (pid={proc.pid})")
        except Exception as e:
            logger.warning("system_plugins: failed to start {}: {}", item["id"], e)
    delay = max(0.5, float(getattr(meta, "system_plugins_start_delay", 2) or 2))
    await asyncio.sleep(delay)
    for item in to_start:
        env = {**base_env}
        for k, v in plugin_env_config.get(item["id"], {}).items():
            env[k] = v
        try:
            reg = await asyncio.create_subprocess_exec(
                "node", "register.js",
                cwd=item["cwd"],
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await reg.communicate()
            if reg.returncode == 0:
                _component_log("system_plugins", f"registered {item['id']}")
            else:
                logger.debug("system_plugins: register {} stderr: {}", item["id"], (stderr or b"").decode(errors="replace")[:500])
        except Exception as e:
            logger.debug("system_plugins: register {} failed: {}", item["id"], e)
