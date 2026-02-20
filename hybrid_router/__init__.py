# Hybrid router: 3-layer smart routing for mix mode (local vs cloud main LLM).
# Layer 1: heuristic (keywords, long-input); Layer 2: semantic; Layer 3: small local classifier.

from hybrid_router.heuristic import load_heuristic_rules, run_heuristic_layer
from hybrid_router.metrics import (
    generate_usage_report,
    get_cloud_usage_stats,
    get_router_stats,
    log_cloud_usage,
    log_router_decision,
    reset_cloud_usage_stats,
    reset_router_stats,
)

__all__ = [
    "load_heuristic_rules",
    "run_heuristic_layer",
    "get_router_stats",
    "log_router_decision",
    "reset_router_stats",
    "log_cloud_usage",
    "get_cloud_usage_stats",
    "reset_cloud_usage_stats",
    "generate_usage_report",
]
