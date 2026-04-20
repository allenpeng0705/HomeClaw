"""
Per-request routing logs and aggregated counts for mix mode and cloud usage.
Used for cost visibility and reporting (Step 6–7).
Supports A/B experiment assignment and persistent counters (flushed to JSON file).
"""
import csv
import io
import json
import os
import threading
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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

# --- A/B Experiment tracking ---
# Per-experiment counters: experiment_id -> {route -> count, by_layer -> {layer -> count}}
_experiments: Dict[str, Dict[str, Any]] = {}
# Experiment definitions from config: list of {id, name, salt, description}
_experiment_defs: List[Dict[str, str]] = []
# Salt for experiment assignment hashing (derived from experiment ID to keep deterministic but resistant to gaming)
_default_experiment_salt = "homeclaw-hybrid-router-v1"


def _experiment_hash(experiment_id: str, user_id: str, salt: str) -> float:
    """
    Deterministically assign a user to [0, 1) for an experiment using HMAC-like hash.
    Uses experiment_id + salt + user_id to produce a stable float.
    """
    msg = f"{experiment_id}:{salt}:{user_id or ''}"
    h = hashlib.sha256(msg.encode("utf-8")).hexdigest()
    # Take first 8 bytes as int, normalize to [0, 1)
    val = int(h[:8], 16)
    return val / (16 ** 8)


def set_experiment_defs(experiments: List[Dict[str, Any]]) -> None:
    """Set A/B experiment definitions from config. Call at startup."""
    global _experiment_defs
    with _lock:
        _experiment_defs = []
        for exp in experiments or []:
            if not isinstance(exp, dict):
                continue
            eid = str(exp.get("id") or "").strip()
            if not eid:
                continue
            _experiment_defs.append({
                "id": eid,
                "name": str(exp.get("name") or eid).strip(),
                "salt": str(exp.get("salt") or f"{_default_experiment_salt}:{eid}").strip(),
                "description": str(exp.get("description") or "").strip(),
            })


def get_experiment_for_user(experiment_id: str, user_id: str) -> Optional[str]:
    """
    Assign user to 'treatment' or 'control' group for an experiment.
    Returns 'treatment', 'control', or None if experiment not found.
    """
    if not experiment_id or not user_id:
        return None
    exp_def = next((e for e in _experiment_defs if e["id"] == experiment_id), None)
    if not exp_def:
        return None
    bucket = _experiment_hash(experiment_id, user_id, exp_def["salt"])
    return "treatment" if bucket < 0.5 else "control"


