"""
Layer 1: Heuristic router. Config-driven keyword and long-input rules.
Multi-language via alias mapping; input normalized (lowercase + Unicode NFC).
User-addable rules via YAML file (e.g. config/hybrid/heuristic_rules.yml).
Supports {{open|launch}} {{browser|app}} templates: expanded to keywords at load time.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import unicodedata
import yaml

from hybrid_router.template_expander import expand_rule_templates


def _normalize(text: str) -> str:
    """Lowercase and Unicode NFC normalization for consistent matching."""
    if not text or not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFC", text.strip().lower())


def load_heuristic_rules(rules_path: str, root_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Load heuristic rules from YAML. rules_path can be absolute or relative to root_dir.
    Returns dict with keys: long_input_chars (int, 0=off), long_input_route (str), rules (list of {route, keywords}).
    Returns None if file missing or invalid.
    """
    if not rules_path or not isinstance(rules_path, str):
        return None
    path = Path(rules_path)
    if not path.is_absolute() and root_dir is not None:
        path = Path(root_dir) / path
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    long_input_chars = int(data.get("long_input_chars") or 0)
    long_input_route = (data.get("long_input_route") or "cloud").strip().lower()
    if long_input_route not in ("local", "cloud"):
        long_input_route = "cloud"
    rules_raw = data.get("rules")
    if not isinstance(rules_raw, list):
        rules_raw = []
    rules: List[Dict[str, Any]] = []
    for r in rules_raw:
        if not isinstance(r, dict):
            continue
        # Expand {{a|b}} templates into keywords if present
        expanded = expand_rule_templates(r)
        kw_list = expanded.get("keywords") or []
        if kw_list:
            rules.append({"route": expanded["route"], "keywords": kw_list})
    return {
        "long_input_chars": max(0, long_input_chars),
        "long_input_route": long_input_route,
        "rules": rules,
    }


def run_heuristic_layer(
    query: str,
    rules_data: Optional[Dict[str, Any]],
    enabled: bool = True,
    threshold: float = 0.5,
) -> Tuple[float, Optional[str]]:
    """
    Run Layer 1 heuristic on user message only.
    Returns (score, selection). selection is "local" | "cloud" or None.
    - If not enabled or threshold <= 0: return (0.0, None).
    - If rules_data is None or empty: return (0.0, None).
    - If long_input_chars > 0 and len(query) > long_input_chars: return (1.0, long_input_route).
    - If any rule's keyword (normalized) is a substring of normalized query: return (1.0, rule.route).
    - Otherwise: return (0.0, None).
    """
    if not enabled or (threshold is not None and threshold <= 0):
        return (0.0, None)
    if not rules_data or not isinstance(rules_data, dict):
        return (0.0, None)
    if not query or not isinstance(query, str):
        return (0.0, None)

    normalized_query = _normalize(query)
    long_input_chars = int(rules_data.get("long_input_chars") or 0)
    long_input_route = (rules_data.get("long_input_route") or "cloud").strip().lower()
    if long_input_route not in ("local", "cloud"):
        long_input_route = "cloud"

    if long_input_chars > 0 and len(query) > long_input_chars:
        return (1.0, long_input_route)

    for rule in rules_data.get("rules") or []:
        route = (rule.get("route") or "local").strip().lower()
        if route not in ("local", "cloud"):
            route = "local"
        for kw in rule.get("keywords") or []:
            if not kw:
                continue
            if _normalize(kw) in normalized_query:
                return (1.0, route)

    return (0.0, None)
