from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AssertionResult:
    ok: bool
    errors: List[str]


def _event_matches(event: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    for k, v in expected.items():
        if k == "details_contains":
            det = event.get("details") if isinstance(event.get("details"), dict) else {}
            if not isinstance(det, dict):
                return False
            for dk, dv in (v or {}).items():
                if det.get(dk) != dv:
                    return False
        elif event.get(k) != v:
            return False
    return True


def assert_contract(events: List[Dict[str, Any]], contract: Dict[str, Any]) -> AssertionResult:
    errs: List[str] = []
    must_have = contract.get("must_have_events") or []
    for idx, need in enumerate(must_have):
        if not isinstance(need, dict):
            continue
        if not any(_event_matches(e, need) for e in events):
            errs.append(f"missing required event[{idx}]: {need}")
    forbidden = contract.get("forbidden_events") or []
    for idx, bad in enumerate(forbidden):
        if not isinstance(bad, dict):
            continue
        if any(_event_matches(e, bad) for e in events):
            errs.append(f"forbidden event seen[{idx}]: {bad}")

    # Optional flexible matcher: each group passes if any event spec in that group is found.
    # Example:
    # must_have_any_of:
    #   - [ {event_type: tool_call_started, ...}, {event_type: model_selected, ...} ]
    must_have_any_of = contract.get("must_have_any_of") or []
    for gidx, group in enumerate(must_have_any_of):
        if not isinstance(group, list) or not group:
            continue
        matched = False
        for opt in group:
            if not isinstance(opt, dict):
                continue
            if any(_event_matches(e, opt) for e in events):
                matched = True
                break
        if not matched:
            errs.append(f"missing required any_of group[{gidx}]: {group}")
    return AssertionResult(ok=(len(errs) == 0), errors=errs)

