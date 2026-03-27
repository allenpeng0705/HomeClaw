from __future__ import annotations

import json
from pathlib import Path

from tests.workflow_framework.runner import evaluate_scenario_from_trace, load_framework_inputs


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

