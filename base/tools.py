"""
Tool layer for HomeClaw: callable tools (name + schema + executor).

Design goals:
- Clear and simple to extend: add a tool = register(name, description, parameters, executor).
- No inheritance required for simple tools; optional ToolDefinition dataclass.
- Registry builds OpenAI-compatible tools list and executes by name.

See Design.md §3.6 (Plugins vs tools).
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

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
        _trace_emit_event(
            event_type="tool_call_started",
            component="tool_registry",
            summary=f"tool call started: {name}",
            details={"tool_name": name, "arguments": args_redacted},
        )
        try:
            result = await tool.execute_async(arguments, context)
            result = result if result is not None else ""
            res_len = len(result) if isinstance(result, str) else 0
            status = "error" if isinstance(result, str) and result.strip().startswith("Error") else "ok"
            logger.debug("[TOOL_RESULT] name={} result_len={} status={}", name, res_len, status)
            _trace_emit_event(
                event_type="tool_call_finished",
                component="tool_registry",
                summary=f"tool call finished: {name}",
                details={"tool_name": name, "status": status, "result_len": res_len},
            )
            return result
        except Exception as e:
            logger.exception("Tool {} failed: {}", name, e)
            logger.debug("[TOOL_RESULT] name={} status=exception", name)
            _trace_emit_event(
                event_type="tool_call_finished",
                component="tool_registry",
                summary=f"tool call exception: {name}",
                details={"tool_name": name, "status": "exception", "error": str(e)},
            )
            return f"Error running tool {name}: {e!s}"


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
