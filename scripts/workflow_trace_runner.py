#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
try:
    import yaml
except Exception:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.workflow_framework.mock_harness import run_mock_turn
from tests.workflow_framework.runner import evaluate_scenario_from_trace, load_framework_inputs
from tests.workflow_framework.adapters.real_core import RealCoreRunner


def _load_run_config(root: Path, config_path: str) -> Dict[str, Any]:
    if not (config_path or "").strip() or yaml is None:
        return {}
    p = Path(config_path.strip())
    if not p.is_absolute():
        p = (root / p).resolve()
    if not p.is_file():
        return {}
    try:
        obj = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace")) or {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _read_failed_scenarios_from_report(path_str: str, root: Path) -> List[str]:
    if not (path_str or "").strip():
        return []
    p = Path(path_str.strip())
    if not p.is_absolute():
        p = (root / p).resolve()
    if not p.is_file():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    rows = obj.get("results") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return []
    out: List[str] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if bool(r.get("ok")):
            continue
        sid = str(r.get("scenario_id") or "").strip()
        if sid:
            out.append(sid)
    return sorted(set(out))


def _write_json_report(root: Path, mode: str, report: Dict[str, Any], target_path: str = "") -> str:
    out_path: Path
    if (target_path or "").strip():
        out_path = Path(target_path.strip())
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
    else:
        reports_dir = root / "output" / "workflow_traces" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = reports_dir / f"workflow-trace-{mode}-{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(out_path)


def _clean_trace_output_dir(trace_dir: Path) -> int:
    """Remove all files/dirs under trace_dir. Returns removed item count."""
    removed = 0
    if not trace_dir.exists():
        return removed
    for p in sorted(trace_dir.iterdir(), key=lambda x: x.name):
        try:
            if p.is_dir():
                for child in sorted(p.rglob("*"), key=lambda x: len(x.parts), reverse=True):
                    try:
                        if child.is_file() or child.is_symlink():
                            child.unlink(missing_ok=True)
                        elif child.is_dir():
                            child.rmdir()
                    except Exception:
                        continue
                p.rmdir()
                removed += 1
            else:
                p.unlink(missing_ok=True)
                removed += 1
        except Exception:
            continue
    return removed


def _line_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _snapshot_trace_lines(trace_dir: Path) -> Dict[str, int]:
    snap: Dict[str, int] = {}
    if not trace_dir.is_dir():
        return snap
    for p in trace_dir.glob("*.jsonl"):
        snap[p.name] = _line_count(p)
    return snap


def _extract_new_events_to_temp_file(trace_dir: Path, before: Dict[str, int], scenario_id: str) -> Tuple[Path, int]:
    out_lines: List[str] = []
    if trace_dir.is_dir():
        for p in sorted(trace_dir.glob("*.jsonl"), key=lambda x: x.stat().st_mtime):
            old_n = int(before.get(p.name, 0))
            cur_n = _line_count(p)
            if cur_n <= old_n:
                continue
            try:
                with p.open("r", encoding="utf-8", errors="replace") as f:
                    for idx, ln in enumerate(f):
                        if idx >= old_n:
                            s = (ln or "").strip()
                            if s:
                                out_lines.append(s)
            except Exception:
                continue
    out_dir = trace_dir / "_scenario_slices"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"{scenario_id}.jsonl"
    tmp.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    return tmp, len(out_lines)


