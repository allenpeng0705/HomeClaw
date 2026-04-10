from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.workflow_framework.mock_harness import run_mock_turn
from tests.workflow_framework.runner import evaluate_scenario_from_trace, load_framework_inputs

_TESTS_DIR = Path(__file__).resolve().parent
_WORKFLOW_LOADED = load_framework_inputs(
    _TESTS_DIR / "workflow_scenarios",
    _TESTS_DIR / "workflow_framework" / "contracts.yaml",
)
_WORKFLOW_SCENARIOS = _WORKFLOW_LOADED["scenarios"]


def _write_trace(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_framework_inputs_load():
    root = Path(__file__).resolve().parent
    loaded = load_framework_inputs(
        root / "workflow_scenarios",
        root / "workflow_framework" / "contracts.yaml",
    )
    assert loaded["scenarios"]
    assert "contracts" in loaded["contracts"]


def test_contract_evaluation_from_trace(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    _write_trace(
        trace_path,
        [
            {
                "schema_version": "1.0",
                "run_id": "r1",
                "turn_id": "t1",
                "timestamp": 1.0,
                "sequence": 1,
                "event_type": "skill_call_started",
                "component": "run_skill",
                "summary": "run_skill started",
                "details": {"skill_name": "daily-brief-1.0.0"},
            },
            {
                "schema_version": "1.0",
                "run_id": "r1",
                "turn_id": "t1",
                "timestamp": 2.0,
                "sequence": 2,
                "event_type": "arg_normalization",
                "component": "run_skill",
                "summary": "run_skill argv finalized",
                "details": {
                    "argv": [
                        "fetch-vmprint",
                        "--max",
                        "20",
                        "--lang",
                        "cn",
                        "--theme",
                        "dispatch",
                        "--output_format",
                        "browser_preview_html",
                        "--document-layout",
                        "digest_table",
                    ]
                },
            },
        ],
    )
    root = Path(__file__).resolve().parent
    loaded = load_framework_inputs(
        root / "workflow_scenarios",
        root / "workflow_framework" / "contracts.yaml",
    )
    res = evaluate_scenario_from_trace(
        scenario_id="daily_brief_ast_default",
        contract_name="daily_brief_ast_default",
        contracts=loaded["contracts"],
        trace_path=trace_path,
    )
    assert res.ok is True


@pytest.mark.parametrize("scenario", _WORKFLOW_SCENARIOS, ids=lambda s: s.id)
def test_workflow_scenario_in_process_mock(scenario, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the same mock turn + contract checks as scripts/workflow_trace_runner.py --mode in_process_mock."""
    monkeypatch.setenv("HOMECLAW_WORKFLOW_TRACE", "1")
    monkeypatch.setenv("HOMECLAW_WORKFLOW_TRACE_DIR", str(tmp_path))
    run = run_mock_turn(scenario.prompt, trace_dir=tmp_path)
    ev = evaluate_scenario_from_trace(
        scenario_id=scenario.id,
        contract_name=scenario.contract,
        contracts=_WORKFLOW_LOADED["contracts"],
        trace_path=Path(run["trace_path"]),
        response=str(run.get("response") or ""),
    )
    assert ev.ok, f"{scenario.id}: {ev.errors}"

