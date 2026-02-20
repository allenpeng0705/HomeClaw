#!/usr/bin/env python3
"""
Validate heuristic_rules.yml for keyword conflicts.

Checks that no keyword (after normalization) is assigned to both 'local' and 'cloud'.
Because the router uses first-match-wins, a conflict is confusing: the same word
would route differently depending on rule order. This script helps catch mistakes.

Uses the same normalization as hybrid_router.heuristic (lowercase + Unicode NFC).
Requires: PyYAML (pip install pyyaml). Run from repo root.

Usage:
  python scripts/validate_heuristic_rules.py
  python scripts/validate_heuristic_rules.py path/to/heuristic_rules.yml
Exit code: 0 if valid, 1 if conflicts or load error.
"""
from pathlib import Path
import sys
import unicodedata

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = REPO_ROOT / "config" / "hybrid" / "heuristic_rules.yml"


def _normalize(text: str) -> str:
    """Same as hybrid_router.heuristic: lowercase + Unicode NFC."""
    if not text or not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFC", text.strip().lower())


def load_rules(path: Path):
    """Load YAML and return list of {route, keywords}; None on error."""
    if not path.is_file():
        return None
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    rules_raw = data.get("rules")
    if not isinstance(rules_raw, list):
        return []
    rules = []
    for r in rules_raw:
        if not isinstance(r, dict):
            continue
        route = (r.get("route") or "local").strip().lower()
        if route not in ("local", "cloud"):
            route = "local"
        keywords = r.get("keywords")
        if isinstance(keywords, list):
            kw_list = [str(k).strip() for k in keywords if k]
        elif isinstance(keywords, str):
            kw_list = [keywords.strip()] if keywords.strip() else []
        else:
            kw_list = []
        if kw_list:
            rules.append({"route": route, "keywords": kw_list})
    return rules


def main() -> int:
    rules_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_RULES_PATH
    if not rules_path.is_file():
        print(f"Error: rules file not found: {rules_path}", file=sys.stderr)
        return 1

    rules = load_rules(rules_path)
    if rules is None:
        print("Error: could not load heuristic rules (missing or invalid YAML).", file=sys.stderr)
        print("Tip: pip install pyyaml", file=sys.stderr)
        return 1

    # normalized_keyword -> list of (route, original_keyword)
    by_norm: dict[str, list[tuple[str, str]]] = {}
    for rule in rules:
        route = rule.get("route", "local")
        for kw in rule.get("keywords") or []:
            orig = (kw or "").strip()
            if not orig:
                continue
            norm = _normalize(orig)
            if not norm:
                continue
            by_norm.setdefault(norm, []).append((route, orig))

    local_norms = {n for n, pairs in by_norm.items() if any(r == "local" for r, _ in pairs)}
    cloud_norms = {n for n, pairs in by_norm.items() if any(r == "cloud" for r, _ in pairs)}
    conflicts = local_norms & cloud_norms

    if not conflicts:
        print("OK: No keyword conflicts (no keyword assigned to both local and cloud).")
        return 0

    print("Keyword conflicts: the following normalized keyword(s) appear in both LOCAL and CLOUD rules.", file=sys.stderr)
    print("(Router uses first-match-wins; fix by keeping each keyword in only one route.)\n", file=sys.stderr)
    for norm in sorted(conflicts):
        pairs = by_norm[norm]
        local_examples = [orig for r, orig in pairs if r == "local"]
        cloud_examples = [orig for r, orig in pairs if r == "cloud"]
        print(f"  '{norm}'", file=sys.stderr)
        print(f"    -> local:  {local_examples}", file=sys.stderr)
        print(f"    -> cloud:  {cloud_examples}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