def _write_markdown_report(root: Path, mode: str, report: Dict[str, Any], target_path: str = "") -> str:
    out_path: Path
    if (target_path or "").strip():
        out_path = Path(target_path.strip())
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
    else:
        reports_dir = root / "output" / "workflow_traces" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = reports_dir / f"workflow-trace-{mode}-{ts}.md"

    total = int(report.get("total") or 0)
    failed = int(report.get("failed") or 0)
    passed = max(0, total - failed)
    rows = report.get("results") if isinstance(report.get("results"), list) else []

    lines: List[str] = []
    lines.append("# Workflow Trace Run Report")
    lines.append("")
    lines.append(f"- Mode: `{mode}`")
    lines.append(f"- Total: `{total}`")
    lines.append(f"- Passed: `{passed}`")
    lines.append(f"- Failed: `{failed}`")
    lines.append("")
    lines.append("## Scenario Results")
    lines.append("")
    lines.append("| Scenario | Status | Events | Trace |")
    lines.append("|---|---:|---:|---|")
    for r in rows:
        sid = str(r.get("scenario_id") or "")
        ok = bool(r.get("ok"))
        status = "PASS" if ok else "FAIL"
        events_n = str(r.get("events_appended") if r.get("events_appended") is not None else "-")
        tpath = str(r.get("trace_path") or "")
        lines.append(f"| `{sid}` | {status} | {events_n} | `{tpath}` |")

    lines.append("")
    lines.append("## Failures")
    lines.append("")
    any_fail = False
    for r in rows:
        if bool(r.get("ok")):
            continue
        any_fail = True
        sid = str(r.get("scenario_id") or "")
        tpath = str(r.get("trace_path") or "")
        lines.append(f"### `{sid}`")
        lines.append(f"- Trace: `{tpath}`")
        errs = r.get("errors") if isinstance(r.get("errors"), list) else []
        if errs:
            lines.append("- Errors:")
            for e in errs:
                lines.append(f"  - {str(e)}")
        else:
            lines.append("- Errors: (none listed)")
        lines.append("")
    if not any_fail:
        lines.append("- No failures.")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)


def _discover_api_key(root: Path) -> str:
    env_key = (os.environ.get("HOMECLAW_INBOUND_API_KEY") or "").strip()
    if env_key:
        return env_key
    if yaml is None:
        return ""
    try:
        p = root / "config" / "core.yml"
        if not p.is_file():
            return ""
        obj = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace")) or {}
        if not isinstance(obj, dict):
            return ""
        return str(obj.get("auth_api_key") or "").strip()
    except Exception:
        return ""


def _discover_real_core_user_id(root: Path) -> str:
    env_uid = (os.environ.get("HOMECLAW_WORKFLOW_TEST_USER_ID") or "").strip()
    if env_uid:
        return env_uid
    if yaml is None:
        return "workflow-test-user"
    try:
        p = root / "config" / "user.yml"
        if not p.is_file():
            return "workflow-test-user"
        obj = yaml.safe_load(p.read_text(encoding="utf-8", errors="replace")) or {}
        if not isinstance(obj, dict):
            return "workflow-test-user"
        users = obj.get("users")
        if not isinstance(users, list):
            return "workflow-test-user"
        # Prefer a configured IM identity because inbound permission checks use it.
        for u in users:
            if not isinstance(u, dict):
                continue
            im_list = u.get("im")
            if isinstance(im_list, list):
                for im in im_list:
                    s = str(im or "").strip()
                    if s:
                        return s
        # Fallback to first user id if present.
        for u in users:
            if not isinstance(u, dict):
                continue
            uid = str(u.get("id") or "").strip()
            if uid:
                return uid
    except Exception:
        pass
    return "workflow-test-user"


