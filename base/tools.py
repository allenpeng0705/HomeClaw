"""
Tool layer for HomeClaw: callable tools (name + schema + executor).

Design goals:
- Clear and simple to extend: add a tool = register(name, description, parameters, executor).
- No inheritance required for simple tools; optional ToolDefinition dataclass.
- Registry builds OpenAI-compatible tools list and executes by name.

See Design.md §3.6 (Plugins vs tools).
"""

from dataclasses import dataclass, field
import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from loguru import logger

try:
    from base.util import redact_params_for_log
except ImportError:
    def redact_params_for_log(obj: Any) -> Any:
        return obj
try:
    from base.workflow_trace import emit_event as _trace_emit_event
except ImportError:
    def _trace_emit_event(**kwargs):  # type: ignore
        return None

# When a routing tool (route_to_tam, route_to_plugin) runs, it returns this; Core skips sending another response.
ROUTING_RESPONSE_ALREADY_SENT = "__ROUTING_ALREADY_SENT__"


@dataclass
class ToolContext:
    """Context passed to every tool executor: core, request ids, optional request."""

    core: Any  # CoreInterface
    app_id: str = "homeclaw"
    user_name: Optional[str] = None
    user_id: Optional[str] = None  # For storage (chat, KB, memory): system user id when set by Core; else channel identity
    system_user_id: Optional[str] = None  # Our system user id (from user.yml); use this or user_id for storage
    friend_id: Optional[str] = None  # Which friend this conversation is with (e.g. "HomeClaw", "Sabrina"). Default "HomeClaw" when from request and not set.
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    request: Optional[Any] = None  # PromptRequest if available
    # Mutable session for browser tools: {"browser", "page"} so navigate/snapshot/click/type share one page per request
    browser_session: Dict[str, Any] = field(default_factory=dict)
    # Optional: set by Core from core.yml tool_policy for execute_async gate (see base.tool_permissions).
    permission_context: Optional[Any] = None
    # Optional: concatenated recent **user** message texts (from the in-flight OpenAI-style message list) so tools
    # (e.g. document_read) can infer filenames/paths from prior turns without reading the full model context.
    recent_user_messages_text: Optional[str] = None


# Executor: async (arguments: dict, context: ToolContext) -> str
ToolExecutor = Callable[[Dict[str, Any], ToolContext], Awaitable[str]]
RetryAdjuster = Callable[[Dict[str, Any], ToolContext, int, str], Dict[str, Any]]
RetryDecider = Callable[[Dict[str, Any], ToolContext, str], bool]


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_argument_schema(
    schema: Dict[str, Any],
    value: Any,
    path: str = "$",
) -> List[str]:
    errors: List[str] = []
    if not isinstance(schema, dict):
        return errors
    expected = schema.get("type")
    if isinstance(expected, str) and not _schema_type_matches(value, expected):
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
        return errors

    if expected == "object" and isinstance(value, dict):
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for k in required:
            if k not in value:
                errors.append(f"{path}: missing required field '{k}'")
        additional = schema.get("additionalProperties")
        if additional is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unknown field '{key}'")
        for key, subschema in props.items():
            if key in value and isinstance(subschema, dict):
                errors.extend(_validate_argument_schema(subschema, value[key], f"{path}.{key}"))
    elif expected == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(_validate_argument_schema(item_schema, item, f"{path}[{idx}]"))
    return errors


def _looks_like_error_result(result: Any) -> Tuple[bool, str]:
    if not isinstance(result, str):
        return False, ""
    text = result.strip()
    if text.lower().startswith("error"):
        return True, text
    return False, text


def filter_openai_tools_for_llm(
    openai_tools: Optional[List[Dict[str, Any]]],
    allowlist: Optional[List[str]],
    *,
    always_include_discovery: bool = True,
) -> Optional[List[Dict[str, Any]]]:
    """
    When allowlist is non-empty, keep only those tool names (OpenAI-style descriptors).
    Optionally always include list_available_tools and search_available_tools for discovery.
    """
    if not openai_tools or not isinstance(openai_tools, list):
        return openai_tools
    if not allowlist:
        return openai_tools
    names = {str(x).strip() for x in allowlist if x is not None and str(x).strip()}
    if not names:
        return openai_tools
    if always_include_discovery:
        names.add("list_available_tools")
        names.add("search_available_tools")
    out = [t for t in openai_tools if isinstance(t, dict) and ((t.get("function") or {}).get("name") or "") in names]
    return out if out else openai_tools


