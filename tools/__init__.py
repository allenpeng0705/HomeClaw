"""
Built-in and extensible tools for HomeClaw (tool layer).

- tools.builtin: register_builtin_tools(registry) — sessions_transcript, etc.
- Add new tools by creating ToolDefinition and registry.register(tool).
"""

from tools.builtin import register_builtin_tools

__all__ = ["register_builtin_tools"]
