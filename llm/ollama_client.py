"""
Ollama HTTP API client for listing and pulling models. Used by CLI (main ollama list/pull/set-main)
and can be used by UI. No process spawning; only HTTP calls. Defensive: never raises; returns empty/False on error.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# Default Ollama server (no config dependency in this module)
DEFAULT_OLLAMA_HOST = "127.0.0.1"
DEFAULT_OLLAMA_PORT = 11434


def _base_url(host: str, port: int) -> str:
    host = (host or "").strip() or DEFAULT_OLLAMA_HOST
    try:
        port = max(1, min(65535, int(port)))
    except (TypeError, ValueError):
        port = DEFAULT_OLLAMA_PORT
    return f"http://{host}:{port}"


def list_models(host: str = DEFAULT_OLLAMA_HOST, port: int = DEFAULT_OLLAMA_PORT, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """
    GET /api/tags from Ollama server. Returns list of dicts with at least 'name', optionally 'size', 'modified_at', 'details'.
    On error (connection, timeout, non-JSON) returns [] and logs at debug. Never raises.
    """
    try:
        import httpx
        url = f"{_base_url(host, port)}/api/tags"
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url)
            if r.status_code != 200:
                logger.debug("Ollama GET /api/tags returned {}: {}", r.status_code, r.text[:200] if r.text else "")
                return []
            data = r.json()
            if not isinstance(data, dict):
                return []
            models = data.get("models")
            if not isinstance(models, list):
                return []
            return [m for m in models if isinstance(m, dict) and (m.get("name") or m.get("model"))]
    except Exception as e:
        logger.debug("Ollama list_models failed: {}", e)
        return []


def pull_model(
    name: str,
    host: str = DEFAULT_OLLAMA_HOST,
    port: int = DEFAULT_OLLAMA_PORT,
    timeout: float = 600.0,
    on_status: Optional[Any] = None,
) -> bool:
    """
    POST /api/pull with {"model": name}. Ollama returns a streaming response (ndjson or JSON) with status/digest/etc.
    If on_status is callable(status_dict), call it for each chunk (for progress). Returns True if pull completed
    successfully (we look for "status": "success" in the stream or a final success). Returns False on error or timeout.
    Never raises.
    """
    name = (name or "").strip()
    if not name:
        logger.warning("Ollama pull_model: empty model name")
        return False
    try:
        import httpx
        url = f"{_base_url(host, port)}/api/pull"
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, json={"model": name}) as resp:
                if resp.status_code != 200:
                    logger.debug("Ollama POST /api/pull returned {}", resp.status_code)
                    return False
                success = False
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        import json
                        chunk = json.loads(line)
                        if isinstance(chunk, dict):
                            if chunk.get("status") == "success":
                                success = True
                            if callable(on_status):
                                try:
                                    on_status(chunk)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                return success
    except Exception as e:
        logger.debug("Ollama pull_model failed: {}", e)
        return False


def get_default_host_port(meta: Any) -> Tuple[str, int]:
    """
    From Core metadata (local_models with type ollama) or defaults, return (host, port).
    meta can be None or an object with local_models list. Never raises.
    """
    host = DEFAULT_OLLAMA_HOST
    port = DEFAULT_OLLAMA_PORT
    try:
        local = getattr(meta, "local_models", None) or []
        if not isinstance(local, list):
            return (host, port)
        for m in local:
            if not isinstance(m, dict):
                continue
            if str(m.get("type") or "").strip().lower() == "ollama":
                host = str(m.get("host") or host).strip() or host
                try:
                    port = max(1, min(65535, int(m.get("port", port))))
                except (TypeError, ValueError):
                    pass
                return (host, port)
    except Exception:
        pass
    return (host, port)


def sanitize_ollama_id(model_name: str) -> str:
    """Build a safe local_models id from Ollama model name (e.g. qwen2.5:7b -> Ollama-qwen2-5-7b)."""
    s = (model_name or "").strip()
    if not s:
        return "Ollama-default"
    s = re.sub(r"[^\w.\-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return f"Ollama-{s}" if s else "Ollama-default"
