"""
Layer 1: Heuristic router. Config-driven keyword and long-input rules.
Multi-language via alias mapping; input normalized (lowercase + Unicode NFC).
User-addable rules via YAML file (e.g. config/hybrid/heuristic_rules.yml).
Supports {{open|launch}} {{browser|app}} templates: expanded to keywords at load time.
"""
import re
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


def _keyword_needs_word_boundary(kw: str) -> bool:
    """
    Returns True if the keyword should use word-boundary regex matching.
    Single-word ASCII letter-only keywords (e.g. 'cpu', 'password') get word boundaries
    to avoid false positives like 'CPU prices' matching 'cpu'.
    Keywords with spaces, non-ASCII (Chinese), non-letter chars (e.g. '.pdf', 'api_key',
    'take a screenshot') use substring matching to avoid under-matching.
    """
    if not kw:
        return False
    # Contains any non-ASCII or non-letter characters → use substring
    if not kw.isascii():
        return False
    if not kw.isalpha():
        # Has digits, underscores, hyphens, etc. → use substring (e.g. api_key, .pdf, cpu1)
        return False
    # Has spaces → phrase, use substring
    if " " in kw:
        return False
    # Single-word ASCII letter-only keyword → needs word boundary
    return True


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
    threshold: float = 0.5,  # unused; kept for backward compatibility
) -> Tuple[float, Optional[str]]:
    """
    Run Layer 1 heuristic on user message only.
    Returns (score, selection). selection is "local" | "cloud" or None.
    - If not enabled: return (0.0, None).
    - If rules_data is None or empty: return (0.0, None).
    - If long_input_chars > 0 and len(query) > long_input_chars: return (1.0, long_input_route).
    - If any rule's keyword matches normalized query:
        - Single-word ASCII keywords (e.g. 'cpu', 'password') use word-boundary regex to avoid false positives.
        - Phrases, Chinese, or special-char keywords use substring match.
      → return (1.0, rule.route).
    - Otherwise: return (0.0, None).
    No threshold: first match (long-input or keyword) wins.
    """
    if not enabled:
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
            kw_norm = _normalize(kw)
            if _keyword_needs_word_boundary(kw):
                # Single-word ASCII keyword: use word boundary to avoid false positives
                # (e.g. 'cpu' should not match 'CPU prices')
                try:
                    pattern = r"\b" + re.escape(kw_norm) + r"\b"
                    if re.search(pattern, normalized_query):
                        return (1.0, route)
                except re.error:
                    # Fall back to substring on invalid pattern
                    if kw_norm in normalized_query:
                        return (1.0, route)
            else:
                # Phrase, Chinese, or special-char keyword: use substring match
                if kw_norm in normalized_query:
                    return (1.0, route)

    return (0.0, None)
