"""
Planner–Executor: one planning LLM call → JSON plan (goal + steps); executor runs steps (Phase 3+).
DAG: fixed flows per category (no planner); run steps in order, resolve args_from (user_message_path, result_of_step_N, llm_from_step_N).

Phase 2: planning only — build prompt, call LLM, parse and validate plan. Execution still via ReAct.
Phase 3: executor runs plan steps (resolve placeholders, execute tools); on success return final result; on error fall back to ReAct.
Phase 4: on step error, call planner again (re-plan) with goal + execution log + error; resume with new plan up to max_replans.
Phase 5: when requires_final_summary is true, one LLM call with execution log → short user-facing reply.
See docs_design/PlannerExecutorAndDAG.md.

Stability: All public functions are defensive and never raise. Invalid inputs, parse failures, and LLM/network
errors are caught; callers get None or (False, {}, error_msg) and can fall back to ReAct. run_executor wraps
the main loop in try/except so unexpected exceptions return a failure tuple instead of propagating.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

# Prefix for tool execution errors returned by the registry
TOOL_ERROR_PREFIX = "Error running tool"


# System prompt for the planner: output JSON only, use only allowed tools.
PLANNER_SYSTEM = """You are a task planner. Given the user's request and the intent category, output a single JSON object with:
- "goal": short description of the task (one sentence).
- "steps": array of steps. Each step has: "id" (string, e.g. "1", "2"), "tool" (exact tool name from the list), "arguments" (object with parameters for that tool), "optional" (boolean, default false). Use only tools from the available list.
- "requires_final_summary": boolean (true if the user should get a short natural-language reply after steps run).

Output only valid JSON. No markdown, no code fence, no explanation. For run_skill, set "arguments": {"skill_name": "<exact skill folder name>"}. You may use placeholders in arguments like "<from_step_1>" to mean "use the text result of step 1"; the executor will replace them."""

# Re-plan: same JSON schema; planner sees goal, what ran so far, and the failure.
REPLAN_SYSTEM = """You are a task planner. A previous plan failed at one step. Given the original goal, the execution log (steps that already ran and their results), and the error, output a NEW single JSON object with:
- "goal": same or updated goal (one sentence).
- "steps": array of steps from this point. You may retry the failed step with different arguments, skip to a later step, or define a new sequence. Use only tools from the allowed list. Each step: "id", "tool", "arguments", "optional" (boolean).
- "requires_final_summary": boolean.

