"""
Workspace bootstrap loader (optional).
Loads IDENTITY.md, AGENTS.md, TOOLS.md from config/workspace/ and injects into system prompt.
See Design.md §3.6 — workspace bootstrap while keeping RAG.
Daily memory: memory/YYYY-MM-DD.md (today + yesterday) for bounded short-term context; see SessionAndDualMemoryDesign.md.
"""
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Project root: parent of base/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_WORKSPACE_DIR = _PROJECT_ROOT / "config" / "workspace"

WORKSPACE_FILES = ("IDENTITY.md", "AGENTS.md", "TOOLS.md")
AGENT_MEMORY_FILENAME = "AGENT_MEMORY.md"
KEY_IDENTITY = "identity"
KEY_AGENTS = "agents"
KEY_TOOLS = "tools"
FILE_TO_KEY = {
    "IDENTITY.md": KEY_IDENTITY,
    "AGENTS.md": KEY_AGENTS,
    "TOOLS.md": KEY_TOOLS,
}


def get_workspace_dir(config_dir: Optional[str] = None) -> Path:
    """Return workspace directory path. Prefer config_dir if given and absolute or under project. Never raises."""
    if not config_dir or not str(config_dir).strip():
        return _DEFAULT_WORKSPACE_DIR
    try:
        p = Path(str(config_dir).strip())
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p
    except Exception:
        return _DEFAULT_WORKSPACE_DIR


def load_workspace(workspace_dir: Optional[Path] = None) -> Dict[str, str]:
    """
    Load workspace bootstrap files (IDENTITY.md, AGENTS.md, TOOLS.md).
    Returns dict with keys 'identity', 'agents', 'tools'; value is file content or empty string. Never raises.
    """
    result = {KEY_IDENTITY: "", KEY_AGENTS: "", KEY_TOOLS: ""}
    try:
        root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        if not root.is_dir():
            return result
    except Exception:
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


def get_agent_memory_file_path(workspace_dir: Optional[Path] = None, agent_memory_path: Optional[str] = None) -> Optional[Path]:
    """Return the Path for AGENT_MEMORY.md, or None if not configured. Used for read and append. Never raises."""
    try:
        root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        if agent_memory_path and str(agent_memory_path).strip():
            p = Path(str(agent_memory_path).strip())
            if not p.is_absolute():
                p = _PROJECT_ROOT / p
            return p
        return root / AGENT_MEMORY_FILENAME
    except Exception:
        return _DEFAULT_WORKSPACE_DIR / AGENT_MEMORY_FILENAME


def ensure_agent_memory_file_exists(
    workspace_dir: Optional[Path] = None,
    agent_memory_path: Optional[str] = None,
) -> bool:
    """Create AGENT_MEMORY.md if it does not exist (empty). Returns True if created or already existed."""
    path = get_agent_memory_file_path(workspace_dir=workspace_dir, agent_memory_path=agent_memory_path)
    if path is None:
        return False
    if path.is_file():
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False


def load_agent_memory_file(
    workspace_dir: Optional[Path] = None,
    agent_memory_path: Optional[str] = None,
    max_chars: int = 0,
) -> str:
    """
    Load AGENT_MEMORY.md (curated long-term memory). Used with RAG; AGENT_MEMORY is authoritative on conflict.
    If agent_memory_path is set and is a valid path, use it; otherwise workspace_dir/AGENT_MEMORY.md.
    If max_chars > 0 and content is longer, returns only the last max_chars with an omission note (avoids filling context window).
    Returns file content or empty string.
    """
    root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
    path = get_agent_memory_file_path(workspace_dir=root, agent_memory_path=agent_memory_path)
    if path is None or not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    if not content:
        return ""
    if max_chars > 0 and len(content) > max_chars:
        note = f"... (earlier content omitted; showing last {max_chars} of {len(content)} chars)\n\n"
        return note + content[-max_chars:]
    return content


