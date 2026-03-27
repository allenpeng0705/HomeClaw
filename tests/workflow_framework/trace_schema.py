from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


TRACE_SCHEMA_VERSION = "1.0"

ALLOWED_EVENT_TYPES = {
    "turn_started",
    "model_selected",
    "intent_router_decision",
    "tool_call_started",
    "tool_call_finished",
    "skill_call_started",
    "skill_call_finished",
    "plugin_call_started",
    "plugin_call_finished",
    "arg_normalization",
    "fallback_applied",
    "llm_response_received",
    "turn_finished",
}

REQUIRED_EVENT_FIELDS = {
    "schema_version",
    "run_id",
    "turn_id",
    "timestamp",
    "sequence",
    "event_type",
    "component",
    "summary",
    "details",
}


@dataclass
class TraceValidationResult:
    ok: bool
    errors: List[str]


def validate_event(event: Dict[str, Any]) -> TraceValidationResult:
    errs: List[str] = []
    if not isinstance(event, dict):
        return TraceValidationResult(False, ["event is not an object"])
    missing = [k for k in REQUIRED_EVENT_FIELDS if k not in event]
    if missing:
        errs.append(f"missing required fields: {', '.join(sorted(missing))}")
    if event.get("schema_version") != TRACE_SCHEMA_VERSION:
        errs.append(
            f"invalid schema_version: expected {TRACE_SCHEMA_VERSION}, got {event.get('schema_version')!r}"
        )
    et = str(event.get("event_type") or "")
    if et and et not in ALLOWED_EVENT_TYPES:
        errs.append(f"unsupported event_type: {et}")
    if not isinstance(event.get("details", {}), dict):
        errs.append("details must be an object")
    return TraceValidationResult(ok=(len(errs) == 0), errors=errs)

