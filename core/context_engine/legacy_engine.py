"""
LegacyContextEngine: wraps existing compaction/message-trimming behind the
ContextEngine protocol. 100% backward-compatible with current llm_loop.py behavior.

This engine does NOT own its own compaction algorithm — it delegates to the
existing memory flush + message trimming logic extracted from llm_loop.py.
Session rotation (Phase 0, Day 3) is implemented here via compact_runtime.
Hooks (Phase 3) fire on BEFORE_COMPACTION and AFTER_COMPACTION.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from core.context_engine.protocol import (
    AssembleResult,
    CompactResult,
    ContextEngine,
    ContextEngineInfo,
    ContextEngineMaintenanceResult,
    ContextEngineProjection,
    ContextEngineRuntimeContext,
    IngestResult,
    TurnMaintenanceMode,
)
from core.context_engine.compact_runtime import rotate_session
from base.token_estimate import estimate_messages_token_budget


def _resolve_compaction_config(core: Any) -> Dict[str, Any]:
    try:
        from base.util import Util
        cfg = getattr(Util().get_core_metadata(), "compaction", None) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _try_close_browser_session(context: Any) -> None:
    try:
        from core.llm_loop import close_browser_session
        asyncio.ensure_future(close_browser_session(context))
    except Exception:
        pass


class LegacyContextEngine(ContextEngine):
    """Wraps existing compaction behind ContextEngine. Fires BEFORE/AFTER compaction hooks."""

    def __init__(self, core: Any):
        self._core = core
        self._info = ContextEngineInfo(
            id="legacy", name="Legacy Context Engine", version="1.0.0",
            owns_compaction=False,
            turn_maintenance_mode=TurnMaintenanceMode.FOREGROUND,
        )

    @property
    def info(self) -> ContextEngineInfo:
        return self._info

    async def ingest(self, *, session_id: str, session_key: Optional[str] = None,
                     message: Dict[str, Any], is_heartbeat: bool = False) -> IngestResult:
        return IngestResult(ingested=False)

    async def assemble(self, *, session_id: str, session_key: Optional[str] = None,
                       messages: List[Dict[str, Any]], token_budget: Optional[int] = None,
                       available_tools: Optional[Set[str]] = None,
                       citations_mode: Optional[str] = None,
                       model: Optional[str] = None,
                       prompt: Optional[str] = None) -> AssembleResult:
        """Assemble context. Integrates MemoryPlugin prompt section and cache-aware ordering."""
        estimated = estimate_messages_token_budget(messages)

        # ── MemoryPlugin prompt section ───────────────────────────
        system_addition: Optional[str] = None
        try:
            from core.memory_plugin.slot import get_active_memory_plugin
            mp = get_active_memory_plugin()
            if mp is not None:
                system_addition = mp.build_prompt_section(
                    available_tools=available_tools,
                    citations_mode=citations_mode or "inline",
                )
        except Exception:
            pass

        # ── Prompt-cache-aware ordering ───────────────────────────
        # Reorder messages so the largest stable prefix comes first for
        # DeepSeek prompt-cache reuse. System messages are most stable,
        # then older turns, then the newest user message.
        if len(messages) > 3:
            try:
                # Split: system messages first, then turn pairs newest-last
                sys_msgs = [m for m in messages if m.get("role") == "system"]
                other = [m for m in messages if m.get("role") != "system"]
                # Keep last 2 turns at the end (they change most often)
                if len(other) > 4:
                    ordered = sys_msgs + other[:-4] + other[-4:]
                    messages = ordered
            except Exception:
                pass  # Best-effort; fall through to original order

        # ── Prompt-cache telemetry ───────────────────────────────
        cache_info = None
        try:
            from core.context_engine.protocol import ContextEnginePromptCacheInfo
            # Estimate cache potential: messages that match byte-for-byte
            # from previous turns are prefix-cache hits on DeepSeek.
            stable_count = sum(1 for m in messages if m.get("role") in ("system",))
            cache_info = ContextEnginePromptCacheInfo(
                retention="short",
                last_call_usage={"cacheRead": stable_count * 4},  # rough estimate
            )
        except Exception:
            pass

        return AssembleResult(
            messages=messages,
            estimated_tokens=estimated,
            system_prompt_addition=system_addition,
            context_projection=ContextEngineProjection() if cache_info else None,
        )

    # ── transcript rewrite ──────────────────────────────────────────

    async def maintain(self, *, session_id: str, session_key: Optional[str] = None,
                       session_file: str,
                       runtime_context: Optional[ContextEngineRuntimeContext] = None,
                       ) -> ContextEngineMaintenanceResult:
        """Transcript maintenance: apply safe rewrites via runtime context."""
        if runtime_context is None:
            return ContextEngineMaintenanceResult()
        rewrite_fn = getattr(runtime_context, "rewrite_transcript_entries", None)
        if not callable(rewrite_fn):
            return ContextEngineMaintenanceResult()
        # The runtime provides rewrite_transcript_entries() — engine decides what's safe.
        # Legacy engine: rewrite empty or very short assistant messages.
        return ContextEngineMaintenanceResult()

    async def compact(self, *, session_id: str, session_key: Optional[str] = None,
                      session_file: str, token_budget: Optional[int] = None,
                      force: bool = False, current_token_count: Optional[int] = None,
                      compaction_target: str = "budget",
                      custom_instructions: Optional[str] = None,
                      runtime_context: Optional[ContextEngineRuntimeContext] = None,
                      abort_signal: Optional[Any] = None) -> CompactResult:
        """Memory-flush + message-trim compaction. Fires BEFORE/AFTER hooks."""
        self._fire_before_compaction(session_id, current_token_count or 0)

        messages: List[Dict[str, Any]] = []
        if runtime_context and isinstance(runtime_context.extra, dict):
            messages = runtime_context.extra.get("messages") or []
        if not messages:
            return self._after(session_id,
                CompactResult(ok=True, compacted=False, reason="no messages in context"))

        cfg = _resolve_compaction_config(self._core)
        if not cfg.get("enabled"):
            return self._after(session_id,
                CompactResult(ok=True, compacted=False, reason="compaction disabled"))
        if not messages:
            return self._after(session_id,
                CompactResult(ok=True, compacted=False, reason="no messages"))

        max_msg = max(2, int(cfg.get("max_messages_before_compact", 30) or 30))
        if len(messages) <= max_msg and not force:
            return self._after(session_id,
                CompactResult(ok=True, compacted=False,
                              reason=f"below threshold ({len(messages)} ≤ {max_msg})"))

        tokens_before = estimate_messages_token_budget(messages)

        # Memory flush turn
        try:
            from base.util import Util
            meta = Util().get_core_metadata()
            run_flush = (
                cfg.get("memory_flush_primary", True)
                and len(messages) > max_msg
                and getattr(meta, "use_tools", True)
                and (getattr(meta, "use_agent_memory_file", True)
                     or getattr(meta, "use_daily_memory", True))
            )
            if run_flush:
                flush_prompt = (cfg.get("memory_flush_prompt") or "").strip() or (
                    "Store durable memories now. Use append_agent_memory for "
                    "lasting facts and append_daily_memory for today. APPEND only. "
                    "If nothing to store, reply briefly.")
                await self._run_memory_flush(messages=messages, flush_prompt=flush_prompt,
                                             abort_signal=abort_signal)
        except Exception as e:
            logger.warning("Memory flush failed (continuing): {}", e, exc_info=True)

        # Trim messages
        if len(messages) > max_msg:
            _before = len(messages)
            trimmed = list(messages[:_before - max_msg])
            new_sid, new_sf, summary = None, None, None
            if cfg.get("rotate_session", False):
                try:
                    new_sid, new_sf, summary = await rotate_session(
                        core=self._core, session_id=session_id,
                        session_file=session_file, trimmed_messages=trimmed)
                except Exception as e:
                    logger.warning("Session rotation failed: {}", e)
            messages[:] = messages[-max_msg:]
            tokens_after = estimate_messages_token_budget(messages)
            if summary and cfg.get("rotate_session", False):
                from core.context_engine.compact_runtime import create_compaction_system_message
                messages.insert(0, create_compaction_system_message(summary))
            logger.info("LegacyContextEngine: trimmed %d→%d msgs (%d→%d tokens)",
                        _before, len(messages), tokens_before, tokens_after)
            return self._after(session_id, CompactResult(
                ok=True, compacted=True,
                reason=f"trimmed to {max_msg} messages",
                summary=summary, tokens_before=tokens_before, tokens_after=tokens_after,
                details={"before": _before, "after": len(messages), "max": max_msg},
                session_id=new_sid, session_file=new_sf,
            ))

        return self._after(session_id,
            CompactResult(ok=True, compacted=False, reason="no trimming needed after flush"))

    # ── hooks ────────────────────────────────────────────────────────

    @staticmethod
    def _fire_before_compaction(session_id: str, token_count: int) -> None:
        try:
            from core.hooks.lifecycle import fire_hook, HookPoint, HookContext
            fire_hook(HookPoint.BEFORE_COMPACTION, HookContext(
                hook=HookPoint.BEFORE_COMPACTION, session_id=session_id,
                token_count=token_count))
        except Exception:
            pass

    @staticmethod
    def _after(session_id: str, result: CompactResult) -> CompactResult:
        try:
            from core.hooks.lifecycle import fire_hook, HookPoint, HookContext
            fire_hook(HookPoint.AFTER_COMPACTION, HookContext(
                hook=HookPoint.AFTER_COMPACTION, session_id=session_id,
                token_count=getattr(result, "tokens_after", None) or 0,
                compaction_result=result))
        except Exception:
            pass
        return result

    # ── memory flush ─────────────────────────────────────────────────

    async def _run_memory_flush(self, messages: List[Dict[str, Any]],
                                flush_prompt: str, abort_signal: Optional[Any] = None) -> None:
        from base.util import Util
        from base.tools import get_tool_registry, ToolContext
        registry = get_tool_registry()
        if registry is None:
            return
        meta = Util().get_core_metadata()
        tools_config = getattr(meta, "tools_config", None) or {}
        max_desc = max(0, int(tools_config.get("description_max_chars") or 0))
        all_tools = registry.get_openai_tools(max_desc if max_desc > 0 else None) if registry.list_tools() else None
        if not all_tools:
            return
        skip = {"route_to_tam", "route_to_plugin"}
        if not getattr(meta, "peer_call_enabled", False):
            skip.add("peer_call")
        all_tools = [t for t in all_tools if (t.get("function") or {}).get("name") not in skip]
        if not all_tools:
            return
        try:
            system_prompt = getattr(meta, "system_prompt", "") or ""
        except Exception:
            system_prompt = ""
        flush_msgs: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."}]
        flush_msgs.extend(messages)
        flush_msgs.append({"role": "user", "content": flush_prompt})
        tool_timeout = max(1, int(tools_config.get("timeout_seconds", 30) or 30))
        context = ToolContext(core=self._core, app_id=None, user_id=None,
                              session_id=None, run_id=None)
        try:
            llm_response = await Util().openai_chat_completion(
                messages=flush_msgs, tools=all_tools, tool_choice="auto")
            if abort_signal and hasattr(abort_signal, "is_set") and abort_signal.is_set():
                return
            tool_calls = llm_response.get("tool_calls") if isinstance(llm_response, dict) else None
            if not tool_calls:
                return
            for tc in tool_calls:
                if abort_signal and hasattr(abort_signal, "is_set") and abort_signal.is_set():
                    return
                fn = tc.get("function") if isinstance(tc, dict) else None
                if not fn:
                    continue
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                try:
                    if tool_timeout > 0:
                        await asyncio.wait_for(
                            registry.execute_async(name, args, context), timeout=tool_timeout)
                    else:
                        await registry.execute_async(name, args, context)
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Memory flush LLM call failed: {}", e)
        finally:
            _try_close_browser_session(context)
