"""
Per-request routing logs and aggregated counts for mix mode and cloud usage.
Used for cost visibility and reporting (Step 6–7).
"""
import csv
import io
import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

# In-memory counters (thread-safe). Router: only when main_llm_mode == "mix". Cloud: every completion with cloud model.
_lock = threading.Lock()
_total_mix_requests = 0
_routed_local = 0
_routed_cloud = 0
_by_layer: Dict[str, int] = {
    "heuristic": 0,
    "semantic": 0,
    "classifier": 0,
    "perplexity": 0,
    "default_route": 0,
}
# Cloud usage: incremented on every chat completion that uses a cloud model (mix routed to cloud + single cloud mode).
_cloud_requests_total = 0


def log_router_decision(
    route: str,
    layer: str,
    score: float = 0.0,
    reason: str = "",
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> None:
    """Write one structured log line for a mix-mode routing decision and increment counters."""
    if route not in ("local", "cloud"):
        return
    payload = {
        "event": "hybrid_router_decision",
        "route": route,
        "layer": layer,
        "score": round(score, 4),
        "reason": (reason or "")[:200],
    }
    if request_id:
        payload["request_id"] = request_id
    if session_id:
        payload["session_id"] = session_id
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    logger.info("Router decision: {}", json.dumps(payload, ensure_ascii=False))

    with _lock:
        global _total_mix_requests, _routed_local, _routed_cloud, _by_layer
        _total_mix_requests += 1
        if route == "local":
            _routed_local += 1
        else:
            _routed_cloud += 1
        layer_key = layer if layer in _by_layer else "default_route"
        _by_layer[layer_key] = _by_layer.get(layer_key, 0) + 1


def get_router_stats() -> Dict[str, Any]:
    """Return current aggregated counts for mix-mode router (for reports)."""
    with _lock:
        return {
            "total_mix_requests": _total_mix_requests,
            "routed_local": _routed_local,
            "routed_cloud": _routed_cloud,
            "by_layer": dict(_by_layer),
        }


def reset_router_stats() -> None:
    """Reset router counters (e.g. for tests)."""
    with _lock:
        global _total_mix_requests, _routed_local, _routed_cloud, _by_layer
        _total_mix_requests = 0
        _routed_local = 0
        _routed_cloud = 0
        _by_layer = {"heuristic": 0, "semantic": 0, "classifier": 0, "default_route": 0}


def log_cloud_usage() -> None:
    """Call when a chat completion uses a cloud model (mix routed to cloud or single cloud mode). Increments total."""
    with _lock:
        global _cloud_requests_total
        _cloud_requests_total += 1


def get_cloud_usage_stats() -> Dict[str, Any]:
    """Return cloud usage counts for reports."""
    with _lock:
        return {"cloud_requests_total": _cloud_requests_total}


def reset_cloud_usage_stats() -> None:
    """Reset cloud usage counters (e.g. for tests)."""
    with _lock:
        global _cloud_requests_total
        _cloud_requests_total = 0


def generate_usage_report(format: str = "json") -> Dict[str, Any] | str:
    """
    Build a single report from router stats + cloud usage. format='json' returns the dict; format='csv' returns a CSV string.
    Use for REST API and tools.
    """
    router = get_router_stats()
    cloud = get_cloud_usage_stats()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "router": router,
        "cloud_usage": cloud,
        "summary": {
            "total_cloud_requests": cloud["cloud_requests_total"],
            "mix_requests": router["total_mix_requests"],
            "mix_routed_local": router["routed_local"],
            "mix_routed_cloud": router["routed_cloud"],
        },
    }
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["section", "key", "value"])
        w.writerow(["summary", "generated_at", report["generated_at"]])
        w.writerow(["summary", "total_cloud_requests", report["summary"]["total_cloud_requests"]])
        w.writerow(["summary", "mix_requests", report["summary"]["mix_requests"]])
        w.writerow(["summary", "mix_routed_local", report["summary"]["mix_routed_local"]])
        w.writerow(["summary", "mix_routed_cloud", report["summary"]["mix_routed_cloud"]])
        for k, v in report["router"].items():
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    w.writerow(["router", f"{k}.{k2}", v2])
            else:
                w.writerow(["router", k, v])
        for k, v in report["cloud_usage"].items():
            w.writerow(["cloud_usage", k, v])
        return buf.getvalue()
    return report
