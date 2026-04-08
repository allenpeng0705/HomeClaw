from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .assert_engine import assert_contract
from .scenario_loader import load_contracts, load_scenarios
from .trace_collector import load_trace_jsonl, validate_trace


@dataclass
class ScenarioRunResult:
    scenario_id: str
    ok: bool
    errors: List[str]
    trace_path: str
    response: str


def evaluate_scenario_from_trace(
    scenario_id: str,
    contract_name: str,
    contracts: Dict[str, Any],
    trace_path: Path,
    response: str = "",
) -> ScenarioRunResult:
    events = load_trace_jsonl(trace_path)
    errs = validate_trace(events)
    c = (contracts.get("contracts") or {}).get(contract_name) if isinstance(contracts, dict) else None
    if not isinstance(c, dict):
        errs.append(f"missing contract: {contract_name}")
        return ScenarioRunResult(scenario_id=scenario_id, ok=False, errors=errs, trace_path=str(trace_path), response=response)
    ar = assert_contract(events, c)
    errs.extend(ar.errors)
    return ScenarioRunResult(
        scenario_id=scenario_id,
        ok=(len(errs) == 0),
        errors=errs,
        trace_path=str(trace_path),
        response=response,
    )


def load_framework_inputs(scenarios_dir: Path, contracts_path: Path) -> Dict[str, Any]:
    return {
        "scenarios": load_scenarios(scenarios_dir),
        "contracts": load_contracts(contracts_path),
    }

