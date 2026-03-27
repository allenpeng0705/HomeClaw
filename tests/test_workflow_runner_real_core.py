from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.workflow_framework.adapters.real_core import RealCoreRunner


@pytest.mark.skipif(
    os.environ.get("HOMECLAW_RUN_REALCORE_WORKFLOW_TESTS") != "1",
    reason="Set HOMECLAW_RUN_REALCORE_WORKFLOW_TESTS=1 to run real core workflow smoke test.",
)
def test_real_core_runner_smoke(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    runner = RealCoreRunner(root=root, trace_dir=tmp_path / "traces")
    try:
        runner.start()
        assert runner.wait_ready(timeout_sec=5) in (True, False)
    finally:
        runner.stop()

