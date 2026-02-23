"""
Companion chat store: one thread per (user_id, companion_name). Data is separate from main user DB.
Per-user settings (character, language, response_length, idle_days_before_nudge) override Core defaults.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

def _store_dir() -> Path:
    root = os.environ.get("HOMECLAW_ROOT") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    d = os.environ.get("COMPANION_STORE_DIR") or os.path.join(root, "database", "companion_store")
    return Path(d)


def _thread_path(user_id: str, companion_name: str) -> Path:
    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user_id or "").strip()) or "default"
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (companion_name or "companion").strip()) or "companion"
    _store_dir().mkdir(parents=True, exist_ok=True)
    return _store_dir() / f"{safe_uid}_{safe_name}.json"


def get_history(user_id: str, companion_name: str, num_rounds: int = 12) -> List[Dict[str, str]]:
    """Return last num_rounds turns: [{"role": "user"|"assistant", "content": "..."}, ...]."""
    path = _thread_path(user_id, companion_name)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        turns = data.get("turns") or []
        return turns[-num_rounds:] if num_rounds else turns
    except Exception:
        return []


def append_turn(user_id: str, companion_name: str, user_content: str, assistant_content: str) -> None:
    """Append one user+assistant turn. Creates file if needed."""
    path = _thread_path(user_id, companion_name)
    data = {"turns": []}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    turns = data.get("turns") or []
    turns.append({"role": "user", "content": user_content})
    turns.append({"role": "assistant", "content": assistant_content})
    data["turns"] = turns
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


def _settings_path(user_id: str) -> Path:
    safe_uid = "".join(c if c.isalnum() or c in "-_" else "_" for c in (user_id or "").strip()) or "default"
    _store_dir().mkdir(parents=True, exist_ok=True)
    return _store_dir() / f"{safe_uid}_settings.json"


def get_user_settings(user_id: str) -> Dict[str, Any]:
    """Return per-user companion settings (character, language, response_length, idle_days_before_nudge). Empty dict if none."""
    path = _settings_path(user_id)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def set_user_settings(user_id: str, settings: Dict[str, Any]) -> None:
    """Save per-user companion settings. Merges with existing; only provided keys are updated."""
    path = _settings_path(user_id)
    existing = get_user_settings(user_id)
    allowed = {"character", "language", "response_length", "idle_days_before_nudge"}
    for k, v in settings.items():
        if k in allowed and v is not None:
            if k == "idle_days_before_nudge":
                existing[k] = max(0, int(v))
            else:
                existing[k] = str(v).strip() if isinstance(v, str) else v
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
