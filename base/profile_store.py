"""
Per-user profile store: one JSON file per (user_id, HomeClaw).
Profile is owned by HomeClaw only; path is profiles/{user_id}/HomeClaw.json.
Used for learned facts (name, birthday, preferences, families, etc.) and personalization.
See docs/UserProfileDesign.md and UserFriendsModelFullDesign.md Step 4.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

PROFILE_FRIEND_ID = "HomeClaw"


def _safe_user_id(system_user_id: str) -> str:
    """Make system_user_id safe for use as a path segment (no path separators or reserved chars). Never raises."""
    try:
        if not system_user_id or not isinstance(system_user_id, str):
            return "_unknown"
        s = re.sub(r'[^\w\-.]', '_', str(system_user_id).strip())
        return s[:200] if len(s) > 200 else s or "_unknown"
    except Exception:
        return "_unknown"


def get_profile_dir(base_dir: Optional[str] = None) -> Path:
    """Return the profiles directory. If base_dir is None/empty, uses Util().data_path()/profiles. Never raises."""
    try:
        if (base_dir or "").strip():
            p = Path(str(base_dir).strip())
        else:
            from base.util import Util
            p = Path(Util().data_path()) / "profiles"
        p.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        from base.util import Util
        return Path(Util().data_path()) / "profiles"


def _profile_path(dir_path: Path, safe_id: str) -> Path:
    """Path for (user_id, HomeClaw): dir_path / safe_id / HomeClaw.json."""
    return dir_path / safe_id / f"{PROFILE_FRIEND_ID}.json"


def _legacy_profile_path(dir_path: Path, safe_id: str) -> Path:
    """Legacy path: dir_path / safe_id.json (pre-Step4)."""
    return dir_path / f"{safe_id}.json"


def get_profile(system_user_id: str, base_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Load the profile for the given system user id (stored under (user_id, HomeClaw)).
    Returns a dict (possibly empty). Migrates from legacy profiles/{id}.json if present. Never raises.
    """
    try:
        if not (str(system_user_id or "").strip()):
            return {}
    except Exception:
        return {}
    try:
        safe_id = _safe_user_id(system_user_id)
        dir_path = get_profile_dir(base_dir)
        path = _profile_path(dir_path, safe_id)
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception as e:
                logger.warning("profile_store: failed to read {}: {}", path, e)
                return {}
        legacy = _legacy_profile_path(dir_path, safe_id)
        if legacy.is_file():
            try:
                with open(legacy, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data = data if isinstance(data, dict) else {}
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.debug("profile_store: migrated {} -> {}", legacy, path)
                return data
            except Exception as e:
                logger.warning("profile_store: migrate read failed {}: {}", legacy, e)
        return {}
    except Exception as e:
        logger.debug("profile_store: get_profile failed: {}", e)
        return {}


def update_profile(
    system_user_id: str,
    updates: Dict[str, Any],
    remove_keys: Optional[List[str]] = None,
    base_dir: Optional[str] = None,
) -> None:
    """
    Merge updates into the user's profile (stored under (user_id, HomeClaw)) and optionally remove keys. Atomic write.
    """
    try:
        if not (str(system_user_id or "").strip()):
            return
    except Exception:
        return
    try:
        safe_id = _safe_user_id(system_user_id)
        dir_path = get_profile_dir(base_dir)
        path = _profile_path(dir_path, safe_id)
        current = get_profile(system_user_id, base_dir=base_dir)
        for k, v in (updates or {}).items():
            if k and isinstance(k, str):
                current[k] = v
        for k in (remove_keys or []):
            if k and isinstance(k, str) and k in current:
                del current[k]
        path.parent.mkdir(parents=True, exist_ok=True)
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
    except Exception as e:
        logger.debug("profile_store: update_profile failed: {}", e)


def clear_all_profiles(base_dir: Optional[str] = None) -> int:
    """
    Delete all user profile JSON files (profiles/{id}/HomeClaw.json and legacy profiles/{id}.json). Used when memory is reset.
    Returns the number of profile files removed. Never raises.
    """
    try:
        dir_path = get_profile_dir(base_dir)
        if not dir_path.exists() or not dir_path.is_dir():
            return 0
        removed = 0
        for path in dir_path.glob("*.json"):
            if path.is_file():
                try:
                    path.unlink()
                    removed += 1
                except Exception as e:
                    logger.warning("profile_store: failed to remove {}: {}", path, e)
        for subdir in dir_path.iterdir():
            if subdir.is_dir():
                profile_file = subdir / f"{PROFILE_FRIEND_ID}.json"
                if profile_file.is_file():
                    try:
                        profile_file.unlink()
                        removed += 1
                    except Exception as e:
                        logger.warning("profile_store: failed to remove {}: {}", profile_file, e)
        return removed
    except Exception as e:
        logger.debug("profile_store: clear_all_profiles failed: {}", e)
        return 0


def format_profile_for_prompt(profile: Dict[str, Any], max_chars: int = 2000) -> str:
    """Format profile dict as a compact string for system prompt (key: value or key: [list]). Never raises."""
    if not profile or not isinstance(profile, dict):
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
    try:
        cap = max(0, int(max_chars)) if max_chars is not None else 2000
    except (TypeError, ValueError):
        cap = 2000
    if cap > 0 and len(text) > cap:
        text = text[: cap - 20] + "\n..."
    return text