def strip_deferred_tools_from_openai_list(
    openai_tools: Optional[List[Dict[str, Any]]],
    defer_names: Optional[List[str]],
) -> Optional[List[Dict[str, Any]]]:
    """
    Remove tool names in defer_names from the LLM-facing OpenAI-style tool list.
    Execution registry is unchanged; use list_available_tools / search_available_tools to surface deferred names.
    """
    if not openai_tools or not isinstance(openai_tools, list):
        return openai_tools
    if not defer_names or not isinstance(defer_names, (list, tuple)):
        return openai_tools
    d = {str(x).strip() for x in defer_names if x is not None and str(x).strip()}
    if not d:
        return openai_tools
    out = [
        t
        for t in openai_tools
        if isinstance(t, dict) and ((t.get("function") or {}).get("name") or "") not in d
    ]
    return out if out else openai_tools


def _truncate_description(desc: str, max_chars: int) -> str:
    """Truncate description for local LLMs; prefer sentence or word boundary. Never raises."""
    if not isinstance(desc, str):
        return (desc or "") if desc is not None else ""
    try:
        mc = int(max_chars) if max_chars is not None else 0
    except (TypeError, ValueError):
        mc = 0
    if not desc or mc <= 0 or len(desc) <= mc:
        return desc
    cut = desc[: mc + 1]
    for sep in (". ", "。", "! ", "? ", "; ", " "):
        idx = cut.rfind(sep)
        if idx > mc // 2:
            return (cut[: idx + len(sep)].rstrip() + "…") if idx + len(sep) < len(desc) else cut[: idx + len(sep)].rstrip()
    return cut.rstrip() + "…"


@dataclass
class ToolDefinition:
    """
    One callable tool: name, description, JSON Schema for parameters, and async executor.
    To add a new tool: create ToolDefinition(...) and registry.register(tool).
    optional short_description: used when tools.description_max_chars is set (local LLM mode) for more accurate tool selection.
    """

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for the tool's arguments (e.g. {"type": "object", "properties": {...}})
    execute_async: ToolExecutor
    short_description: Optional[str] = None  # One-line cue for local LLMs; used when description_max_chars > 0
    # Policy hooks (optional). Used when core.yml tool_policy.default_mode=allow_read_restrict_write.
    risk_tier: Optional[str] = None  # read | write | network | exec | user_data; unset → treated as read
    requires_confirmation: bool = False  # When true, blocked in allow_read_restrict_write (before risk_tier check)
    max_retries: int = 0  # Retry count after initial attempt (0 = no retry)
    retry_delay_seconds: float = 0.0  # Optional backoff between retries
    retry_adjuster: Optional[RetryAdjuster] = None  # Optional strategy hook to mutate args between retries
    retry_decider: Optional[RetryDecider] = None  # Optional gate to decide whether a retry is allowed

    def to_openai_function(self, max_description_chars: Optional[int] = None) -> Dict[str, Any]:
        """OpenAI/OpenAI-compatible function descriptor for chat API. When max_description_chars > 0, use short_description or truncate for local LLM."""
        desc = self.description if isinstance(self.description, str) else (self.description or "")
        try:
            mc = int(max_description_chars) if max_description_chars is not None else 0
        except (TypeError, ValueError):
            mc = 0
        if mc > 0:
            if self.short_description and isinstance(self.short_description, str) and len(self.short_description) <= mc:
                desc = self.short_description
            else:
                desc = _truncate_description(desc, mc)
        params = self.parameters if isinstance(self.parameters, dict) else {}
        return {
            "type": "function",
            "function": {
                "name": str(self.name) if self.name is not None else "",
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": params.get("properties", {}),
                    "required": params.get("required", []) if isinstance(params.get("required"), list) else [],
                },
            },
        }


