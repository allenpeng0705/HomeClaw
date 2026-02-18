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
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    request: Optional[Any] = None  # PromptRequest if available
    # Mutable session for browser tools: {"browser", "page"} so navigate/snapshot/click/type share one page per request
    browser_session: Dict[str, Any] = field(default_factory=dict)


# Executor: async (arguments: dict, context: ToolContext) -> str
ToolExecutor = Callable[[Dict[str, Any], ToolContext], Awaitable[str]]


@dataclass
class ToolDefinition:
    """
    One callable tool: name, description, JSON Schema for parameters, and async executor.
    To add a new tool: create ToolDefinition(...) and registry.register(tool).
    """

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for the tool's arguments (e.g. {"type": "object", "properties": {...}})
    execute_async: ToolExecutor

    def to_openai_function(self) -> Dict[str, Any]:
        """OpenAI/OpenAI-compatible function descriptor for chat API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters.get("properties", {}),
                    "required": self.parameters.get("required", []),
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

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """List of tool descriptors for OpenAI-compatible chat API (tools=...)."""
        return [t.to_openai_function() for t in self._tools.values()]

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
            result = await tool.execute_async(arguments, context)
            return result if result is not None else ""
        except Exception as e:
            logger.exception("Tool {} failed: {}", name, e)
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
