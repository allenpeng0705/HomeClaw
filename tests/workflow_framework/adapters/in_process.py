from __future__ import annotations

import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

from core.llm_loop import answer_from_memory


class _DummyCore:
    def __init__(self) -> None:
        self.chatDB = SimpleNamespace(add=lambda **kwargs: None)
        self.prune_session_transcript = lambda **kwargs: 0

    def get_pending_plugin_call(self, *args, **kwargs):
        return None

    def set_pending_plugin_call(self, *args, **kwargs):
        return None

    def clear_pending_plugin_call(self, *args, **kwargs):
        return None


async def run_prompt_in_process(
    prompt: str,
    *,
    trace_dir: Path,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    os.environ["HOMECLAW_WORKFLOW_TRACE"] = "1"
    os.environ["HOMECLAW_WORKFLOW_TRACE_DIR"] = str(trace_dir)
    core = _DummyCore()
    req = SimpleNamespace(
        request_id=uuid.uuid4().hex,
        user_id="workflow-test-user",
        system_user_id="workflow-test-user",
        friend_id="HomeClaw",
        text=prompt,
        request_metadata={},
        model_copy=lambda deep=True: SimpleNamespace(request_metadata={}),
    )
    if isinstance(request_overrides, dict):
        for k, v in request_overrides.items():
            setattr(req, k, v)
    response, memory_turn_data = await answer_from_memory(
        core=core,
        query=prompt,
        app_id="homeclaw",
        user_name="workflow-test",
        user_id="workflow-test-user",
        session_id="workflow-session",
        run_id=run_id,
        request=req,
        messages=[],
    )
    return {
        "run_id": run_id,
        "response": response,
        "memory_turn_data": memory_turn_data,
        "trace_path": str((trace_dir / f"{run_id}.jsonl").resolve()),
    }

