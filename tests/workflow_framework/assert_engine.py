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
    return AssertionResult(ok=(len(errs) == 0), errors=errs)