def trim_content_bootstrap(content: str, max_chars: int) -> str:
    """
    OpenClaw-style trim: when content exceeds max_chars, keep head (70% of cap) + tail (20% of cap)
    with a marker in between. So the model sees structure (head) and recent content (tail). Never raises.
    """
    if not content or not str(content).strip():
        return ""
    try:
        max_chars = max(500, int(max_chars))
    except (TypeError, ValueError):
        max_chars = 5000
    if len(content) <= max_chars:
        return content
    head_chars = int(0.7 * max_chars)
    tail_chars = int(0.2 * max_chars)
    marker = f"\n\n... (middle omitted; total {len(content)} chars) ...\n\n"
    return content[:head_chars] + marker + content[-tail_chars:]


def clear_agent_memory_file(
    workspace_dir: Optional[Path] = None,
    agent_memory_path: Optional[str] = None,
) -> bool:
    """
    Clear AGENT_MEMORY.md (write empty file). Used when memory is reset (e.g. /memory/reset) so curated
    long-term memory is cleared together with RAG. Creates parent dirs and file if needed.
    Returns True if the file was cleared (or created empty), False if path is not configured.
    """
    root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
    path = get_agent_memory_file_path(workspace_dir=root, agent_memory_path=agent_memory_path)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False


# ---- Daily memory (memory/YYYY-MM-DD.md): short-term, load yesterday + today ----

def get_daily_memory_dir(
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
) -> Path:
    """Return the directory for daily memory files (memory/YYYY-MM-DD.md). Default: workspace_dir/memory. Never raises."""
    try:
        root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        if daily_memory_dir and str(daily_memory_dir).strip():
            p = Path(str(daily_memory_dir).strip())
            if not p.is_absolute():
                p = _PROJECT_ROOT / p
            return p
        return root / "memory"
    except Exception:
        return _DEFAULT_WORKSPACE_DIR / "memory"


def get_daily_memory_path_for_date(
    d: date,
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
) -> Path:
    """Return the Path for memory/YYYY-MM-DD.md for the given date."""
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir)
    return base / f"{d.isoformat()}.md"


def ensure_daily_memory_file_exists(
    d: date,
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
) -> bool:
    """Create today's daily memory file if it does not exist (empty). Returns True if created or already existed."""
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir)
    path = base / f"{d.isoformat()}.md"
    if path.is_file():
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False


def load_daily_memory_for_dates(
    dates: List[date],
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
    max_chars: int = 0,
) -> str:
    """
    Load and concatenate daily memory files for the given dates (newest last).
    Returns a single string with optional "## YYYY-MM-DD" headers per file. Used to inject yesterday + today into the prompt.
    If max_chars > 0 and concatenated content is longer, returns only the last max_chars with an omission note.
    Creates today's file if missing so the file exists for the model to append to later.
    """
    if not dates:
        return ""
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir)
    today = date.today()
    parts = []
    for d in sorted(dates):
        path = base / f"{d.isoformat()}.md"
        if d == today and not path.is_file():
            ensure_daily_memory_file_exists(d, workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir)
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    parts.append(f"## {d.isoformat()}\n{text}")
            except Exception:
                pass
    content = "\n\n".join(parts) if parts else ""
    if not content:
        return ""
    if max_chars > 0 and len(content) > max_chars:
        note = f"... (daily memory truncated; showing last {max_chars} of {len(content)} chars)\n\n"
        return note + content[-max_chars:]
    return content


def append_daily_memory(
    content: str,
    d: Optional[date] = None,
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
) -> bool:
    """
    Append content to the daily memory file for the given date (default: today).
    Creates the file and parent dir if needed. Returns True on success.
    """
    if not content or not content.strip():
        return False
    day = d or date.today()
    path = get_daily_memory_path_for_date(day, workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        new_content = (existing + "\n\n" + content.strip()).strip() if existing else content.strip()
        path.write_text(new_content + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def clear_daily_memory_for_dates(
    dates: List[date],
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
) -> int:
    """Clear (truncate to empty) daily memory files for the given dates. Returns number of files cleared."""
    if not dates:
        return 0
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir)
    cleared = 0
    for d in dates:
        path = base / f"{d.isoformat()}.md"
        if path.is_file():
            try:
                path.write_text("", encoding="utf-8")
                cleared += 1
            except Exception:
                pass
    return cleared
