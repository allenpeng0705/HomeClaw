"""
Runtime patch for Instructor so Cognee cognify works with local LLMs.

Local models (e.g. via LiteLLM) often return 0 tool_calls (content-only) or multiple
tool_calls. Instructor's parse_tools asserts exactly 1 tool call, which triggers
"Instructor does not support multiple tool calls, use List[Model] instead".

This module patches instructor.processing.function_calls.OpenAISchema.parse_tools to:
- When there are 0 tool_calls: parse message.content as JSON (same as parse_json path).
- When there are >1 tool_calls: use the first one (Cognee expects one structured blob).
- Otherwise: behave like the original (exactly 1 tool call).

Apply once at Cognee adapter init via apply_instructor_patch_for_local_llm().
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PATCHED = False


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


def apply_instructor_patch_for_local_llm() -> bool:
    """
    Patch Instructor's OpenAISchema.parse_tools to accept 0 or multiple tool_calls
    so Cognee cognify works with local LLMs. Idempotent; returns True if patch applied.
    """
    global _PATCHED
    if _PATCHED:
        return True
    try:
        # Prefer processing.function_calls (canonical); fallback to re-export
        try:
            from instructor.processing import function_calls as fc
        except ImportError:
            from instructor import function_calls as fc  # type: ignore[attr-defined]
        if not hasattr(fc, "OpenAISchema"):
            logger.debug("Instructor patch: OpenAISchema not found, skip")
            return False
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
            return original_parse_tools(cls, completion, validation_context, strict)

        OpenAISchema.parse_tools = _parse_tools_local_friendly
        _PATCHED = True
        logger.debug("Instructor patch applied for local LLM (0/multiple tool_calls)")
        return True
    except Exception as e:
        logger.debug("Instructor patch not applied: %s", e)
        return False
