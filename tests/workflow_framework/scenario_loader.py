from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class Scenario:
    id: str
    prompt: str
    contract: str
    metadata: Dict[str, Any]


def _load_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required for workflow scenario loading.")
    raw = path.read_text(encoding="utf-8", errors="replace")
    obj = yaml.safe_load(raw) or {}
    if not isinstance(obj, dict):
        raise ValueError(f"Scenario file must be object: {path}")
    return obj


def load_scenarios(dir_path: Path) -> List[Scenario]:
    out: List[Scenario] = []
    if not dir_path.is_dir():
        return out
    for p in sorted(dir_path.glob("*.yaml")):
        data = _load_yaml(p)
        sid = str(data.get("id") or p.stem).strip()
        prompt = str(data.get("prompt") or "").strip()
        contract = str(data.get("contract") or "").strip()
        if not sid or not prompt or not contract:
            continue
        out.append(Scenario(id=sid, prompt=prompt, contract=contract, metadata=data))
    return out


def load_contracts(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    return _load_yaml(path)

