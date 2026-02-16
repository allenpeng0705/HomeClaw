"""
Workspace bootstrap loader (optional).
Loads IDENTITY.md, AGENTS.md, TOOLS.md from config/workspace/ and injects into system prompt.
See Design.md §3.6 — workspace bootstrap while keeping RAG.
"""
import os
from pathlib import Path
from typing import Dict, Optional

# Project root: parent of base/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WORKSPACE_DIR = _PROJECT_ROOT / "config" / "workspace"

WORKSPACE_FILES = ("IDENTITY.md", "AGENTS.md", "TOOLS.md")
KEY_IDENTITY = "identity"
KEY_AGENTS = "agents"
KEY_TOOLS = "tools"
FILE_TO_KEY = {
    "IDENTITY.md": KEY_IDENTITY,
    "AGENTS.md": KEY_AGENTS,
    "TOOLS.md": KEY_TOOLS,
}


def get_workspace_dir(config_dir: Optional[str] = None) -> Path:
    """Return workspace directory path. Prefer config_dir if given and absolute or under project."""
    if config_dir:
        p = Path(config_dir)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p
    return _DEFAULT_WORKSPACE_DIR


def load_workspace(workspace_dir: Optional[Path] = None) -> Dict[str, str]:
    """
    Load workspace bootstrap files (IDENTITY.md, AGENTS.md, TOOLS.md).
    Returns dict with keys 'identity', 'agents', 'tools'; value is file content or empty string.
    """
    result = {KEY_IDENTITY: "", KEY_AGENTS: "", KEY_TOOLS: ""}
    root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
    if not root.is_dir():
        return result
    for filename, key in FILE_TO_KEY.items():
        path = root / filename
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    result[key] = text
            except Exception:
                pass
    return result


def build_workspace_system_prefix(workspace: Dict[str, str]) -> str:
    """
    Build a single system-prompt block from workspace dict.
    Only includes non-empty identity, agents, tools; each wrapped with a short header.
    """
    parts = []
    if workspace.get(KEY_IDENTITY):
        parts.append("## Identity\n" + workspace[KEY_IDENTITY])
    if workspace.get(KEY_AGENTS):
        parts.append("## Agents / behavior\n" + workspace[KEY_AGENTS])
    if workspace.get(KEY_TOOLS):
        parts.append("## Tools / capabilities\n" + workspace[KEY_TOOLS])
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"
