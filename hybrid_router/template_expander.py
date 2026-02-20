"""
Template-to-keywords and template-to-regex for Layer 1 heuristic rules.

Supports {{open|launch|start}} {{browser|app}} style templates:
  - expand_template(tmpl) -> list of all phrase permutations (for keyword list).
  - template_to_regex(tmpl) -> regex pattern with \\b boundaries (for whole-word match).

Safety: Reject templates containing {{.*}} or similar greedy patterns to avoid
shadowing (matching everything). Templates must be specific (finite alternatives only).
"""
from __future__ import annotations

import re
from itertools import product

# Forbidden in template alternatives (would cause over-match)
_GREEDY_PATTERN = re.compile(r"\.\*|\.\+|\{\s*\.\*", re.IGNORECASE)
_MAX_EXPANSIONS = 2000  # cap per template to avoid explosion


def expand_template(template: str) -> list[str]:
    """
    Expand a string like '{{open|launch}} the {{browser|app}}' into all combinations.
    - {{a|b|c}} → alternatives; literal text outside is preserved.
    - Normalizes whitespace to single space; strips each result.
    - Returns at most _MAX_EXPANSIONS items; rejects greedy patterns.
    """
    if not template or not isinstance(template, str):
        return []
    if _GREEDY_PATTERN.search(template):
        return []
    parts = re.split(r"(\{\{[^}]+\}\})", template)
    options: list[list[str]] = []
    for part in parts:
        if part.startswith("{{") and part.endswith("}}"):
            # Don't strip options so "{{a |}}" keeps "a " (optional "a " vs empty)
            opts = [p if p is not None else "" for p in part[2:-2].split("|")]
            if not opts:
                opts = [""]
            options.append(opts)
        else:
            options.append([part])
    combinations = ["".join(items).strip() for items in product(*options)]
    out = [re.sub(r"\s+", " ", c).strip() for c in combinations if c]
    return out[:_MAX_EXPANSIONS]


def template_to_regex(template: str) -> str | None:
    """
    Build a regex pattern for the template with word boundaries (\\b).
    E.g. {{take|capture}} {{screenshot|screen}} -> \\b(take|capture)\\s+(screenshot|screen)\\b
    So matching is whole-word and optimized for re.search(). Returns None if greedy.
    """
    if not template or not isinstance(template, str):
        return None
    if _GREEDY_PATTERN.search(template):
        return None
    parts = re.split(r"(\{\{[^}]+\}\})", template)
    regex_parts: list[str] = []
    for part in parts:
        if part.startswith("{{") and part.endswith("}}"):
            opts = [p.strip() for p in part[2:-2].split("|") if p is not None]
            if not opts:
                regex_parts.append(r"\s*")
            else:
                escaped = [re.escape(p) for p in opts if p]
                if not escaped:
                    regex_parts.append(r"\s*")
                else:
                    regex_parts.append("(" + "|".join(escaped) + ")")
        else:
            if part:
                regex_parts.append(re.escape(part))
    if not regex_parts:
        return None
    # One or more whitespace between parts; wrap in word boundaries for whole-word match
    pattern = r"\s+".join(regex_parts)
    return r"\b" + pattern + r"\b"


def expand_rule_templates(rule: dict) -> dict:
    """
    If rule has 'tmpl' (or 'templates' list), expand to keywords and merge into 'keywords'.
    Returns a new rule dict with only 'route' and 'keywords' (no 'tmpl').
    """
    route = (rule.get("route") or "local").strip().lower()
    if route not in ("local", "cloud"):
        route = "local"
    keywords = list(rule.get("keywords") or [])
    tmpls = rule.get("tmpl")
    if isinstance(tmpls, str):
        tmpls = [tmpls]
    elif not isinstance(tmpls, list):
        tmpls = []
    for t in tmpls:
        if not t or not isinstance(t, str):
            continue
        for phrase in expand_template(t):
            if phrase and phrase not in keywords:
                keywords.append(phrase)
    return {"route": route, "keywords": keywords}
