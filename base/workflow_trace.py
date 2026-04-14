from __future__ import annotations

import contextvars
import json
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional live subscribers (SSE). No overhead when empty.
_TRACE_SSE_QUEUES: List[queue.Queue] = []
_FANOUT_LOCK = threading.Lock()


def apply_workflow_trace_env_from_config(meta: Any, *, project_root: str) -> None:
    """Set ``HOMECLAW_WORKFLOW_TRACE`` / ``HOMECLAW_WORKFLOW_TRACE_DIR`` from ``core.yml`` when the
    corresponding env var is not already set (environment always wins). Paths are relative to *project_root*."""
    if meta is None or not (project_root or "").strip():
        return
    try:
        root = os.path.normpath(str(project_root).strip())
        d = (getattr(meta, "workflow_trace_dir", None) or "").strip()
        if d:
            abs_d = d if os.path.isabs(d) else os.path.normpath(os.path.join(root, d))
            if not (os.environ.get("HOMECLAW_WORKFLOW_TRACE_DIR") or "").strip():
                os.environ["HOMECLAW_WORKFLOW_TRACE_DIR"] = abs_d
        if bool(getattr(meta, "workflow_trace_enabled", False)):
            if not (os.environ.get("HOMECLAW_WORKFLOW_TRACE") or "").strip():
                os.environ["HOMECLAW_WORKFLOW_TRACE"] = "1"
    except Exception:
        return


_TRACE_STATE: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "homeclaw_trace_state", default={}
)
_WRITE_LOCK = threading.Lock()


def _truthy(v: Optional[str]) -> bool:
    s = (v or "").strip().lower()
    return s in ("1", "true", "yes", "on")


def _trace_enabled() -> bool:
    return _truthy(os.environ.get("HOMECLAW_WORKFLOW_TRACE"))


def _trace_raw_enabled() -> bool:
    return _truthy(os.environ.get("HOMECLAW_WORKFLOW_TRACE_RAW"))


def _trace_dir() -> Path:
    d = (os.environ.get("HOMECLAW_WORKFLOW_TRACE_DIR") or "output/workflow_traces").strip()
    p = Path(d)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


_SENSITIVE_KEY_RE = re.compile(
    r"(key|token|secret|password|authorization|cookie|api[_-]?key|bearer)",
    re.IGNORECASE,
)


def _redact(obj: Any) -> Any:
    if _trace_raw_enabled():
        return obj
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            kk = str(k)
            if _SENSITIVE_KEY_RE.search(kk):
                out[kk] = "***REDACTED***"
            else:
                out[kk] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    if isinstance(obj, str):
        if len(obj) > 2000:
            return obj[:2000] + "...(truncated)"
        return obj
    return obj


def _next_sequence(state: Dict[str, Any]) -> int:
    n = int(state.get("sequence") or 0) + 1
    state["sequence"] = n
    return n


def start_turn(
    *,
    run_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    query: Optional[str] = None,
) -> None:
    if not _trace_enabled():
        return
    rid = (run_id or "").strip() or uuid.uuid4().hex
    tid = (turn_id or "").strip() or request_id or uuid.uuid4().hex
    state = {
        "run_id": rid,
        "turn_id": tid,
        "request_id": (request_id or "").strip() or None,
        "session_id": (session_id or "").strip() or None,
        "user_id": (user_id or "").strip() or None,
        "trace_path": str((_trace_dir() / f"{rid}.jsonl").resolve()),
        "sequence": 0,
        "started_at": time.time(),
    }
    _TRACE_STATE.set(state)
    emit_event(
        event_type="turn_started",
        component="llm_loop",
        summary="turn started",
        details={"query": query or ""},
    )


def end_turn(final_output: Optional[str] = None, artifact: Optional[Dict[str, Any]] = None) -> None:
    if not _trace_enabled():
        return
    state = _TRACE_STATE.get({})
    if not state:
        return
    elapsed_ms = int((time.time() - float(state.get("started_at") or time.time())) * 1000)
    emit_event(
        event_type="turn_finished",
        component="llm_loop",
        summary="turn finished",
        details={"elapsed_ms": elapsed_ms, "final_output": final_output or "", "artifact": artifact or {}},
    )


def emit_event(
    *,
    event_type: str,
    component: str,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> None:
    if not _trace_enabled():
        return
    state = dict(_TRACE_STATE.get({}))
    if run_id:
        state["run_id"] = run_id
    if turn_id:
        state["turn_id"] = turn_id
    if not state.get("run_id"):
        state["run_id"] = uuid.uuid4().hex
    if not state.get("turn_id"):
        state["turn_id"] = uuid.uuid4().hex
    if not state.get("trace_path"):
        state["trace_path"] = str((_trace_dir() / f"{state['run_id']}.jsonl").resolve())
    seq = _next_sequence(state)
    _TRACE_STATE.set(state)
    payload = {
        "schema_version": "1.0",
        "run_id": state.get("run_id"),
        "turn_id": state.get("turn_id"),
        "request_id": state.get("request_id"),
        "session_id": state.get("session_id"),
        "user_id": state.get("user_id"),
        "timestamp": time.time(),
        "sequence": seq,
        "event_type": str(event_type or "").strip(),
        "component": str(component or "").strip(),
        "summary": str(summary or "").strip(),
        "details": _redact(details or {}),
    }
    path = Path(str(state["trace_path"]))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with _WRITE_LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        try:
            _fanout_trace_line(line)
        except Exception:
            pass
    except Exception:
        # Never break runtime due to tracing.
        return


def current_trace_path() -> Optional[str]:
    state = _TRACE_STATE.get({})
    p = state.get("trace_path")
    return str(p) if p else None


def subscribe_trace_sse_queue(maxsize: int = 200) -> queue.Queue:
    """Register a queue to receive each JSON trace line (same as JSONL). Unsubscribe when done."""
    q: queue.Queue = queue.Queue(maxsize=maxsize)
    with _FANOUT_LOCK:
        _TRACE_SSE_QUEUES.append(q)
    return q


def unsubscribe_trace_sse_queue(q: queue.Queue) -> None:
    with _FANOUT_LOCK:
        try:
            _TRACE_SSE_QUEUES.remove(q)
        except ValueError:
            pass


def _fanout_trace_line(line: str) -> None:
    with _FANOUT_LOCK:
        qs = list(_TRACE_SSE_QUEUES)
    for q in qs:
        try:
            q.put_nowait(line)
        except queue.Full:
            try:
                q.get_nowait()
            except Exception:
                pass
            try:
                q.put_nowait(line)
            except Exception:
                pass


def emit_tool_progress(
    *,
    tool_name: str,
    phase: str,
    message: str = "",
    fraction: Optional[float] = None,
) -> None:
    """Structured progress for long-running tools (optional)."""
    det: Dict[str, Any] = {"tool_name": tool_name, "phase": phase}
    if message:
        det["message"] = message
    if fraction is not None:
        det["fraction"] = fraction
    emit_event(
        event_type="tool_progress",
        component="tool_registry",
        summary=f"tool progress: {tool_name} {phase}",
        details=det,
    )
