"""
Per-user profile store: one JSON file per system user id.
Used for learned facts (name, birthday, preferences, families, etc.) and personalization.
See docs/UserProfileDesign.md.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


def _safe_user_id(system_user_id: str) -> str:
    """Make system_user_id safe for use as a filename (no path separators or reserved chars)."""
    if not system_user_id or not isinstance(system_user_id, str):
        return "_unknown"
    s = re.sub(r'[^\w\-.]', '_', system_user_id.strip())
    return s[:200] if len(s) > 200 else s or "_unknown"


def get_profile_dir(base_dir: Optional[str] = None) -> Path:
    """Return the profiles directory. If base_dir is None/empty, uses Util().data_path()/profiles."""
    if (base_dir or "").strip():
        p = Path(base_dir.strip())
    else:
        from base.util import Util
        p = Path(Util().data_path()) / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_profile(system_user_id: str, base_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Load the profile for the given system user id. Returns a dict (possibly empty).
    Per-user: each user has their own JSON file.
    """
    if not (system_user_id or "").strip():
        return {}
    safe_id = _safe_user_id(system_user_id)
    dir_path = get_profile_dir(base_dir)
    path = dir_path / f"{safe_id}.json"
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("profile_store: failed to read {}: {}", path, e)
        return {}


def update_profile(
    system_user_id: str,
    updates: Dict[str, Any],
    remove_keys: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
) -> None:
    """
    Merge updates into the user's profile and optionally remove keys. Atomic write.
    Per-user: updates only that user's JSON file.
    """
    if not (system_user_id or "").strip():
        return
    safe_id = _safe_user_id(system_user_id)
    dir_path = get_profile_dir(base_dir)
    path = dir_path / f"{safe_id}.json"
    current = get_profile(system_user_id, base_dir=base_dir)
    for k, v in (updates or {}).items():
        if k and isinstance(k, str):
            current[k] = v
    for k in (remove_keys or []):
        if k and isinstance(k, str) and k in current:
            del current[k]
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception as e:
        logger.warning("profile_store: failed to write {}: {}", path, e)
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def format_profile_for_prompt(profile: Dict[str, Any], max_chars: int = 2000) -> str:
    """Format profile dict as a compact string for system prompt (key: value or key: [list])."""
    if not profile:
        return ""
    lines = []
    for k, v in sorted(profile.items()):
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            v_str = ", ".join(str(x) for x in v[:20]) if v else ""
            if len(v) > 20:
                v_str += ", ..."
        elif isinstance(v, dict):
            v_str = json.dumps(v, ensure_ascii=False)[:500]
        else:
            v_str = str(v).strip()
        if v_str:
            lines.append(f"{k}: {v_str}")
    text = "\n".join(lines)
    if max_chars > 0 and len(text) > max_chars:
        text = text[: max_chars - 20] + "\n..."
    return text
