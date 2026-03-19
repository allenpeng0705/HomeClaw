---
name: deep-research-workflow
description: >
  Structured web research workflow—plan, search with bounded tool budget, fetch sources when needed,
  synthesize a report with inline citations [1][2] and a ### Sources section. Uses HomeClaw builtins
  (tavily_research, web_search, fetch_url, tavily_extract) instead of LangGraph/deepagents.
keywords:
  - deep research
  - research report
  - literature review
  - web research
  - cited sources
  - 深度调研
  - 调研报告
  - 文献综述
trigger:
  patterns:
    - "deep\\s+research|in-?depth\\s+research|research\\s+report|comprehensive\\s+research|literature\\s+review"
    - "深度调研|调研报告|详细调研|全面调研|文献综述"
  instruction: >
    The user wants thorough web research with sources, not a one-line answer.
    Follow this skill's workflow using tools only (no separate LangGraph app): prefer tavily_research when
    Tavily is configured; otherwise web_search then fetch_url for key URLs. Enforce search budgets and
    finish with a structured report and ### Sources. Optional run_skill(skill_name='deep-research-workflow',
    script='workflow_reminder.py', args=['<short topic>']) returns a JSON reminder only—then you must still
    call tavily_research / web_search / fetch_url and write the full answer yourself.
metadata:
  openclaw:
    emoji: "🔬"
    requires:
      env: []
      bins: [python3]
---

# Deep research workflow (HomeClaw)

This skill encodes a **process** inspired by LangChain’s `deepagents` deep-research example, implemented with **existing HomeClaw tools**—no `deepagents`, no LangGraph server.

## When to use

- User asks for **deep / comprehensive / cited** research, a **mini literature review**, or a **report with sources**.
- User wants **comparison of multiple topics** or **multi-angle** analysis (plan sub-questions, then search each).

## Prerequisites

| Tool | Needs |
|------|--------|
| **`tavily_research`** | `TAVILY_API_KEY` or `tools.web.search.tavily.api_key` in config — **preferred** for one async research job + synthesized content + sources. |
| **`web_search`** | Provider config (often Tavily-backed) for URL/snippets. |
| **`fetch_url`** | For full page text when snippets are insufficient. |
| **`tavily_extract`** | Optional; structured extract when configured. |

If **`tavily_research`** is available, try it **first** for open-ended questions; it returns `content` + `sources` JSON. If it errors (no key, timeout), fall back to **`web_search` + `fetch_url`**.

## Workflow (do this in order)

1. **Clarify** (if needed): narrow scope, time range, or geography in one short reply or assumption statement.
2. **Plan**: mentally or briefly list 2–5 sub-questions; for comparisons, one sub-question per item.
3. **Search (budget)**  
   - **Simple fact / single topic:** 2–4 search-related tool calls total.  
   - **Complex / multi-part:** up to **8** search-related calls; stop earlier if results repeat.  
   - After **two** similar result sets, **stop searching** and synthesize.
4. **Fetch**: For top 2–4 URLs, use **`fetch_url`** when snippets lack detail (respect size/time limits).
5. **Synthesize**: Write the final answer in **prose** (not meta “I searched…”). Use **`##` / `###` headings** for structure.
6. **Citations**: Inline **`[1]`, `[2]`** where claims are sourced. End with:

```markdown
### Sources
[1] Title or site: https://...
[2] Title or site: https://...
```

Number sources **once** globally; no gaps in numbering.

## What not to do

- Do **not** claim you used a tool without calling it.
- Do **not** spin forever: respect the budgets above.
- Do **not** depend on **`run_skill`** alone for research — `workflow_reminder.py` only returns a JSON hint; **you** must run **`tavily_research` / `web_search` / `fetch_url`**.

## Tool cheat sheet

```text
# Best-effort single shot (Tavily Research API — async, may take up to max_wait_seconds)
tavily_research(input="<research question>", max_wait_seconds=120)

# Classic search → then open promising URLs
web_search(query="<query>")
fetch_url(url="https://...")

# Optional extract pipeline (if configured)
tavily_extract(...)   # per project docs / tool definitions
```

## Long outputs

If the report is very long and the user wants a file or PDF, use **`save_result_page`** or **`markdown_to_pdf`** per your usual HomeClaw patterns after the main answer.

## Optional: confirm skill loaded

```text
run_skill(skill_name="deep-research-workflow", script="workflow_reminder.py", args=["<topic>"])
```

Then proceed with real research tools as above.
