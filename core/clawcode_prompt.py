"""Load optional Claw-Code system prompt addendum from config/clawcode.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from base.util import Util

_CLAWCODE_YAML = "clawcode.yml"


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_clawcode_yaml() -> Dict[str, Any]:
    root = Util().root_path()
    p = Path(root) / "config" / _CLAWCODE_YAML
    if not p.is_file():
        return {}
    return _read_yaml(p)


def load_system_prompt_addendum() -> str:
    """Multi-line string appended after the fixed Claw-Code session block in llm_loop."""
    data = load_clawcode_yaml()
    s = data.get("system_prompt_addendum")
    return (str(s).strip() if s is not None else "")