def _run_in_process_mock(
    root: Path,
    scenario_ids: List[str],
    report_markdown: bool,
    report_markdown_path: str,
    report_json: bool,
    report_json_path: str,
    clean_all_traces: bool,
) -> int:
    tests_dir = root / "tests"
    loaded = load_framework_inputs(
        tests_dir / "workflow_scenarios",
        tests_dir / "workflow_framework" / "contracts.yaml",
    )
    scenarios = loaded["scenarios"]
    if scenario_ids:
        scenario_set = set(scenario_ids)
        scenarios = [s for s in scenarios if s.id in scenario_set]
    trace_dir = root / "output" / "workflow_traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    if clean_all_traces:
        _clean_trace_output_dir(trace_dir)
    os.environ["HOMECLAW_WORKFLOW_TRACE"] = "1"
    os.environ["HOMECLAW_WORKFLOW_TRACE_DIR"] = str(trace_dir)
    results: List[Dict[str, Any]] = []
    fail = 0
    for s in scenarios:
        run = run_mock_turn(s.prompt, trace_dir=trace_dir)
        ev = evaluate_scenario_from_trace(
            scenario_id=s.id,
            contract_name=s.contract,
            contracts=loaded["contracts"],
            trace_path=Path(run["trace_path"]),
            response=str(run.get("response") or ""),
        )
        row = {
            "scenario_id": s.id,
            "ok": ev.ok,
            "errors": ev.errors,
            "trace_path": ev.trace_path,
        }
        results.append(row)
        if not ev.ok:
            fail += 1
    report = {"total": len(results), "failed": fail, "results": results}
    if report_json:
        json_path = _write_json_report(root, "in_process_mock", report, target_path=report_json_path)
        report["json_report"] = json_path
    if report_markdown:
        md_path = _write_markdown_report(root, "in_process_mock", report, target_path=report_markdown_path)
        report["markdown_report"] = md_path
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if fail else 0


