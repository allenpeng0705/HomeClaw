"""
Runtime patch for Instructor so Cognee cognify works with local LLMs.

1. **System message first:** We ensure the first message has role="system" so Instructor's
   "System message must be at the beginning" check passes. We (a) reorder messages to put
   any system message(s) at the top, and (b) if there is no system message, prepend one
   with minimal content so local stacks (llama.cpp, Ollama, litellm) see system first.

2. **Jinja templating:** Instructor 1.5+ can also raise via Jinja; we disable that as a
   fallback so the strict validation never runs.

3. **Tool-call count:** Local models often return 0 or multiple tool_calls. We patch
   OpenAISchema.parse_tools to accept 0 or >1.

Applied at memory package import (memory/__init__.py) and again at Cognee adapter/KB init via apply_instructor_patch_for_local_llm() (idempotent). Ensures local LLM cognify works before any cognee/instructor use.
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Minimal system message when none present (satisfies "system first"; task-agnostic for cognify).
DEFAULT_SYSTEM_MESSAGE: str = "You are a helpful assistant. Follow the user's instructions and respond in the requested format."

_PATCHED = False
_JINJA_PATCHED = False
_LITELLM_MESSAGES_PATCHED = False


def _ensure_system_first(messages: Any) -> List[Any]:
    """
    Ensure the first message has role='system' so Instructor's check passes.
    - Reorder: put all system messages at the top (then user/assistant).
    - If no system message exists, prepend one with DEFAULT_SYSTEM_MESSAGE.
    Never raises: on any error returns the original list (or copy) unchanged.
    """
    try:
        if messages is None:
            return []
        if not isinstance(messages, (list, tuple)):
            return list(messages) if hasattr(messages, "__iter__") and not isinstance(messages, (str, bytes)) else []
        out: List[Any] = []
        system_msgs: List[Any] = []
        for m in messages:
            try:
                if isinstance(m, dict) and (m.get("role") or "").strip().lower() == "system":
                    system_msgs.append(m)
                else:
                    out.append(m)
            except Exception:
                out.append(m)
        if system_msgs:
            return system_msgs + out
        return [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}] + list(out)
    except Exception:
        try:
            return list(messages) if isinstance(messages, (list, tuple)) else []
        except Exception:
            return []


def _apply_litellm_messages_patch() -> bool:
    """Ensure every litellm completion call gets messages with system first. Idempotent."""
    global _LITELLM_MESSAGES_PATCHED
    if _LITELLM_MESSAGES_PATCHED:
        return True
    try:
        import litellm  # noqa: PLC0415
        _orig_completion = getattr(litellm, "completion", None)
        _orig_acompletion = getattr(litellm, "acompletion", None)

        def _sync_wrapper(f: Any) -> Any:
            def _inner(*args: Any, **kwargs: Any) -> Any:
                try:
                    msgs = kwargs.get("messages")
                    if msgs is not None:
                        kwargs = {**kwargs, "messages": _ensure_system_first(msgs)}
                except Exception:
                    pass  # keep original kwargs so call never crashes
                return f(*args, **kwargs)
            return _inner

        def _async_wrapper(f: Any) -> Any:
            """Sync factory: returns the inner async function so litellm.acompletion is callable (acompletion(**kwargs) then await)."""
            async def _inner(*args: Any, **kwargs: Any) -> Any:
                try:
                    msgs = kwargs.get("messages")
                    if msgs is not None:
                        kwargs = {**kwargs, "messages": _ensure_system_first(msgs)}
                except Exception:
                    pass  # keep original kwargs so call never crashes
                return await f(*args, **kwargs)
            # Force Instructor to use async path (avoid 'coroutine' object is not callable when
            # is_async() wrongly returns False and retry_sync calls func() without await)
            setattr(_inner, "__homeclaw_force_async__", True)
            return _inner

        if _orig_completion is not None:
            litellm.completion = _sync_wrapper(_orig_completion)
        if _orig_acompletion is not None:
            litellm.acompletion = _async_wrapper(_orig_acompletion)
        _LITELLM_MESSAGES_PATCHED = True
        logger.debug("Instructor patch: litellm completion messages normalized (system first)")
        return True
    except Exception as e:
        logger.debug("LiteLLM messages patch not applied: %s", e)
    return False


def _extract_text_content(completion: Any) -> str:
    """Extract text from completion for content fallback (mirrors instructor utils)."""
    if hasattr(completion, "choices") and completion.choices:
        return (getattr(completion.choices[0].message, "content", None) or "") or ""
    if hasattr(completion, "text"):
        return completion.text or ""
    return ""


def _extract_json_from_codeblock(text: str) -> str:
    """Try to get JSON from markdown code block or raw text (minimal mirror of instructor)."""
    if not text or not text.strip():
        return "{}"
    text = text.strip()
    # ```json ... ``` or ``` ... ```
    for marker in ("```json", "```"):
        if marker in text:
            start = text.find(marker) + len(marker)
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()
    return text


def _apply_instructor_jinja_patch() -> bool:
    """Disable Instructor Jinja templating so 'System message must be at the beginning' raise_exception never runs. Idempotent."""
    global _JINJA_PATCHED
    if _JINJA_PATCHED:
        return True
    try:
        import instructor.templating as tpl  # noqa: PLC0415
        if hasattr(tpl, "apply_template"):
            _orig_apply = tpl.apply_template
            def _noop_template(text: Any, context: Any = None) -> Any:
                return text if text is not None else ""
            tpl.apply_template = _noop_template
            _JINJA_PATCHED = True
            logger.debug("Instructor patch: Jinja templating disabled (apply_template no-op)")
            return True
    except Exception as e:
        logger.debug("Instructor Jinja patch not applied: %s", e)
    return False


_INSTRUCTOR_IS_ASYNC_PATCHED = False


def _instructor_func_is_async(func: Any) -> bool:
    """Check if func should be treated as async (coroutine or our marker). Used so we never use retry_sync with an async func."""
    try:
        import inspect
        if getattr(func, "__homeclaw_force_async__", False):
            return True
        if inspect.iscoroutinefunction(func):
            return True
        # Unwrap bound methods and wrappers to get to the real callable
        f = getattr(func, "__func__", func)
        if inspect.iscoroutinefunction(f):
            return True
        return False
    except Exception:
        return False


def _apply_instructor_is_async_patch() -> bool:
    """Force async path for our wrapped litellm.acompletion so Instructor never uses retry_sync (which would call func() without await and cause 'coroutine' object is not callable). Idempotent."""
    global _INSTRUCTOR_IS_ASYNC_PATCHED
    if _INSTRUCTOR_IS_ASYNC_PATCHED:
        return True
    try:
        from instructor.utils import is_async as _orig_is_async
    except ImportError:
        try:
            from instructor.utils.core import is_async as _orig_is_async
        except ImportError:
            return False
    from collections.abc import Callable

    def _is_async_force(func: Callable[..., Any]) -> bool:
        try:
            if _instructor_func_is_async(func):
                return True
            return _orig_is_async(func)
        except Exception:
            return False  # never crash Instructor; fallback to sync path if detection fails

    try:
        import instructor.utils as utils
        utils.is_async = _is_async_force
    except Exception:
        pass
    try:
        import instructor.utils.core as core
        core.is_async = _is_async_force
    except Exception:
        pass
    try:
        import instructor.core.patch as patch_mod
        patch_mod.is_async = _is_async_force
    except Exception:
        pass
    _INSTRUCTOR_IS_ASYNC_PATCHED = True
    logger.debug("Instructor patch: is_async forces True for __homeclaw_force_async__ / coroutine")
    return True


def _apply_instructor_patch_force_async_path() -> bool:
    """
    When Instructor's patch() chooses sync wrapper but the underlying create is async, we get
    'coroutine' object is not callable. Intercept patch(): if the client's create is async
    (by our check), temporarily replace it with an async wrapper so is_async() sees a coroutine
    function and patch assigns new_create_async. Idempotent.
    """
    try:
        import instructor.core.patch as patch_mod
    except ImportError:
        return False
    if getattr(patch_mod, "_homeclaw_patch_wrapped", False):
        return True
    _orig_patch = patch_mod.patch

    def _wrapped_patch(client: Any = None, create: Any = None, mode: Any = None, **kwargs: Any) -> Any:
        func = create if create is not None else (getattr(client, "chat", None) and getattr(client.chat, "completions", None) and getattr(client.chat.completions, "create", None))
        # Force async path when create is async, or when client is AsyncOpenAI (Cognee uses aclient; litellm may wrap so is_async misses it).
        force_async = func is not None and _instructor_func_is_async(func)
        if not force_async and client is not None:
            cls_name = getattr(getattr(client, "__class__", None), "__name__", "") or ""
            if "Async" in cls_name:
                force_async = True
        if func is not None and force_async:
            # So that patch() sees an async create and assigns new_create_async, pass create= an async wrapper.
            _orig_create = func
            import asyncio

            async def _async_create(*args: Any, **kw: Any) -> Any:
                out = _orig_create(*args, **kw)
                # Underlying create may be sync but return a coroutine (e.g. litellm wrapper).
                if asyncio.iscoroutine(out):
                    return await out
                return out

            setattr(_async_create, "__homeclaw_force_async__", True)
            if client is not None:
                # Temporarily replace client's create so patch() sees an async func and assigns new_create_async.
                client.chat.completions.create = _async_create  # type: ignore[assignment]
                return _orig_patch(client=client, mode=mode or getattr(patch_mod, "Mode", None), **kwargs)
            if create is not None:
                return _orig_patch(create=_async_create, mode=mode or getattr(patch_mod, "Mode", None), **kwargs)
        return _orig_patch(client=client, create=create, mode=mode, **kwargs)

    patch_mod.patch = _wrapped_patch  # type: ignore[assignment]
    setattr(patch_mod, "_homeclaw_patch_wrapped", True)
    logger.debug("Instructor patch: patch() forces async path when create is async")
    return True


_RETRY_SYNC_PATCHED = False


def _apply_retry_sync_coroutine_handling() -> bool:
    """
    If Cognee/Instructor still use retry_sync with an async func (e.g. client created before our
    patch), func(*args, **kwargs) returns a coroutine and retry_sync crashes. Patch retry_sync
    so that when the result is a coroutine (or func is a coroutine), we run it and use the result.
    Idempotent.
    """
    global _RETRY_SYNC_PATCHED
    if _RETRY_SYNC_PATCHED:
        return True
    try:
        import asyncio
        import instructor.core.retry as retry_mod
    except ImportError:
        return False
    _orig_retry_sync = getattr(retry_mod, "retry_sync", None)
    if _orig_retry_sync is None:
        return False
    # Skip if we already patched (e.g. our wrapper is already there)
    if getattr(_orig_retry_sync, "_homeclaw_retry_sync_wrapper", False):
        _RETRY_SYNC_PATCHED = True
        return True

    def _retry_sync_wrapper(
        func: Any,
        response_model: Any,
        args: Any,
        kwargs: Any,
        context: Any = None,
        max_retries: Any = 1,
        strict: Any = None,
        mode: Any = None,
        hooks: Any = None,
    ) -> Any:
        # Wrap func so that if it IS a coroutine object or it RETURNS a coroutine, we run it.
        # Cognee/Instructor can pass either an async function or an already-created coroutine into
        # retry_sync. Calling a coroutine object raises "'coroutine' object is not callable", which
        # is the bug we are shielding against here.
        def _sync_func(*a: Any, **kw: Any) -> Any:
            import concurrent.futures

            def _run_coro(coro: Any) -> Any:
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, coro)
                        return future.result()
                except Exception:
                    raise

            # Case 1: func itself is a coroutine object (not callable) – run it directly.
            if asyncio.iscoroutine(func):
                return _run_coro(func)

            # Case 2: func is callable; it may return a coroutine.
            try:
                out = func(*a, **kw)
            except TypeError as te:
                msg = str(te).lower()
                # "'coroutine' object is not callable": treat func as coroutine object and run it.
                if "coroutine" in msg and "not callable" in msg and asyncio.iscoroutine(func):
                    return _run_coro(func)
                raise

            if asyncio.iscoroutine(out):
                return _run_coro(out)
            return out

        return _orig_retry_sync(
            func=_sync_func,
            response_model=response_model,
            args=args,
            kwargs=kwargs,
            context=context,
            max_retries=max_retries,
            strict=strict,
            mode=mode,
            hooks=hooks,
        )

    setattr(_retry_sync_wrapper, "_homeclaw_retry_sync_wrapper", True)
    retry_mod.retry_sync = _retry_sync_wrapper  # type: ignore[assignment]
    # instructor.core.patch does "from .retry import retry_sync" at import time, so it holds
    # a reference to the original. Cognee's path goes through patch.new_create_sync -> patch's
    # retry_sync(...). Update the patch module's reference so the sync path uses our wrapper.
    # If patch was already loaded (e.g. by Cognee before our init), update via sys.modules.
    import sys as _sys
    _patch_name = "instructor.core.patch"
    if _patch_name in _sys.modules:
        _sys.modules[_patch_name].retry_sync = retry_mod.retry_sync
    try:
        import instructor.core.patch as patch_mod  # noqa: PLC0415
        patch_mod.retry_sync = retry_mod.retry_sync
    except Exception:
        pass
    _RETRY_SYNC_PATCHED = True
    logger.debug("Instructor patch: retry_sync runs returned coroutines on running loop")
    return True


def apply_instructor_patch_for_local_llm() -> bool:
    """
    Patch for local LLMs: (1) ensure system message first (litellm); (2) disable Jinja templating;
    (3) OpenAISchema.parse_tools to accept 0 or multiple tool_calls; (4) force async for our acompletion wrapper so cognify never hits 'coroutine' is not callable;     (5) intercept patch() so client.create async -> use async wrapper; (6) retry_sync: if func returns a coroutine, run it in a thread. Idempotent; returns True if at least one patch applied.
    """
    global _PATCHED
    messages_ok = _apply_litellm_messages_patch()
    jinja_ok = _apply_instructor_jinja_patch()
    is_async_ok = _apply_instructor_is_async_patch()
    patch_force_async_ok = _apply_instructor_patch_force_async_path()
    retry_sync_ok = _apply_retry_sync_coroutine_handling()
    if _PATCHED:
        return messages_ok or jinja_ok or is_async_ok or patch_force_async_ok or retry_sync_ok or True
    try:
        # Prefer processing.function_calls (canonical); fallback to re-export
        try:
            from instructor.processing import function_calls as fc
        except ImportError:
            from instructor import function_calls as fc  # type: ignore[attr-defined]
        if not hasattr(fc, "OpenAISchema"):
            logger.debug("Instructor patch: OpenAISchema not found, skip")
            return messages_ok or jinja_ok or is_async_ok or patch_force_async_ok or retry_sync_ok
        OpenAISchema = fc.OpenAISchema
        original_parse_tools = OpenAISchema.parse_tools

        @classmethod
        def _parse_tools_local_friendly(
            cls: type,
            completion: Any,
            validation_context: Optional[dict[str, Any]] = None,
            strict: Optional[bool] = None,
        ) -> Any:
            if not getattr(completion, "choices", None) or len(completion.choices) == 0:
                _err = getattr(fc, "ResponseParsingError", ValueError)
                if _err is ValueError:
                    raise ValueError("No completion choices in LLM response")
                raise _err(
                    "No completion choices in LLM response",
                    mode="TOOLS",
                    raw_response=completion,
                )
            message = completion.choices[0].message
            if hasattr(message, "refusal") and message.refusal is not None:
                raise ValueError(
                    f"Unable to generate a response due to {message.refusal}"
                )
            tool_calls = message.tool_calls or []
            if len(tool_calls) == 0:
                # Content-only response (common with local LLMs): parse as JSON
                text = _extract_text_content(completion)
                json_content = _extract_json_from_codeblock(text or "")
                if not json_content or not json_content.strip():
                    json_content = "{}"
                return cls.model_validate_json(
                    json_content,
                    context=validation_context if validation_context is not None else {},
                    strict=strict if strict is not None else True,
                )
            if len(tool_calls) > 1:
                # Use first tool call instead of failing (local models sometimes return multiple)
                tool_call = tool_calls[0]
                try:
                    args = getattr(tool_call.function, "arguments", None)
                    if args is None:
                        raise ValueError("Tool call has no arguments")
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    return cls.model_validate_json(
                        args,
                        context=validation_context if validation_context is not None else {},
                        strict=strict if strict is not None else True,
                    )
                except Exception as e:
                    # Do not fall through to original (it asserts len==1); surface the real error
                    _err = getattr(fc, "ResponseParsingError", ValueError)
                    if _err is ValueError:
                        raise ValueError(f"Failed to parse first of multiple tool calls: {e}") from e
                    raise _err(
                        f"Failed to parse first of multiple tool calls: {e}",
                        mode="TOOLS",
                        raw_response=completion,
                    ) from e
            # classmethod binds cls; only pass (completion, validation_context, strict)
            return original_parse_tools(completion, validation_context, strict)

        OpenAISchema.parse_tools = _parse_tools_local_friendly
        _PATCHED = True
        logger.debug("Instructor patch applied for local LLM (0/multiple tool_calls)")
        return True
    except Exception as e:
        logger.debug("Instructor parse_tools patch not applied: %s", e)
    return messages_ok or jinja_ok or is_async_ok or patch_force_async_ok or retry_sync_ok