You may use placeholders in arguments: "<from_step_N>" = text result of step N from the execution log. Output only valid JSON. No markdown, no explanation."""

# Final summary (Phase 5): one short LLM call to turn execution outcome into a user-facing reply.
FINAL_SUMMARY_SYSTEM = """You are a helpful assistant. The user asked for a task; the system has just run a plan (tools/steps) and completed it. Given the goal and a brief summary of what was done and the last result, write a short natural-language reply to the user (1–3 sentences). Mention the outcome and any link or key result if relevant. No tools, no JSON. Write only the reply."""

# DAG: one short LLM call to fill a single field (e.g. title) from a prior step result.
DAG_FILL_FIELD_SYSTEM = """You are a helper. Given the content below (output from a previous step), produce a single short value for the requested field (e.g. a title, or a one-line summary). Output only that value, no explanation, no markdown, no quotes. One line only."""

# DAG: one LLM call to convert document content into full Markdown (e.g. for markdown_to_pdf).
DAG_LLM_MARKDOWN_SYSTEM = """You are a document assistant. Given the document content below, produce a clear Markdown report or summary. Use headings (##), lists, and paragraphs. Output only the Markdown body—no explanation, no "Here is the summary" wrapper. The output will be converted to PDF; keep it well-structured and readable."""

# DAG: one short LLM call to summarize content for a direct reply (e.g. when search result is short and we skip save_result_page).
DAG_SUMMARIZE_FOR_REPLY_SYSTEM = """You are a helpful assistant. The user asked a question and the system retrieved the content below. Summarize it concisely in 1–4 sentences so the user gets a direct answer. Output only the summary, no preamble or "Here is..."."""

# DAG: compose email draft from user message + contacts list (for send_email flow).
DAG_COMPOSE_EMAIL_SYSTEM = """You are an email assistant. You have a contacts list (name, email, and optional notes) and the user's request. Output a single email draft in this exact format, with no other text before or after:

To: <email address from contacts or user>
Subject: <short subject line>
Body:
<email body, multiple lines allowed>

Use the contacts list to resolve names to email addresses. If the user said "send to John", pick John's email from the list. If the list is empty or no match, use the user's wording. Output only the draft in the format above."""


def get_flow_for_categories(categories: List[str], config: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Return the first flow whose category is in the given list. config is planner_executor_config; flows = config.get("flows").
    Returns None if no flow matches. Never raises.
    """
    if not categories or not isinstance(config, dict):
        return None
    flows = config.get("flows")
    if not isinstance(flows, dict) or not flows:
        return None
    for c in categories:
        if not c or not isinstance(c, str):
            continue
        cat = (c or "").strip().lower()
        for flow_name, flow in flows.items():
            if not isinstance(flow, dict):
                continue
            flow_cat = (flow.get("category") or "").strip().lower()
            if flow_cat and flow_cat == cat:
                return flow
    return None


def _extract_path_from_user_message(message: Optional[str]) -> Optional[str]:
    """
    Extract a relative file path from the user message. Works for:
    - Paths under sandbox folders: documents/, share/, output/, images/, work/, downloads/, knowledge/
    - Bare filenames with document extension: report.pdf, myfile.docx (no leading folder)
    Returns None if no path found; then DAG uses the configured default (e.g. documents/). Never raises.
    """
    if not message or not isinstance(message, str) or not message.strip():
        return None
    q = message.strip()
    # 1) Path with known folder prefix (documents/, share/, output/, etc.)
    m = re.search(
        r"(documents|share|output|images|work|downloads|knowledge)/[^\s\]\[\)\,\"\'\n]+\.(?:pdf|docx|doc|pptx|ppt|txt|md|html)",
        q,
        re.IGNORECASE,
    )
    if m and not m.group(0).startswith("/"):
        return m.group(0)
    # 2) Bare filename with document extension (e.g. "report.pdf", "resume.docx")
    m2 = re.search(
        r"\b([a-zA-Z0-9_\-\u4e00-\u9fff][^\s\]\[\)\,\"\'\n]*\.(?:pdf|docx|doc|pptx|ppt|txt|md|html))\b",
        q,
        re.IGNORECASE,
    )
    if m2:
        cand = m2.group(1).strip()
        if "/" not in cand and "\\" not in cand and len(cand) < 200:
            return cand
    return None


def _user_message_path_to_pdf_output(message: Optional[str], default: str = "output/report.pdf") -> str:
    """If user message contains a file path, return output/<basename>.pdf; else return default. Never raises."""
    p = _extract_path_from_user_message(message)
    if not p:
        return default or "output/report.pdf"
    base = os.path.basename(p)
    name, _ = os.path.splitext(base)
    if not name:
        return default or "output/report.pdf"
    return f"output/{name}.pdf"


def _extract_folder_from_user_message(message: Optional[str]) -> str:
    """Extract a sandbox folder name from the user message (e.g. 'documents', 'images', 'output'). Returns '.' if none found. Never raises."""
    if not message or not isinstance(message, str) or not message.strip():
        return "."
    q = message.strip().lower()
    for folder in ("documents", "images", "output", "work", "downloads", "knowledge", "share"):
        if folder in q:
            return folder
    return "."


def _user_message_text(message: Optional[str], max_chars: int = 500) -> str:
    """Return the user message trimmed to max_chars (for use as query, etc.). Never raises."""
    if not message or not isinstance(message, str):
        return ""
    return message.strip()[:max_chars]


async def _dag_llm_fill_field(
    completion_fn: Any,
    step_result: str,
    field_name: str,
    default_value: str,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """One short LLM call to generate a single field value (e.g. title) from step result. Returns default on failure. Never raises."""
    if not completion_fn or not step_result:
        return default_value or ""
    content_preview = (step_result[:3000] + "…") if len(step_result) > 3000 else step_result
    user_content = f"Field to produce: {field_name}.\n\nContent:\n{content_preview}"
    messages = [
        {"role": "system", "content": DAG_FILL_FIELD_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    try:
        planner_llm = (config or {}).get("planner_llm") or None
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(messages=messages, llm_name=planner_llm)
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if response and isinstance(response, str) and response.strip():
            return response.strip()[:500]
    except Exception as e:
        logger.debug("DAG fill-field LLM failed: {}", e)
    return default_value or ""


async def _dag_llm_markdown_from_step(
    completion_fn: Any,
    step_result: str,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """One LLM call to turn document content into full Markdown (for PDF flow). Returns empty string on failure. Never raises."""
    if not completion_fn or not step_result or not step_result.strip():
        return ""
    content_preview = (step_result[:12000] + "…") if len(step_result) > 12000 else step_result
    messages = [
        {"role": "system", "content": DAG_LLM_MARKDOWN_SYSTEM},
        {"role": "user", "content": f"Document content:\n\n{content_preview}"},
    ]
    try:
        planner_llm = (config or {}).get("planner_llm") or None
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(messages=messages, llm_name=planner_llm)
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if response and isinstance(response, str) and response.strip():
            return response.strip()[:100000]
    except Exception as e:
        logger.debug("DAG markdown-from-step LLM failed: {}", e)
    return ""


async def _dag_llm_summarize_for_reply(
    completion_fn: Any,
    content: str,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """One LLM call to summarize content for a direct reply (e.g. short search result). Returns empty on failure. Never raises."""
    if not completion_fn or not content or not content.strip():
        return content or ""
    preview = (content[:4000] + "…") if len(content) > 4000 else content
    messages = [
        {"role": "system", "content": DAG_SUMMARIZE_FOR_REPLY_SYSTEM},
        {"role": "user", "content": preview},
    ]
    try:
        planner_llm = (config or {}).get("planner_llm") or None
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(messages=messages, llm_name=planner_llm)
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if response and isinstance(response, str) and response.strip():
            return response.strip()[:3000]
    except Exception as e:
        logger.debug("DAG summarize-for-reply LLM failed: {}", e)
    return content[:2000] + ("…" if len(content) > 2000 else "")


async def _dag_llm_compose_email_from_step(
    completion_fn: Any,
    step_result: str,
    user_message: Optional[str],
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """One LLM call to compose an email draft (To, Subject, Body) from contacts content + user request. Returns empty on failure. Never raises."""
    if not completion_fn or not step_result or not step_result.strip():
        return ""
    contacts_preview = (step_result[:6000] + "…") if len(step_result) > 6000 else step_result
    user_preview = (user_message or "").strip()[:1000] or "(no message)"
    messages = [
        {"role": "system", "content": DAG_COMPOSE_EMAIL_SYSTEM},
        {"role": "user", "content": f"Contacts list:\n{contacts_preview}\n\nUser request:\n{user_preview}"},
    ]
    try:
        planner_llm = (config or {}).get("planner_llm") or None
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(messages=messages, llm_name=planner_llm)
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if response and isinstance(response, str) and response.strip():
            return response.strip()[:8000]
    except Exception as e:
        logger.debug("DAG compose-email LLM failed: {}", e)
    return ""


async def _resolve_flow_step_args(
    step: Dict[str, Any],
    step_index_1based: int,
    step_results: Dict[str, str],
    user_message: Optional[str],
    completion_fn: Optional[Any],
    config: Optional[Dict[str, Any]],
    flow: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolve args and args_from for a DAG step. step_index_1based is 1-based. Returns merged args dict. Never raises.
    args_from: key -> [source, default?]. source: user_message_path | result_of_step_N | llm_from_step_N.
    """
    out: Dict[str, Any] = {}
    fixed = step.get("args")
    if isinstance(fixed, dict):
        out.update(fixed)
    args_from = step.get("args_from")
    if not isinstance(args_from, dict):
        return out
    step_id_str = str(step_index_1based)
    for key, spec in args_from.items():
        if not isinstance(spec, list) or not spec:
            continue
        source = spec[0] if spec else None
        default = spec[1] if len(spec) > 1 else ""
        if source == "user_message_path":
            val = _extract_path_from_user_message(user_message)
            out[key] = val if val is not None else (default if default is not None else "")
        elif source == "user_message_path_pdf":
            out[key] = _user_message_path_to_pdf_output(user_message, default or "output/report.pdf")
        elif source == "user_message_folder":
            out[key] = _extract_folder_from_user_message(user_message) or (default if default is not None else ".")
        elif source == "user_message_text":
            out[key] = _user_message_text(user_message, 500) or (default or "")
        elif isinstance(source, str) and source.startswith("result_of_step_"):
            n = source.replace("result_of_step_", "").strip()
            out[key] = (step_results.get(n) or step_results.get(str(n)) or "") if n else (default or "")
        elif isinstance(source, str) and source.startswith("llm_from_step_"):
            n = source.replace("llm_from_step_", "").strip()
            prior = (step_results.get(n) or step_results.get(str(n)) or "") if n else ""
            if completion_fn and prior:
                val = await _dag_llm_fill_field(completion_fn, prior, key, default or "", config)
                out[key] = val
            else:
                out[key] = default or ""
        elif isinstance(source, str) and source.startswith("llm_markdown_from_step_"):
            n = source.replace("llm_markdown_from_step_", "").strip()
            prior = (step_results.get(n) or step_results.get(str(n)) or "") if n else ""
            if completion_fn and prior:
                val = await _dag_llm_markdown_from_step(completion_fn, prior, config)
                out[key] = val if val else (default or "")
            else:
                out[key] = default or ""
        elif isinstance(source, str) and source.startswith("llm_compose_email_from_step_"):
            n = source.replace("llm_compose_email_from_step_", "").strip()
            prior = (step_results.get(n) or step_results.get(str(n)) or "") if n else ""
            if completion_fn and prior and user_message:
                val = await _dag_llm_compose_email_from_step(completion_fn, prior, user_message, config)
                out[key] = val if val else (default or "")
            else:
                out[key] = default or ""
        elif isinstance(source, str) and source.startswith("flow_config:"):
            key_name = source.split(":", 1)[1].strip() if ":" in source else ""
            if isinstance(flow, dict) and key_name:
                val = flow.get(key_name)
                out[key] = val if val not in (None, "") else (default if default is not None else "")
            else:
                out[key] = default if default is not None else ""
        else:
            out[key] = default if default is not None else ""
    return out


async def _resolve_single_output_spec(
    spec: List[Any],
    step_results: Dict[str, str],
    user_message: Optional[str],
    completion_fn: Optional[Any],
    config: Optional[Dict[str, Any]],
    flow: Optional[Dict[str, Any]],
) -> str:
    """Resolve a single output spec (e.g. for output_only step) to a string. spec = [source, default]. Never raises."""
    if not isinstance(spec, list) or not spec:
        return ""
    source = spec[0] if spec else None
    default = spec[1] if len(spec) > 1 else ""
    if source == "user_message_text":
        return _user_message_text(user_message, 500) or (default or "")
    if isinstance(source, str) and source.startswith("result_of_step_"):
        n = source.replace("result_of_step_", "").strip()
        return (step_results.get(n) or step_results.get(str(n)) or "") if n else (default or "")
    if isinstance(source, str) and source.startswith("llm_compose_email_from_step_"):
        n = source.replace("llm_compose_email_from_step_", "").strip()
        prior = (step_results.get(n) or step_results.get(str(n)) or "") if n else ""
        if completion_fn and prior and user_message:
            val = await _dag_llm_compose_email_from_step(completion_fn, prior, user_message, config)
            return val if val else (default or "")
        return default or ""
    if isinstance(source, str) and source.startswith("flow_config:"):
        key_name = source.split(":", 1)[1].strip() if ":" in source else ""
        if isinstance(flow, dict) and key_name:
            val = flow.get(key_name)
            return str(val) if val not in (None, "") else (default or "")
        return default or ""
    return default or ""


async def run_dag(
    flow: Dict[str, Any],
    registry: Any,
    context: Any,
    user_message: Optional[str] = None,
    completion_fn: Optional[Any] = None,
    config: Optional[Dict[str, Any]] = None,
    tool_names: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """
    Execute a DAG flow: run steps in order, resolve args_from (user_message_path, result_of_step_N, llm_from_step_N).
    Returns (True, final_result_str) on success, (False, error_msg) on failure. Never raises.
    """
    if not flow or not isinstance(flow, dict):
        return False, "Invalid flow"
    if not registry or not getattr(registry, "execute_async", None):
        return False, "No tool registry"
    steps = flow.get("steps")
    if not isinstance(steps, list) or not steps:
        return False, "Flow has no steps"
    config = config if isinstance(config, dict) else {}
    tool_names_set = set(tool_names or [])
    step_results: Dict[str, str] = {}
    last_result = ""
    when_skipped_summarize = bool(flow.get("when_step_skipped_return_summary_of_previous"))
    try:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return False, f"Step {i + 1} is not an object"
            step_index_1based = i + 1
            output_only_spec = step.get("output_only")
            output_append = step.get("append") or ""

            if output_only_spec is not None:
                # Step without tool: resolve output_only (e.g. draft text) and optional append (e.g. confirm prompt)
                result = await _resolve_single_output_spec(
                    output_only_spec if isinstance(output_only_spec, list) else [output_only_spec],
                    step_results,
                    user_message,
                    completion_fn,
                    config,
                    flow,
                )
                if output_append:
                    result = (result or "") + str(output_append)
                step_id = str(step_index_1based)
                step_results[step_id] = result
                last_result = result
                continue

            tool_name = (step.get("tool") or "").strip()
            if not tool_name:
                return False, f"Step {i + 1} has no tool"
            if tool_names_set and tool_name not in tool_names_set:
                return False, f"Tool {tool_name} is not allowed for this category"
            # Optional: run this step only when previous step result is long enough
            run_only_if_longer = step.get("run_only_if_previous_step_longer_than")
            try:
                threshold = int(run_only_if_longer) if run_only_if_longer is not None else None
            except (TypeError, ValueError):
                threshold = None
            if threshold is not None and i > 0:
                prev_id = str(i)  # previous step 1-based id
                prev_result = step_results.get(prev_id) or ""
                if len(prev_result) < threshold:
                    # Skip this step; return previous result or summarized
                    if when_skipped_summarize and completion_fn and prev_result.strip():
                        summary = await _dag_llm_summarize_for_reply(completion_fn, prev_result, config)
                        if summary:
                            return True, summary.strip()
                    return True, prev_result.strip() or last_result
            args = await _resolve_flow_step_args(
                step=step,
                step_index_1based=step_index_1based,
                step_results=step_results,
                user_message=user_message,
                completion_fn=completion_fn,
                config=config,
                flow=flow,
            )
            try:
                result = await registry.execute_async(tool_name, args, context)
                result = result if result is not None else ""
                if isinstance(result, str) and result.strip().startswith(TOOL_ERROR_PREFIX):
                    return False, result
                step_id = str(step_index_1based)
                step_results[step_id] = result
                last_result = result
            except Exception as e:
                err_msg = f"Error running tool {tool_name}: {e!s}"
                logger.debug("DAG step {} failed: {}", step_index_1based, e)
                return False, err_msg
        # Success: prefer last result that looks like a link or is short
        if last_result and isinstance(last_result, str) and ("/files/out?" in last_result or "http" in last_result):
            return True, last_result.strip()
        if last_result and isinstance(last_result, str) and len(last_result.strip()) < 2000:
            return True, last_result.strip()
        if last_result and isinstance(last_result, str):
            return True, last_result.strip()[:2000] + ("…" if len(last_result) > 2000 else "")
        return True, "Task completed. (任务已完成。)"
    except Exception as e:
        logger.debug("DAG unexpected error: {}; returning failure", e)
        return False, f"DAG error: {e!s}"


def build_final_summary_messages(
    goal: str,
    steps_done: List[Dict[str, Any]],
    step_results: Dict[str, str],
    user_message: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build messages for the final-summary LLM: goal, what ran, last result, optional user message. Never raises."""
    step_results = step_results if isinstance(step_results, dict) else {}
    summary_parts = [f"Goal: {goal or 'Complete the task'}"]
    for entry in steps_done or []:
        if not isinstance(entry, dict):
            continue
        step_id = entry.get("step_id") or "?"
        tool = entry.get("tool") or "?"
        result = (step_results.get(step_id) or "")[:400]
        if len(step_results.get(step_id) or "") > 400:
            result += "…"
        summary_parts.append(f"Step {step_id} ({tool}): result (truncated) — {result!r}")
    summary_parts.append("Write a short reply to the user.")
    if user_message and user_message.strip():
        summary_parts.append(f"User's request: {user_message.strip()[:500]}")
    user_content = "\n\n".join(summary_parts)
    return [
        {"role": "system", "content": FINAL_SUMMARY_SYSTEM},
        {"role": "user", "content": user_content},
    ]


async def call_final_summary(
    completion_fn: Any,
    goal: str,
    steps_done: List[Dict[str, Any]],
    step_results: Dict[str, str],
    user_message: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    One LLM call to produce a short user-facing reply from the execution log. No tools.
    Returns the reply string or None on failure.
    """
    if not completion_fn:
        return None
    messages = build_final_summary_messages(
        goal=goal,
        steps_done=steps_done,
        step_results=step_results,
        user_message=user_message,
    )
    try:
        planner_llm = (config or {}).get("planner_llm") or None
        if isinstance(planner_llm, str):
            planner_llm = planner_llm.strip() or None
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(
                messages=messages,
                llm_name=planner_llm,
            )
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if response and isinstance(response, str) and response.strip():
            return response.strip()
        return None
    except Exception as e:
        logger.debug("Final summary call failed: {}", e)
        return None


def build_planner_messages(
    query: str,
    categories: List[str],
    tool_names: List[str],
    skill_names: Optional[List[str]] = None,
    tools_description: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Build messages for the planner LLM: user request, intent, available tools/skills.
    tools_description: optional short text listing tools (and params if needed); if None, we list tool_names only.
    """
    categories_str = ", ".join((c or "").strip() for c in (categories or []) if (c or "").strip())
    tools_str = tools_description if (tools_description and tools_description.strip()) else (
        "Available tools: " + ", ".join(tool_names) if tool_names else "None"
    )
    skills_str = ""
    if skill_names:
        skills_str = " Available skills (for run_skill skill_name): " + ", ".join(skill_names) + "."
    user_content = (
        f"User request: {query}\n\n"
        f"Intent category: {categories_str}\n\n"
        f"{tools_str}.{skills_str}\n\n"
        "Output the plan as a single JSON object (goal, steps, requires_final_summary)."
    )
    return [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def build_replan_messages(
    goal: str,
    execution_log: List[Dict[str, Any]],
    failed_step_id: str,
    failed_tool: str,
    failed_args: Dict[str, Any],
    error: str,
    tool_names: List[str],
) -> List[Dict[str, Any]]:
    """
    Build messages for re-plan: goal, execution log (step id, tool, result snippet), failed step and error.
    execution_log: list of {step_id, tool, result} (result truncated for prompt).
    """
    log_lines = []
    for entry in execution_log or []:
        step_id = entry.get("step_id") or "?"
        tool = entry.get("tool") or "?"
        result = (entry.get("result") or "")[:500]
        if len((entry.get("result") or "")) > 500:
            result += "…"
        log_lines.append(f"  Step {step_id}: tool={tool}, result (truncated): {result!r}")
    log_text = "\n".join(log_lines) if log_lines else "  (none)"
    try:
        args_preview = (json.dumps(failed_args) if failed_args else "{}")[:300]
    except (TypeError, ValueError):
        args_preview = "{}"
    user_content = (
        f"Original goal: {goal}\n\n"
        f"Execution log (steps that ran):\n{log_text}\n\n"
        f"Failed step: id={failed_step_id}, tool={failed_tool}, arguments={args_preview}\n"
        f"Error: {error}\n\n"
        f"Available tools: {', '.join(tool_names) if tool_names else 'none'}\n\n"
        "Output a new plan as a single JSON object (goal, steps, requires_final_summary). You may retry with different args, skip steps, or simplify."
    )
    return [
        {"role": "system", "content": REPLAN_SYSTEM},
        {"role": "user", "content": user_content},
    ]


async def call_replan(
    completion_fn: Any,
    goal: str,
    execution_log: List[Dict[str, Any]],
    failed_step_id: str,
    failed_tool: str,
    failed_args: Dict[str, Any],
    error: str,
    tool_names: List[str],
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Call planner for re-plan: same parse/validate as run_planner. Returns new plan or None.
    """
    if not tool_names or not completion_fn:
        return None
    config = config or {}
    try:
        max_steps = max(1, min(50, int(config.get("max_steps_per_plan", 12) or 12)))
    except (TypeError, ValueError):
        max_steps = 12
    planner_llm = (config.get("planner_llm") or "").strip() or None
    messages = build_replan_messages(
        goal=goal,
        execution_log=execution_log,
        failed_step_id=failed_step_id,
        failed_tool=failed_tool,
        failed_args=failed_args or {},
        error=error,
        tool_names=tool_names,
    )
    try:
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(
                messages=messages,
                llm_name=planner_llm,
            )
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if not response or not isinstance(response, str):
            return None
        plan = parse_plan(response)
        if not plan:
            return None
        allowed = set(tool_names)
        ok, err = validate_plan(plan, allowed, max_steps=max_steps)
        if not ok:
            logger.debug("Re-plan validation failed: {}", err)
            return None
        return plan
    except Exception as e:
        logger.debug("Re-plan call failed: {}", e)
        return None


def _extract_json_from_response(response: str) -> Optional[str]:
    """Extract a JSON object from the model response (may be wrapped in markdown or text)."""
    if not response or not isinstance(response, str):
        return None
    text = response.strip()
    # Try to find {...} with balanced braces
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_plan(response: str) -> Optional[Dict[str, Any]]:
    """
    Parse planner LLM response into a plan dict. Returns None on parse failure.
    Expects JSON with keys: goal (str), steps (list), requires_final_summary (bool, optional).
    """
    raw = _extract_json_from_response(response)
    if not raw:
        return None
    try:
        plan = json.loads(raw)
        if not isinstance(plan, dict):
            return None
        if "steps" not in plan or not isinstance(plan["steps"], list):
            return None
        return plan
    except (json.JSONDecodeError, TypeError):
        return None


def validate_plan(
    plan: Dict[str, Any],
    allowed_tool_names: Set[str],
    max_steps: int = 20,
) -> Tuple[bool, Optional[str]]:
    """
    Validate plan: tool names in allowed set, step count <= max_steps, step ids unique.
    Returns (True, None) if valid, else (False, error_message).
    """
    if not plan or not isinstance(plan, dict):
        return False, "Plan is not a dict"
    steps = plan.get("steps")
    if not isinstance(steps, list):
        return False, "Plan has no steps list"
    if len(steps) > max_steps:
        return False, f"Plan has {len(steps)} steps; max allowed is {max_steps}"
    if len(steps) == 0:
        return False, "Plan has zero steps"
    seen_ids = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            return False, f"Step {i + 1} is not an object"
        tool = step.get("tool")
        if not tool or not isinstance(tool, str):
            return False, f"Step {i + 1} has no tool name"
        tool = tool.strip()
        if tool not in allowed_tool_names:
            return False, f"Step {i + 1} uses tool '{tool}' which is not in the allowed list"
        step_id = step.get("id")
        if step_id is not None:
            sid = str(step_id).strip()
            if sid in seen_ids:
                return False, f"Duplicate step id: {sid}"
            seen_ids.add(sid)
    return True, None


async def run_planner(
    completion_fn: Any,
    query: str,
    categories: List[str],
    tool_names: List[str],
    skill_names: Optional[List[str]] = None,
    tools_description: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Run the planner: build messages, call LLM, parse and validate plan.
    completion_fn: object with openai_chat_completion(messages=..., llm_name=...) (e.g. core).
    config: planner_executor config (planner_llm, max_steps_per_plan). Optional.
    Returns the plan dict if successful, None otherwise (caller should fall back to ReAct).
    """
    if not query or not categories or not tool_names:
        return None
    config = config or {}
    try:
        max_steps = max(1, min(50, int(config.get("max_steps_per_plan", 12) or 12)))
    except (TypeError, ValueError):
        max_steps = 12
    planner_llm = (config.get("planner_llm") or "").strip() or None
    messages = build_planner_messages(
        query=query,
        categories=categories,
        tool_names=tool_names,
        skill_names=skill_names,
        tools_description=tools_description,
    )
    try:
        if hasattr(completion_fn, "openai_chat_completion"):
            response = await completion_fn.openai_chat_completion(
                messages=messages,
                llm_name=planner_llm,
            )
        else:
            response = await completion_fn(messages, llm_name=planner_llm)
        if not response or not isinstance(response, str):
            logger.debug("Planner returned no response")
            return None
        plan = parse_plan(response)
        if not plan:
            logger.debug("Planner response could not be parsed as JSON plan")
            return None
        allowed = set(tool_names)
        ok, err = validate_plan(plan, allowed, max_steps=max_steps)
        if not ok:
            logger.debug("Planner plan invalid: {}", err)
            return None
        return plan
    except Exception as e:
        logger.debug("Planner call failed: {}", e)
        return None


def resolve_placeholders(obj: Any, step_results: Dict[str, str]) -> Any:
    """
    Recursively replace <from_step_N> placeholders in obj (dict/list/str) with step_results[N].
    step_results maps step id (e.g. "1", "2") to the raw text result of that step. Never raises.
    """
    if not step_results or not isinstance(step_results, dict):
        return obj
    if isinstance(obj, str):
        s = obj
        # Replace from highest step id first so we don't replace part of a longer placeholder; only use str keys
        keys = [k for k in step_results.keys() if k is not None and isinstance(k, str)]
        for step_id in sorted(keys, key=lambda x: (len(x), x), reverse=True):
            placeholder = f"<from_step_{step_id}>"
            if placeholder in s:
                val = step_results.get(step_id, "")
                s = s.replace(placeholder, str(val) if val is not None else "")
        return s
    if isinstance(obj, dict):
        return {k: resolve_placeholders(v, step_results) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_placeholders(v, step_results) for v in obj]
    return obj


def _execution_log_from_step_results(
    steps: List[Dict[str, Any]],
    step_results: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Build execution log for re-plan: list of {step_id, tool, result} in order. Never raises."""
    log = []
    step_results = step_results if isinstance(step_results, dict) else {}
    for i, step in enumerate(steps or []):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or str(i + 1)).strip()
        if step_id not in step_results:
            continue
        tool = (step.get("tool") or "").strip()
        log.append({"step_id": step_id, "tool": tool, "result": step_results[step_id]})
    return log


async def run_executor(
    plan: Dict[str, Any],
    registry: Any,
    context: Any,
    initial_step_results: Optional[Dict[str, str]] = None,
    re_plan_count: int = 0,
    completion_fn: Optional[Any] = None,
    config: Optional[Dict[str, Any]] = None,
    tool_names: Optional[List[str]] = None,
    user_message: Optional[str] = None,
) -> Tuple[bool, Dict[str, str], str]:
    """
    Execute the plan: for each step, resolve placeholders (using initial_step_results + step_results), run the tool, collect results.
    On non-optional step failure: if re_plan_on_error and re_plan_count < max_replans, call re-plan and resume with new plan; else return (False, ..., error).
    When requires_final_summary is true and completion_fn is set: one LLM call to produce a short user-facing reply (Phase 5).
    initial_step_results: from a previous run (e.g. after re-plan); placeholders can reference these.
    Never raises: returns (False, {}, error_msg) on invalid inputs or tool errors.
    """
    if not plan or not isinstance(plan, dict):
        return False, {}, "Invalid plan"
    if not registry or not getattr(registry, "execute_async", None):
        return False, {}, "No tool registry"
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    if not steps:
        return False, {}, "Plan has no steps"
    config = config if isinstance(config, dict) else {}
    try:
        max_replans = max(0, int(config.get("max_replans", 2) or 2))
    except (TypeError, ValueError):
        max_replans = 2
    re_plan_on_error = bool(config.get("re_plan_on_error", True))
    initial_step_results = initial_step_results if isinstance(initial_step_results, dict) else {}
    step_results: Dict[str, str] = dict(initial_step_results)
    last_result = ""
    try:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return False, step_results, f"Step {i + 1} is not an object"
            step_id = str(step.get("id") or str(i + 1)).strip()
            tool_name = (step.get("tool") or "").strip()
            if not tool_name:
                return False, step_results, f"Step {step_id} has no tool"
            raw_args = step.get("arguments")
            if not isinstance(raw_args, dict):
                raw_args = {}
            # Resolve placeholders using both initial (from previous run) and current step_results
            args = resolve_placeholders(raw_args, step_results)
            optional = bool(step.get("optional"))
            try:
                result = await registry.execute_async(tool_name, args, context)
                result = result if result is not None else ""
                if isinstance(result, str) and result.strip().startswith(TOOL_ERROR_PREFIX):
                    if optional:
                        logger.debug("Planner executor: optional step {} failed: {}", step_id, result[:200])
                        step_results[step_id] = result
                        continue
                    # Re-plan (Phase 4)
                    if re_plan_count < max_replans and re_plan_on_error and completion_fn and tool_names:
                        goal = (plan.get("goal") or "Complete the task").strip()
                        exec_log = _execution_log_from_step_results(steps[: i + 1], {**step_results, step_id: result})
                        new_plan = await call_replan(
                            completion_fn=completion_fn,
                            goal=goal,
                            execution_log=exec_log,
                            failed_step_id=step_id,
                            failed_tool=tool_name,
                            failed_args=args,
                            error=result[:800],
                            tool_names=tool_names,
                            config=config,
                        )
                        if new_plan and new_plan.get("steps"):
                            logger.debug("Planner executor: re-plan (count={}); resuming with new plan", re_plan_count + 1)
                            return await run_executor(
                                new_plan,
                                registry,
                                context,
                                initial_step_results=step_results,
                                re_plan_count=re_plan_count + 1,
                                completion_fn=completion_fn,
                                config=config,
                                tool_names=tool_names,
                                user_message=user_message,
                            )
                    return False, step_results, result
                step_results[step_id] = result
                last_result = result
            except Exception as e:
                err_msg = f"Error running tool {tool_name}: {e!s}"
                logger.debug("Planner executor step {} failed: {}", step_id, e)
                if optional:
                    step_results[step_id] = err_msg
                    continue
                # Re-plan on exception
                if re_plan_count < max_replans and re_plan_on_error and completion_fn and tool_names:
                    goal = (plan.get("goal") or "Complete the task").strip()
                    step_results[step_id] = err_msg
                    exec_log = _execution_log_from_step_results(steps[: i + 1], step_results)
                    new_plan = await call_replan(
                        completion_fn=completion_fn,
                        goal=goal,
                        execution_log=exec_log,
                        failed_step_id=step_id,
                        failed_tool=tool_name,
                        failed_args=args,
                        error=err_msg[:800],
                        tool_names=tool_names,
                        config=config,
                    )
                    if new_plan and new_plan.get("steps"):
                        logger.debug("Planner executor: re-plan after exception (count={})", re_plan_count + 1)
                        return await run_executor(
                            new_plan,
                            registry,
                            context,
                            initial_step_results=step_results,
                            re_plan_count=re_plan_count + 1,
                            completion_fn=completion_fn,
                            config=config,
                            tool_names=tool_names,
                            user_message=user_message,
                        )
                return False, step_results, err_msg
        # Success: optionally run final-summary LLM (Phase 5)
        requires_summary = plan.get("requires_final_summary") and config.get("requires_final_summary", True)
        if requires_summary and completion_fn:
            steps_done = _execution_log_from_step_results(steps, step_results)
            summary = await call_final_summary(
                completion_fn=completion_fn,
                goal=(plan.get("goal") or "Complete the task").strip(),
                steps_done=steps_done,
                step_results=step_results,
                user_message=user_message,
                config=config,
            )
            if summary:
                return True, step_results, summary
        # Fallback: prefer last result that looks like a link or is short
        if last_result and isinstance(last_result, str) and ("/files/out?" in last_result or "http" in last_result):
            return True, step_results, last_result.strip()
        if last_result and isinstance(last_result, str) and len(last_result.strip()) < 2000:
            return True, step_results, last_result.strip()
        if last_result and isinstance(last_result, str):
            return True, step_results, last_result.strip()[:2000] + ("…" if len(last_result) > 2000 else "")
        return True, step_results, "Task completed. (任务已完成。)"
    except Exception as e:
        logger.debug("Planner executor unexpected error: {}; returning failure", e)
        return False, step_results, f"Planner executor error: {e!s}"
