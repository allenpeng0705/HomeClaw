"""
Execute confirmed pending user actions by kind.

- Registered handlers: multi-step or special logic (e.g. daily_brief_magazine_pdf).
- Generic fallback: payload with \"tool\" + \"arguments\" (dict) runs one registry tool name allowlisted
  in tools.pending_user_action_generic_tools (default: run_skill only).

Security: payloads are produced by Core/trusted code, not raw user text. Generic run_skill still honors
normal tool executors and sandbox rules; do not write arbitrary DB rows from untrusted input.
"""
import re
from datetime import datetime
from typing import Any, Dict, Set, Tuple

from loguru import logger

from base.tools import ToolContext

try:
    from core.services.tool_helpers import tool_result_looks_like_error
except (ImportError, ModuleNotFoundError):
    from core.tool_helpers_fallback import tool_result_looks_like_error


Outcome = str  # "executed" | "failed_keep" | "cancelled_unsupported"


async def _handler_daily_brief_magazine_pdf(registry: Any, context: ToolContext, payload: Dict[str, Any]) -> str:
    try:
        max_items = int((payload or {}).get("max_items") or 20)
    except (TypeError, ValueError):
        max_items = 20
    lang = str((payload or {}).get("lang") or "all").strip() or "all"
    max_items = max(1, min(100, max_items))
    daily_res = await registry.execute_async(
        "run_skill",
        {
            "skill_name": "daily-brief-1.0.0",
            "script": "fetch_rss.py",
            "args": ["fetch", "--max", str(max_items), "--lang", lang],
        },
        context,
    )
    if not isinstance(daily_res, str) or not daily_res.strip():
        return "Could not fetch the news brief. Please try again."
    if tool_result_looks_like_error(daily_res):
        return daily_res.strip()
    md = daily_res.strip()
    md = re.sub(r"(?is)\n+json\s*\(machine-readable\)\s*:\s*```json[\s\S]*$", "", md).strip()
    md = re.sub(r"(?is)\n+json\s*:\s*```json[\s\S]*$", "", md).strip()
    if len(md) > 12000:
        md = md[:12000]
    out = f"daily_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_res = await registry.execute_async(
        "run_skill",
        {
            "skill_name": "magazine-render-1.0.0",
            "script": "render_magazine.py",
            "args": [
                "render-md",
                "--title", "Daily Brief",
                "--theme", "dispatch",
                "--profile", "literature",
                "--md", md,
                "--preview", "auto",
                "--out", out,
            ],
        },
        context,
    )
    if isinstance(pdf_res, str) and pdf_res.strip():
        return pdf_res.strip()
    return md


# kind -> async (registry, context, payload) -> str
_PENDING_HANDLERS = {
    "daily_brief_magazine_pdf": _handler_daily_brief_magazine_pdf,
}


def _generic_allowlist(tools_config: Dict[str, Any]) -> Set[str]:
    raw = tools_config.get("pending_user_action_generic_tools")
    if not isinstance(raw, list) or not raw:
        return {"run_skill"}
    s = {str(x).strip() for x in raw if str(x).strip()}
    return s if s else {"run_skill"}


async def _try_generic_single_tool(
    registry: Any,
    context: ToolContext,
    payload: Dict[str, Any],
    allow: Set[str],
) -> str:
    tool = payload.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        raise ValueError("missing tool")
    name = tool.strip()
    if not allow:
        raise ValueError("generic tool allowlist is empty")
    if name not in allow:
        raise ValueError("tool not allowed for generic pending execution")
    args = payload.get("arguments")
    if args is None:
        args = payload.get("args")
    # Require a JSON object (not run_skill's CLI args list) so payloads stay explicit and reviewable.
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object (dict), not a list")
    return await registry.execute_async(name, args, context)


async def execute_pending_user_action(
    kind: str,
    payload: Dict[str, Any],
    registry: Any,
    context: ToolContext,
    tools_config: Dict[str, Any],
) -> Tuple[str, Outcome]:
    """
    Returns (user_message, outcome).

    outcome:
    - executed: success; caller should mark DB row executed
    - failed_keep: error; leave row pending for retry
    - cancelled_unsupported: unknown kind and no generic tool payload; caller should cancel row
    """
    k = (kind or "").strip()
    if not k:
        return (
            "That offer is no longer valid. Please ask again. （该请求已失效，请重新说明。）",
            "cancelled_unsupported",
        )

    handler = _PENDING_HANDLERS.get(k)
    if handler is not None:
        try:
            out = await handler(registry, context, payload)
            msg = out.strip() if isinstance(out, str) else str(out)
            if not msg:
                return (
                    "The action returned an empty result. Please try again. （无结果，请重试。）",
                    "failed_keep",
                )
            return (msg, "executed")
        except Exception as e:
            logger.warning("pending_user_action handler {} failed: {}", k, e)
            return (
                "Something went wrong while running that action. Please try again. （执行失败，请重试。）",
                "failed_keep",
            )

    allow = _generic_allowlist(tools_config or {})
    try:
        msg = await _try_generic_single_tool(registry, context, payload, allow)
        if isinstance(msg, str) and msg.strip():
            return (msg.strip(), "executed")
        return (
            "The action returned an empty result. Please try again. （无结果，请重试。）",
            "failed_keep",
        )
    except ValueError as e:
        logger.debug("pending_user_action generic not applicable: {}", e)
        return (
            "This confirmation is not supported or has expired. Please describe what you want again. "
            "（该确认无法执行或已过期，请重新说明需求。）",
            "cancelled_unsupported",
        )
    except Exception as e:
        logger.warning("pending_user_action generic execute failed: {}", e)
        return (
            "Something went wrong while running that action. Please try again. （执行失败，请重试。）",
            "failed_keep",
        )


def register_pending_user_action_handler(kind: str, handler: Any) -> None:
    """Optional: register additional kind handlers at startup (e.g. from a plugin)."""
    k = (kind or "").strip()
    if not k or handler is None:
        return
    if k in _PENDING_HANDLERS and _PENDING_HANDLERS[k] is not handler:
        logger.warning(
            "register_pending_user_action_handler: overwriting existing handler for kind={}",
            k,
        )
    _PENDING_HANDLERS[k] = handler
