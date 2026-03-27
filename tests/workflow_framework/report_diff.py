from __future__ import annotations

from typing import Any, Dict, List


def summarize_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in events:
        out.append(
            {
                "sequence": e.get("sequence"),
                "event_type": e.get("event_type"),
                "component": e.get("component"),
                "summary": e.get("summary"),
            }
        )
    return out


def diff_event_summaries(base: List[Dict[str, Any]], cand: List[Dict[str, Any]]) -> Dict[str, Any]:
    max_len = max(len(base), len(cand))
    diffs: List[Dict[str, Any]] = []
    for i in range(max_len):
        b = base[i] if i < len(base) else None
        c = cand[i] if i < len(cand) else None
        if b != c:
            diffs.append({"index": i, "baseline": b, "candidate": c})
    return {"changed": len(diffs) > 0, "diffs": diffs, "baseline_len": len(base), "candidate_len": len(cand)}

