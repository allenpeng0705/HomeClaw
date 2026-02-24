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

from loguru import logger

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

# When system_user_id is one of these (or None/empty), use global AGENT_MEMORY and daily memory (company app).
_GLOBAL_AGENT_MEMORY_IDS = frozenset(("system", "companion"))


def _is_global_agent_memory_user(system_user_id: Optional[str]) -> bool:
    """True if we should use global (shared) AGENT_MEMORY and daily memory paths. Never raises."""
    try:
        if not system_user_id or not str(system_user_id).strip():
            return True
        return str(system_user_id).strip().lower() in _GLOBAL_AGENT_MEMORY_IDS
    except Exception:
        return True


def _sanitize_system_user_id(system_user_id: Optional[str]) -> str:
    """Sanitize for use in file paths (no directory traversal or invalid chars). Never raises."""
    try:
        if not system_user_id:
            return ""
        s = str(system_user_id).strip()
        for c in r'/\:*?"<>|':
            s = s.replace(c, "_")
        return s or ""
    except Exception:
        return ""


def get_user_knowledgebase_dir(homeclaw_root: str, user_id: str, folder_name: str = "knowledgebase") -> Optional[Path]:
    """
    Path to a user's knowledge base folder: {homeclaw_root}/{user_id}/{folder_name}/.
    Used for folder_sync: files here are scanned and synced to the user's KB. Returns None if homeclaw_root is empty.
    Never raises.
    """
    try:
        root = (homeclaw_root or "").strip()
        if not root:
            return None
        uid = _sanitize_system_user_id(user_id)
        if not uid:
            return None
        name = (folder_name or "knowledgebase").strip() or "knowledgebase"
        for c in r'/\:*?"<>|':
            name = name.replace(c, "_")
        if not name:
            name = "knowledgebase"
        return Path(root).resolve() / uid / name
    except Exception:
        return None


def ensure_user_sandbox_folders(
    homeclaw_root: str,
    user_ids: List[str],
    *,
    share_dir: str = "share",
    companion: bool = True,
    output_subdir: str = "output",
    knowledgebase_subdir: str = "knowledgebase",
) -> None:
    """
    Create per-user and shared sandbox folders under homeclaw_root so they exist for file tools and KB sync.
    For each user_id: {homeclaw_root}/{user_id}, {user_id}/output, {user_id}/knowledgebase.
    Also creates: {homeclaw_root}/share, and if companion: {homeclaw_root}/companion, companion/output.
    Uses _sanitize_system_user_id for path segments. Never raises; logs on mkdir failure.
    """
    try:
        root = (homeclaw_root or "").strip()
        if not root:
            return
        if not isinstance(user_ids, (list, tuple)):
            user_ids = []
        else:
            user_ids = list(user_ids)
        base = Path(root).resolve()
        try:
            if not base.exists():
                base.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.debug("ensure_user_sandbox_folders: mkdir root {} failed: {}", base, e)
            return
        # Share folder (all users + companion)
        share_name = (share_dir or "share").strip() or "share"
        for c in r'/\:*?"<>|':
            share_name = share_name.replace(c, "_")
        try:
            (base / share_name).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.debug("ensure_user_sandbox_folders: mkdir share {} failed: {}", base / share_name, e)
        # Companion folder (when app not tied to a user)
        if companion:
            try:
                comp = base / "companion"
                comp.mkdir(parents=True, exist_ok=True)
                (comp / (output_subdir or "output").strip() or "output").mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.debug("ensure_user_sandbox_folders: mkdir companion failed: {}", e)
        out_sub = (output_subdir or "output").strip() or "output"
        kb_sub = (knowledgebase_subdir or "knowledgebase").strip() or "knowledgebase"
        for c in r'/\:*?"<>|':
            out_sub = out_sub.replace(c, "_")
            kb_sub = kb_sub.replace(c, "_")
        for uid_raw in user_ids:
            uid = _sanitize_system_user_id(uid_raw)
            if not uid:
                continue
            try:
                user_base = base / uid
                user_base.mkdir(parents=True, exist_ok=True)
                (user_base / out_sub).mkdir(parents=True, exist_ok=True)
                (user_base / kb_sub).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.debug("ensure_user_sandbox_folders: mkdir user {} failed: {}", uid, e)
    except Exception as e:
        logger.debug("ensure_user_sandbox_folders: {}", e)


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