def log_experiment_decision(
    experiment_id: str,
    group: str,
    route: str,
    layer: str,
    score: float = 0.0,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """Log a routing decision for an A/B experiment."""
    if experiment_id not in _experiments:
        with _lock:
            if experiment_id not in _experiments:
                _experiments[experiment_id] = {
                    "treatment": {"total": 0, "routed_local": 0, "routed_cloud": 0, "by_layer": {}},
                    "control": {"total": 0, "routed_local": 0, "routed_cloud": 0, "by_layer": {}},
                }
    with _lock:
        grp = _experiments[experiment_id].get(group)
        if not grp:
            return
        grp["total"] += 1
        if route == "local":
            grp["routed_local"] += 1
        else:
            grp["routed_cloud"] += 1
        layer_key = layer if layer in grp["by_layer"] else "default_route"
        grp["by_layer"][layer_key] = grp["by_layer"].get(layer_key, 0) + 1


def get_experiment_stats(experiment_id: Optional[str] = None) -> Dict[str, Any]:
    """Return experiment metrics. If experiment_id is None, return all."""
    with _lock:
        if experiment_id:
            return dict(_experiments.get(experiment_id, {}))
        return {k: dict(v) for k, v in _experiments.items()}


def reset_experiment_stats(experiment_id: Optional[str] = None) -> None:
    """Reset experiment counters. If experiment_id is None, reset all."""
    with _lock:
        if experiment_id:
            if experiment_id in _experiments:
                _experiments[experiment_id] = {
                    "treatment": {"total": 0, "routed_local": 0, "routed_cloud": 0, "by_layer": {}},
                    "control": {"total": 0, "routed_local": 0, "routed_cloud": 0, "by_layer": {}},
                }
        else:
            _experiments.clear()


# --- Persistent counters ---
# Path to flush counters to JSON (set by init_metrics_persistence)
_persist_path: Optional[Path] = None
_persist_interval_seconds = 300  # flush every 5 minutes
_persist_thread: Optional[threading.Thread] = None
_persist_shutdown = threading.Event()


def init_metrics_persistence(persist_path: Optional[str] = None, flush_interval_seconds: int = 300) -> None:
    """
    Initialize persistent counter storage. If persist_path is set, counters are
    loaded from that JSON file on startup and periodically flushed back to it.
    Call once at app startup.
    """
    global _persist_path, _persist_interval_seconds, _persist_thread
    if not persist_path:
        return
    _persist_path = Path(persist_path)
    _persist_interval_seconds = max(30, flush_interval_seconds)
    _load_counters()
    _start_flush_thread()


def _persist_path_default() -> Path:
    """Default path for metrics persistence."""
    from base.util import Util
    root = Path(Util().root_path()).resolve()
    return root / "data" / "hybrid_router_metrics.json"


def _load_counters() -> None:
    """Load counters from JSON file if it exists."""
    global _total_mix_requests, _routed_local, _routed_cloud, _by_layer, _cloud_requests_total
    path = _persist_path or _persist_path_default()
    if not path.is_file():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return
        with _lock:
            _total_mix_requests = int(data.get("total_mix_requests", 0) or 0)
            _routed_local = int(data.get("routed_local", 0) or 0)
            _routed_cloud = int(data.get("routed_cloud", 0) or 0)
            _cloud_requests_total = int(data.get("cloud_requests_total", 0) or 0)
            _by_layer = dict(data.get("by_layer") or {
                "heuristic": 0, "semantic": 0, "classifier": 0,
                "perplexity": 0, "default_route": 0,
            })
        logger.debug("Hybrid router metrics loaded from {}", path)
    except Exception as e:
        logger.warning("Failed to load hybrid router metrics from {}: {}", path, e)


def _flush_counters() -> None:
    """Write current counters to JSON file."""
    path = _persist_path or _persist_path_default()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            data = {
                "total_mix_requests": _total_mix_requests,
                "routed_local": _routed_local,
                "routed_cloud": _routed_cloud,
                "cloud_requests_total": _cloud_requests_total,
                "by_layer": dict(_by_layer),
                "flushed_at": datetime.now(timezone.utc).isoformat(),
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.debug("Hybrid router metrics flushed to {}", path)
    except Exception as e:
        logger.warning("Failed to flush hybrid router metrics to {}: {}", path, e)


def _start_flush_thread() -> None:
    """Start background thread to periodically flush counters."""
    global _persist_thread, _persist_shutdown
    if _persist_thread and _persist_thread.is_alive():
        return
    _persist_shutdown.clear()
    def _flush_loop():
        while not _persist_shutdown.wait(_persist_interval_seconds):
            _flush_counters()
    _persist_thread = threading.Thread(target=_flush_loop, daemon=True, name="hybrid-router-metrics-flush")
    _persist_thread.start()
    logger.info("Hybrid router metrics persistence thread started (flush every {}s)", _persist_interval_seconds)


def shutdown_metrics_persistence() -> None:
    """Stop persistence thread and do a final flush. Call at app shutdown."""
    global _persist_thread, _persist_shutdown
    _persist_shutdown.set()
    if _persist_thread:
        _persist_thread.join(timeout=5.0)
        _persist_thread = None
    _flush_counters()
    logger.info("Hybrid router metrics persistence shut down")


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
    """Reset router counters (e.g. for tests). Does not affect persisted file."""
    with _lock:
        global _total_mix_requests, _routed_local, _routed_cloud, _by_layer
        _total_mix_requests = 0
        _routed_local = 0
        _routed_cloud = 0
        _by_layer = {"heuristic": 0, "semantic": 0, "classifier": 0, "perplexity": 0, "default_route": 0}


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
    Build a single report from router stats + cloud usage + experiments.
    format='json' returns the dict; format='csv' returns a CSV string.
    Use for REST API and tools.
    """
    router = get_router_stats()
    cloud = get_cloud_usage_stats()
    experiments = get_experiment_stats()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "router": router,
        "cloud_usage": cloud,
        "experiments": experiments,
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
        for exp_id, exp_data in report["experiments"].items():
            for group, grp_data in (exp_data or {}).items():
                if isinstance(grp_data, dict):
                    for k2, v2 in grp_data.items():
                        w.writerow(["experiment", f"{exp_id}.{group}.{k2}", v2])
                else:
                    w.writerow(["experiment", f"{exp_id}.{group}", grp_data])
        return buf.getvalue()
    return report
