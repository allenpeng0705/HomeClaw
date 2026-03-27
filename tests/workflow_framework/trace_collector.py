from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .trace_schema import validate_event


def load_trace_jsonl(path: Path) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    if not path.is_file():
        return events
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            events.append(obj)
    return events


def validate_trace(events: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    last_seq = -1
    for i, e in enumerate(events):
        vr = validate_event(e)
        if not vr.ok:
            errors.extend([f"event[{i}]: {x}" for x in vr.errors])
        try:
            seq = int(e.get("sequence"))
            if seq <= last_seq:
                errors.append(f"event[{i}]: non-increasing sequence ({seq} <= {last_seq})")
            last_seq = seq
        except Exception:
            errors.append(f"event[{i}]: invalid sequence")
    return errors