def _run_real_core(
    root: Path,
    scenario_ids: List[str],
    api_key: str,
    base_url: str,
    start_core: bool,
    user_id: str,
    inbound_timeout_sec: int,
    report_markdown: bool,
    report_markdown_path: str,
    report_json: bool,
    report_json_path: str,
    clean_all_traces: bool,
) -> int:
    tests_dir = root / "tests"
    loaded = load_framework_inputs(
        tests_dir / "workflow_scenarios",
        tests_dir / "workflow_framework" / "contracts.yaml",
    )
    scenarios = loaded["scenarios"]
    if scenario_ids:
        scenario_set = set(scenario_ids)
        scenarios = [s for s in scenarios if s.id in scenario_set]
    trace_dir = root / "output" / "workflow_traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    if clean_all_traces:
        _clean_trace_output_dir(trace_dir)
    os.environ["HOMECLAW_WORKFLOW_TRACE"] = "1"
    os.environ["HOMECLAW_WORKFLOW_TRACE_DIR"] = str(trace_dir)
    eff_api_key = (api_key or "").strip() or _discover_api_key(root)
    eff_user_id = (user_id or "").strip() or _discover_real_core_user_id(root)
    runner = RealCoreRunner(root=root, trace_dir=trace_dir, api_key=eff_api_key, base_url=base_url)
    fail = 0
    results: List[Dict[str, Any]] = []
    try:
        if start_core:
            runner.start()
            if not runner.wait_ready(timeout_sec=180):
                raise RuntimeError("Core not ready within timeout (180s).")
        for s in scenarios:
            before = _snapshot_trace_lines(trace_dir)
            try:
                data = runner.run_prompt(s.prompt, user_id=eff_user_id, timeout_sec=inbound_timeout_sec)
                trace_path, appended_events = _extract_new_events_to_temp_file(trace_dir, before, s.id)
                ev = evaluate_scenario_from_trace(
                    scenario_id=s.id,
                    contract_name=s.contract,
                    contracts=loaded["contracts"],
                    trace_path=trace_path,
                    response=str(data.get("text") or ""),
                )
                row = {
                    "scenario_id": s.id,
                    "ok": ev.ok,
                    "errors": ev.errors,
                    "trace_path": ev.trace_path,
                    "status": data.get("status"),
                    "events_appended": appended_events,
                }
                results.append(row)
                if not ev.ok:
                    fail += 1
            except Exception as e:
                trace_path, appended_events = _extract_new_events_to_temp_file(trace_dir, before, s.id)
                row = {
                    "scenario_id": s.id,
                    "ok": False,
                    "errors": [f"scenario execution error: {str(e)}"],
                    "trace_path": str(trace_path),
                    "status": "error",
                    "events_appended": appended_events,
                }
                results.append(row)
                fail += 1
    finally:
        if start_core:
            runner.stop()
    report = {"total": len(results), "failed": fail, "results": results}
    if report_json:
        json_path = _write_json_report(root, "real_core", report, target_path=report_json_path)
        report["json_report"] = json_path
    if report_markdown:
        md_path = _write_markdown_report(root, "real_core", report, target_path=report_markdown_path)
        report["markdown_report"] = md_path
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if fail else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Run HomeClaw workflow trace scenarios.")
    p.add_argument("--mode", choices=["in_process_mock", "real_core"], default="in_process_mock")
    p.add_argument("--config", default="", help="YAML run profile path.")
    p.add_argument("--scenario", action="append", default=[], help="Scenario id (repeatable).")
    p.add_argument("--failed-only-from", default="", help="Run only scenarios that failed in a prior JSON report file.")
    p.add_argument("--api-key", default="", help="Inbound API key for real_core mode. Optional: auto-discovered from env or config/core.yml.")
    p.add_argument("--base-url", default=os.environ.get("HOMECLAW_BASE_URL", "http://127.0.0.1:9000"), help="Core base URL for real_core mode.")
    p.add_argument("--user-id", default=os.environ.get("HOMECLAW_WORKFLOW_TEST_USER_ID", ""), help="Inbound user_id for real_core mode. Optional: auto-discovered from config/user.yml im list.")
    p.add_argument("--start-core", action="store_true", help="Start Core subprocess for real_core mode.")
    p.add_argument(
        "--inbound-timeout",
        type=int,
        default=None,
        metavar="SEC",
        help="Max seconds to wait for each async /inbound turn (poll /inbound/result). "
        "Default: HOMECLAW_WORKFLOW_INBOUND_TIMEOUT_SEC or 600.",
    )
    p.add_argument("--report-markdown", action="store_true", default=True, help="Write a human-readable Markdown report in addition to JSON output (default: enabled).")
    p.add_argument("--no-report-markdown", action="store_false", dest="report_markdown", help="Disable Markdown report output.")
    p.add_argument("--report-markdown-path", default="", help="Optional output path for Markdown report. Defaults to output/workflow_traces/reports/<timestamp>.md")
    p.add_argument("--report-json", action="store_true", default=True, help="Write machine-readable JSON report (default: enabled).")
    p.add_argument("--no-report-json", action="store_false", dest="report_json", help="Disable JSON report file output.")
    p.add_argument("--report-json-path", default="", help="Optional output path for JSON report. Defaults to output/workflow_traces/reports/<timestamp>.json")
    p.add_argument("--clean-all-traces", action="store_true", help="Delete all files under output/workflow_traces before running scenarios.")
    args = p.parse_args()
    root = ROOT
    cfg = _load_run_config(root, str(args.config or ""))

    # Effective values: CLI > config > defaults
    cfg_mode = str(cfg.get("mode") or "").strip()
    eff_mode = str(args.mode or "").strip() or cfg_mode or "in_process_mock"
    if cfg_mode in ("in_process_mock", "real_core") and (not str(args.mode or "").strip() or str(args.mode) == "in_process_mock"):
        # argparse default for --mode is in_process_mock; respect config when user didn't set mode explicitly.
        if "--mode" not in sys.argv:
            eff_mode = cfg_mode

    cfg_sc = cfg.get("scenarios") if isinstance(cfg.get("scenarios"), dict) else {}
    cfg_include = cfg_sc.get("include") if isinstance(cfg_sc.get("include"), list) else []
    cfg_exclude = cfg_sc.get("exclude") if isinstance(cfg_sc.get("exclude"), list) else []
    cli_scenarios = list(args.scenario or [])
    eff_scenarios = cli_scenarios if cli_scenarios else [str(x) for x in cfg_include if str(x).strip()]

    failed_only_from = str(args.failed_only_from or "").strip() or str(cfg_sc.get("failed_only_from") or "").strip()
    using_failed_only = bool(failed_only_from)
    if failed_only_from:
        failed_set = set(_read_failed_scenarios_from_report(failed_only_from, root))
        if eff_scenarios:
            eff_scenarios = [s for s in eff_scenarios if s in failed_set]
        else:
            eff_scenarios = sorted(failed_set)
    if cfg_exclude:
        ex = set(str(x) for x in cfg_exclude)
        eff_scenarios = [s for s in eff_scenarios if s not in ex]
    if using_failed_only and not eff_scenarios:
        # Keep explicit empty-set semantics: run zero scenarios instead of "all".
        eff_scenarios = ["__NO_SCENARIOS__"]

    cfg_outputs = cfg.get("outputs") if isinstance(cfg.get("outputs"), dict) else {}
    cfg_md = cfg_outputs.get("markdown") if isinstance(cfg_outputs.get("markdown"), dict) else {}
    cfg_json = cfg_outputs.get("json") if isinstance(cfg_outputs.get("json"), dict) else {}
    eff_report_md = bool(cfg_md.get("enabled", True))
    eff_report_md = bool(args.report_markdown) if ("--report-markdown" in sys.argv or "--no-report-markdown" in sys.argv) else eff_report_md
    eff_report_md_path = str(args.report_markdown_path or "").strip() or str(cfg_md.get("path") or "").strip()
    eff_report_json = bool(cfg_json.get("enabled", True))
    eff_report_json = bool(args.report_json) if ("--report-json" in sys.argv or "--no-report-json" in sys.argv) else eff_report_json
    eff_report_json_path = str(args.report_json_path or "").strip() or str(cfg_json.get("path") or "").strip()

    eff_clean = bool(cfg.get("clean_all_traces", False))
    if "--clean-all-traces" in sys.argv:
        eff_clean = bool(args.clean_all_traces)

    if eff_mode == "in_process_mock":
        rc = _run_in_process_mock(
            root,
            scenario_ids=list(eff_scenarios),
            report_markdown=eff_report_md,
            report_markdown_path=eff_report_md_path,
            report_json=eff_report_json,
            report_json_path=eff_report_json_path,
            clean_all_traces=eff_clean,
        )
        return rc
    if eff_mode == "real_core":
        _t = args.inbound_timeout
        cfg_real = cfg.get("real_core") if isinstance(cfg.get("real_core"), dict) else {}
        if _t is None and cfg_real.get("inbound_timeout_sec") is not None:
            try:
                _t = int(cfg_real.get("inbound_timeout_sec"))
            except Exception:
                _t = None
        if _t is None:
            env_t = (os.environ.get("HOMECLAW_WORKFLOW_INBOUND_TIMEOUT_SEC") or "").strip()
            try:
                _t = int(env_t) if env_t else 600
                if _t < 30:
                    _t = 600
            except Exception:
                _t = 600
        eff_base_url = str(args.base_url or "").strip() or str(cfg_real.get("base_url") or "").strip() or "http://127.0.0.1:9000"
        eff_api_key = str(args.api_key or "").strip() or str(cfg_real.get("api_key") or "").strip()
        eff_user_id = str(args.user_id or "").strip() or str(cfg_real.get("user_id") or "").strip()
        eff_start_core = bool(args.start_core) if "--start-core" in sys.argv else bool(cfg_real.get("start_core", False))
        return _run_real_core(
            root,
            scenario_ids=list(eff_scenarios),
            api_key=eff_api_key,
            base_url=eff_base_url,
            start_core=eff_start_core,
            user_id=eff_user_id,
            inbound_timeout_sec=int(_t),
            report_markdown=eff_report_md,
            report_markdown_path=eff_report_md_path,
            report_json=eff_report_json,
            report_json_path=eff_report_json_path,
            clean_all_traces=eff_clean,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