class ToolRegistry:
    """
    Central registry of tools. Register tools here; Core uses it to build tools list
    for the LLM and to execute tool_calls.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool by name. Overwrites if same name."""
        if not tool.name or not tool.description:
            raise ValueError("Tool name and description are required")
        self._tools[tool.name] = tool
        logger.debug("Registered tool: {}", tool.name)

    def unregister(self, name: str) -> bool:
        """Remove a tool by name. Returns True if it was present."""
        if name in self._tools:
            del self._tools[name]
            logger.debug("Unregistered tool: {}", name)
            return True
        return False

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def get_openai_tools(self, max_description_chars: Optional[int] = None) -> List[Dict[str, Any]]:
        """List of tool descriptors for OpenAI-compatible chat API (tools=...). When max_description_chars > 0, use short_description or truncate so local LLMs get concise cues."""
        return [t.to_openai_function(max_description_chars) for t in self._tools.values()]

    async def execute_async(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: ToolContext,
    ) -> str:
        """
        Execute a tool by name with the given arguments. Returns the tool's result as string.
        Raises KeyError if tool unknown; propagates executor exceptions.
        """
        tool = self._tools.get(name)
        if not tool:
            raise KeyError(f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            return "Error: invalid tool arguments: payload must be a JSON object."
        schema_errors = _validate_argument_schema(
            {"type": "object", "properties": tool.parameters.get("properties", {}), "required": tool.parameters.get("required", [])},
            arguments,
        )
        if schema_errors:
            logger.info("[TOOL_CALL] name={} INVALID_SCHEMA errors={}", name, schema_errors)
            return f"Error: invalid tool arguments: {'; '.join(schema_errors)}"
        try:
            from base.tool_permissions import evaluate_tool_permission

            perm_ctx = getattr(context, "permission_context", None)
            pr = evaluate_tool_permission(tool, arguments if isinstance(arguments, dict) else {}, perm_ctx)
            if not pr.allowed:
                args_redacted = redact_params_for_log(arguments) if isinstance(arguments, dict) else arguments
                logger.info("[TOOL_CALL] name={} DENIED reason={}", name, pr.reason_code)
                _trace_emit_event(
                    event_type="permission_denied",
                    component="tool_registry",
                    summary=f"permission denied: {name}",
                    details={
                        "tool_name": name,
                        "reason_code": pr.reason_code,
                        "source": "policy",
                        "arguments": args_redacted,
                    },
                )
                try:
                    req = getattr(context, "request", None)
                    md = getattr(req, "request_metadata", None) if req is not None else None
                    pq = md.get("progress_queue") if isinstance(md, dict) else None
                    if pq is not None and hasattr(pq, "put_nowait"):
                        pq.put_nowait(
                            {
                                "event": "progress",
                                "tool": name,
                                "message": f"Permission denied ({pr.reason_code})",
                            }
                        )
                except Exception:
                    pass
                return f"Error: {pr.message}"
        except Exception as _perm_e:
            logger.debug("Tool permission check failed (allowing execution): {}", _perm_e)
        # [TOOL_CALL] / [TOOL_RESULT]: grep these in logs to see only tool/skill invocations and outcomes.
        args_redacted = redact_params_for_log(arguments) if isinstance(arguments, dict) else arguments
        logger.info("[TOOL_CALL] name={} parameters={}", name, args_redacted)

        # ── Approval gate (Phase 5) ──────────────────────────────────
        try:
            from core.approvals.policy import build_policy_from_config, ApprovalDecision
            from base.util import Util
            _approval_cfg = getattr(Util().get_core_metadata(), "approval", None) or {}
            if isinstance(_approval_cfg, dict) and _approval_cfg:
                _policy = build_policy_from_config(_approval_cfg)
                _decision = _policy.resolve(name)
                if _decision == ApprovalDecision.DENY:
                    logger.info("[TOOL_CALL] name={} DENIED_BY_POLICY", name)
                    _audit_record(name, context, str(uuid.uuid4()), time.time(), "denied",
                                  f"Denied by approval policy")
                    return f"Error: tool '{name}' is denied by approval policy."
        except Exception:
            pass

        # ── Audit gate (Phase 6) ──────────────────────────────────────
        _audit_start = time.time()
        _audit_event_id = str(uuid.uuid4())

        _trace_emit_event(
            event_type="tool_call_started",
            component="tool_registry",
            summary=f"tool call started: {name}",
            details={"tool_name": name, "arguments": args_redacted},
        )
        max_retries = max(0, int(getattr(tool, "max_retries", 0) or 0))
        retry_delay = max(0.0, float(getattr(tool, "retry_delay_seconds", 0.0) or 0.0))
        retry_adjuster = getattr(tool, "retry_adjuster", None)
        retry_decider = getattr(tool, "retry_decider", None)
        current_args = dict(arguments)
        last_error = ""
        for attempt in range(max_retries + 1):
            try:
                result = await tool.execute_async(current_args, context)
                result = result if result is not None else ""
                is_error, error_text = _looks_like_error_result(result)
                if not is_error:
                    res_len = len(result) if isinstance(result, str) else 0
                    logger.debug("[TOOL_RESULT] name={} result_len={} status={} attempt={}", name, res_len, "ok", attempt)
                    _audit_record(name, context, _audit_event_id, _audit_start, "ok", result)
                    _trace_emit_event(
                        event_type="tool_call_finished",
                        component="tool_registry",
                        summary=f"tool call finished: {name}",
                        details={"tool_name": name, "status": "ok", "result_len": res_len, "attempt": attempt},
                    )
                    return result
                last_error = error_text
                can_retry = attempt < max_retries
                if can_retry and callable(retry_decider):
                    try:
                        can_retry = bool(retry_decider(dict(current_args), context, error_text))
                    except Exception as _retry_decider_e:
                        logger.debug("Retry decider failed for {} (default no-retry): {}", name, _retry_decider_e)
                        can_retry = False
                if not can_retry:
                    logger.debug("[TOOL_RESULT] name={} status={} attempt={}", name, "error", attempt)
                    _audit_record(name, context, _audit_event_id, _audit_start, "error", result)
                    _trace_emit_event(
                        event_type="tool_call_finished",
                        component="tool_registry",
                        summary=f"tool call finished: {name}",
                        details={"tool_name": name, "status": "error", "result_len": len(result), "attempt": attempt},
                    )
                    return result
                if callable(retry_adjuster):
                    current_args = retry_adjuster(dict(current_args), context, attempt + 1, error_text)
                    if not isinstance(current_args, dict):
                        return "Error: invalid retry strategy: adjusted arguments must be a JSON object."
                logger.warning(
                    "[TOOL_RETRY] name={} attempt={} reason={} adjusted_args={}",
                    name,
                    attempt + 1,
                    error_text[:200],
                    redact_params_for_log(current_args),
                )
                if retry_delay > 0:
                    await asyncio.sleep(retry_delay)
            except Exception as e:
                last_error = str(e)
                can_retry = attempt < max_retries
                if can_retry and callable(retry_decider):
                    try:
                        can_retry = bool(retry_decider(dict(current_args), context, str(e)))
                    except Exception as _retry_decider_e:
                        logger.debug("Retry decider failed for {} (default no-retry): {}", name, _retry_decider_e)
                        can_retry = False
                if not can_retry:
                    logger.exception("Tool {} failed after {} retries: {}", name, max_retries, e)
                    logger.debug("[TOOL_RESULT] name={} status=exception attempt={}", name, attempt)
                    _audit_record(name, context, _audit_event_id, _audit_start, "exception", str(e))
                    _trace_emit_event(
                        event_type="tool_call_finished",
                        component="tool_registry",
                        summary=f"tool call exception: {name}",
                        details={"tool_name": name, "status": "exception", "error": str(e), "attempt": attempt},
                    )
                    return f"Error running tool {name}: {e!s}"
                if callable(retry_adjuster):
                    current_args = retry_adjuster(dict(current_args), context, attempt + 1, str(e))
                    if not isinstance(current_args, dict):
                        return "Error: invalid retry strategy: adjusted arguments must be a JSON object."
                logger.warning(
                    "[TOOL_RETRY] name={} attempt={} exception={} adjusted_args={}",
                    name,
                    attempt + 1,
                    str(e)[:200],
                    redact_params_for_log(current_args),
                )
                if retry_delay > 0:
                    await asyncio.sleep(retry_delay)
        _audit_record(name, context, _audit_event_id, _audit_start, "error", last_error)
        return f"Error running tool {name}: {last_error or 'unknown error'}"


# ── Audit helper (Phase 6) ────────────────────────────────────────────


def _audit_record(tool_name: str, context: ToolContext, event_id: str,
                  start_time: float, status: str, result: Any) -> None:
    """Record a tool execution audit event. Best-effort; never raises."""
    try:
        import uuid as _uuid
        from core.tool_audit import ToolAuditEvent, record_event, init_audit_db
        init_audit_db()
        duration = (time.time() - start_time) * 1000
        summary = (str(result)[:200] if isinstance(result, str) else str(result)[:200])
        event = ToolAuditEvent(
            event_id=event_id or str(_uuid.uuid4()),
            tool_name=tool_name,
            agent_id=getattr(context, "app_id", "") or "",
            session_id=getattr(context, "session_id", "") or "",
            user_id=getattr(context, "user_id", "") or "",
            result_status=status,
            result_summary=summary,
            duration_ms=duration,
        )
        record_event(event)
    except Exception:
        pass


# Global registry instance. Core (or bootstrap) can add built-in tools and plugin tools here.
# Access via get_tool_registry() so tests can replace it if needed.
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Return the global tool registry. Creates it on first use."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_tool_registry() -> None:
    """Clear the global registry (mainly for tests)."""
    global _registry
    _registry = ToolRegistry()
