"""
Optional inner LLM turn for selected skills (bounded tool loop).

Configure `tools.run_skill_subagent_skills` (list of folder names) and optionally
`agent_limits.skill_subagent` with `max_tool_rounds` and `max_estimated_tokens_per_turn`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from loguru import logger


async def delegate_run_skill_to_inner_agent(
    core: Any,
    skill_folder: str,
    script_arg: str,
    args_input: Any,
    context: Any,
    *,
    user_query_tail: str = "",
) -> str:
    """
    Run one full answer_from_memory turn with stricter limits (see request_metadata skill_subagent_*).
    Depth is tracked to avoid infinite run_skill recursion; depth >= 1 falls through to normal run_skill in the caller.
    """
    pr = getattr(context, "request", None)
    if pr is None:
        return "Error: skill subagent requires an active request context."

    from base.util import Util
    from core.llm_loop import answer_from_memory

    md = dict(getattr(pr, "request_metadata", None) or {})
    md["skill_subagent_depth"] = int(md.get("skill_subagent_depth", 0) or 0) + 1
    al = getattr(Util().get_core_metadata(), "agent_limits", None) or {}
    sub_al = al.get("skill_subagent") if isinstance(al.get("skill_subagent"), dict) else {}
    try:
        if sub_al.get("max_tool_rounds") is not None:
            md["skill_subagent_max_tool_rounds"] = max(1, int(sub_al["max_tool_rounds"]))
    except (TypeError, ValueError):
        pass
    try:
        if sub_al.get("max_estimated_tokens_per_turn") is not None:
            md["skill_subagent_max_estimated_tokens"] = max(0, int(sub_al["max_estimated_tokens_per_turn"]))
    except (TypeError, ValueError):
        pass
    pr2 = pr.model_copy(update={"request_metadata": md})
    uq = (getattr(pr, "text", None) or "").strip()
    if user_query_tail and user_query_tail not in uq:
        uq = (uq + " " + user_query_tail).strip()
    try:
        args_repr = json.dumps(
            list(args_input) if isinstance(args_input, (list, tuple)) else args_input,
            ensure_ascii=False,
        )
    except Exception:
        args_repr = str(args_input)
    inner_q = (
        f"[Skill subagent — `{skill_folder}`] Run script `{script_arg or '(see SKILL.md)'}` "
        f"with args: {args_repr}. Follow SKILL.md for this skill; use tools as needed. "
        f"Original user message: {uq}"
    )
    run_inner = str(uuid.uuid4())
    try:
        pair = await answer_from_memory(
            core,
            inner_q,
            messages=[],
            app_id=getattr(context, "app_id", None) or "homeclaw",
            user_name=getattr(context, "user_name", None) or "",
            user_id=getattr(context, "user_id", None) or "",
            session_id=getattr(context, "session_id", None) or "",
            run_id=run_inner,
            request=pr2,
        )
    except Exception as e:
        logger.warning("skill subagent answer_from_memory failed: {}", e)
        return f"Error: skill subagent failed: {e!s}"

    if pair and isinstance(pair, tuple) and pair[0]:
        return str(pair[0]).strip()
    return "Error: skill subagent produced no output."