def build_workspace_system_prefix(workspace: Dict[str, str], skip_identity: bool = False) -> str:
    """
    Build a single system-prompt block from workspace dict.
    Only includes non-empty identity (unless skip_identity), agents, tools; each wrapped with a short header.
    When skip_identity is True (e.g. companion user with "who"), the Identity section is omitted so the caller can inject a who-based identity instead.
    """
    parts = []
    if not skip_identity and workspace.get(KEY_IDENTITY):
        parts.append("## Identity\n" + workspace[KEY_IDENTITY])
    if workspace.get(KEY_AGENTS):
        parts.append("## Agents / behavior\n" + workspace[KEY_AGENTS])
    if workspace.get(KEY_TOOLS):
        parts.append("## Tools / capabilities\n" + workspace[KEY_TOOLS])
    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


def get_agent_memory_file_path(
    workspace_dir: Optional[Path] = None,
    agent_memory_path: Optional[str] = None,
    system_user_id: Optional[str] = None,
) -> Optional[Path]:
    """Return the Path for AGENT_MEMORY (markdown). When system_user_id is set (and not system/companion), uses workspace_dir/agent_memory/{user_id}.md; otherwise global path. Never raises."""
    try:
        root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        if not _is_global_agent_memory_user(system_user_id):
            uid = _sanitize_system_user_id(system_user_id)
            if uid:
                return root / "agent_memory" / f"{uid}.md"
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
    system_user_id: Optional[str] = None,
) -> bool:
    """Create AGENT_MEMORY markdown file if it does not exist (empty). Returns True if created or already existed."""
    path = get_agent_memory_file_path(workspace_dir=workspace_dir, agent_memory_path=agent_memory_path, system_user_id=system_user_id)
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
    system_user_id: Optional[str] = None,
) -> str:
    """
    Load AGENT_MEMORY markdown (curated long-term memory). Per-user when system_user_id is set; otherwise global.
    If max_chars > 0 and content is longer, returns only the last max_chars with an omission note.
    Returns file content or empty string.
    """
    root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
    path = get_agent_memory_file_path(workspace_dir=root, agent_memory_path=agent_memory_path, system_user_id=system_user_id)
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
    system_user_id: Optional[str] = None,
) -> bool:
    """
    Clear AGENT_MEMORY markdown (write empty file). Per-user when system_user_id is set. Used when memory is reset.
    Returns True if the file was cleared (or created empty), False if path is not configured.
    """
    root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
    path = get_agent_memory_file_path(workspace_dir=root, agent_memory_path=agent_memory_path, system_user_id=system_user_id)
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
    system_user_id: Optional[str] = None,
) -> Path:
    """Return the directory for daily memory markdown files (YYYY-MM-DD.md). Per-user when system_user_id is set: daily_memory/{user_id}/. Otherwise global: memory/ or daily_memory_dir. Never raises."""
    try:
        root = workspace_dir if workspace_dir is not None else _DEFAULT_WORKSPACE_DIR
        if not _is_global_agent_memory_user(system_user_id):
            uid = _sanitize_system_user_id(system_user_id)
            if uid:
                return root / "daily_memory" / uid
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
    system_user_id: Optional[str] = None,
) -> Path:
    """Return the Path for the daily memory markdown file (YYYY-MM-DD.md) for the given date. Per-user when system_user_id is set."""
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
    return base / f"{d.isoformat()}.md"


def ensure_daily_memory_file_exists(
    d: date,
    workspace_dir: Optional[Path] = None,
    daily_memory_dir: Optional[str] = None,
    system_user_id: Optional[str] = None,
) -> bool:
    """Create the daily memory markdown file for date d if it does not exist (empty). Returns True if created or already existed."""
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
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
    system_user_id: Optional[str] = None,
) -> str:
    """
    Load and concatenate daily memory markdown files for the given dates (newest last). Per-user when system_user_id is set.
    Returns a single string with optional "## YYYY-MM-DD" headers per file. If max_chars > 0, truncates with an omission note.
    Creates today's file if missing so the file exists for the model to append to later.
    """
    if not dates:
        return ""
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
    today = date.today()
    parts = []
    for d in sorted(dates):
        path = base / f"{d.isoformat()}.md"
        if d == today and not path.is_file():
            ensure_daily_memory_file_exists(d, workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
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
    system_user_id: Optional[str] = None,
) -> bool:
    """
    Append content to the daily memory markdown file for the given date (default: today). Per-user when system_user_id is set.
    Creates the file and parent dir if needed. Returns True on success.
    """
    if not content or not content.strip():
        return False
    day = d or date.today()
    path = get_daily_memory_path_for_date(day, workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
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
    system_user_id: Optional[str] = None,
) -> int:
    """Clear (truncate to empty) daily memory markdown files for the given dates. Per-user when system_user_id is set. Returns number of files cleared."""
    if not dates:
        return 0
    base = get_daily_memory_dir(workspace_dir=workspace_dir, daily_memory_dir=daily_memory_dir, system_user_id=system_user_id)
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
