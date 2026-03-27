#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.workflow_framework.report_diff import diff_event_summaries, summarize_events
from tests.workflow_framework.trace_collector import load_trace_jsonl


def main() -> int:
    p = argparse.ArgumentParser(description="Compare two workflow trace JSONL files.")
    p.add_argument("--baseline", required=True, help="Baseline trace jsonl path.")
    p.add_argument("--candidate", required=True, help="Candidate trace jsonl path.")
    args = p.parse_args()
    b = load_trace_jsonl(Path(args.baseline))
    c = load_trace_jsonl(Path(args.candidate))
    report = diff_event_summaries(summarize_events(b), summarize_events(c))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("changed") else 0


if __name__ == "__main__":
    raise SystemExit(main())

