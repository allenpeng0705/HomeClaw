# Systematic Fix for Wrong Tool/Skill Selection by LLM

## Problem

The LLM frequently selects the wrong tool or skill even when the user's intent is obvious in natural language, for example:

- "帮我上网搜一下现在有什么好看的电影" → model called **exec** or **tavily_crawl** instead of **web_search**
- "Just search and give me results" → model said "I will use web_search" but returned **no tool_calls**
- "List my files" / "目录下有哪些文件" → model sometimes replies with text only instead of **folder_list**
- "Remind me in 5 minutes" → model sometimes doesn't call **remind_me**

Causes:

1. **Too many tools** (70+) in one prompt → the model confuses similar tools (exec vs web_search, tavily_crawl vs web_search).
2. **No single source of truth** for "when user says X, use tool Y" — rules are split across prompt text, `skills_force_include_rules`, and hardcoded fallbacks in `llm_loop.py`.
3. **Prompt-only guidance** — we tell the model "use web_search for search" but when it doesn't, we only added fallbacks ad hoc (folder_list, web_search) in code.
4. **Regex/pattern gaps** — e.g. "上网搜" wasn't in the original search rule; Chinese and follow-up phrases ("just search", "give me results") were missing.

## Systematic Approach

### 1. Intent-first layer (recommended)

**Before** relying on the LLM to pick a tool, run a fast **intent → tool** step:

- **Input:** user query (and optionally conversation context).
- **Output:** optional **intent** (e.g. `search_web`, `list_files`, `schedule_remind`, `read_document`, `run_skill_html_slides`) and suggested **tool + default args**.
- **Implementation options:**
  - **A. Rule-based (phrases + regex)**  
    One config file (e.g. `config/intent_tools.yml`) with entries: intent id, phrases/keywords, regex (optional), tool name, default arguments (e.g. `query: "{{query}}"`). Match query against rules; first match wins. No LLM.
  - **B. Small classifier**  
    Tiny model or embedding similarity: embed query, compare to intent descriptions, return top intent. Heavier but more flexible.
  - **C. Hybrid**  
    Rules for "obvious" intents (search, list files, remind); LLM or classifier for the rest.

Then:

- **High confidence:** When the intent rule matches strongly (e.g. phrase list + regex), **inject** "You MUST use tool X with ..." and register a **fallback**: if the model returns no tool_calls, **run the tool ourselves** and use the result as the response (same as current folder_list / web_search fallbacks).
- **Medium confidence:** Only inject the instruction; no forced execution.
- **Low / no match:** Leave tool choice entirely to the LLM.

This way, **obvious intents never depend on the LLM**; the model only decides for ambiguous or multi-step cases.

### 2. One config for "obvious" intents

Maintain a single list of intents where we are willing to **force-invoke** the tool when the model doesn't call it:

- **search_web** — phrases: 上网搜, 搜一下, 搜索, search the web, just search, give me results, … → **web_search**(query="{{query}}")
- **list_files** — phrases: 目录, 哪些文件, list files, list directory, … → **folder_list**(path="." or from phrase)
- **schedule_remind** — phrases: 提醒我, remind me, N分钟后, … → **remind_me** / **cron_schedule** (existing scheduling rule)
- **open_url** — phrases: open https://, 打开 http, … → **route_to_plugin**(homeclaw-browser, browser_navigate)
- (Optional later) **read_document**, **generate_slides**, etc.

Each entry: **phrases** (list), **tool**, **arguments** (with `{{query}}` or fixed values), **fallback_when_no_tool_call** (bool). When `fallback_when_no_tool_call` is true and the model returns no tool_calls, we run the tool and set the response (same as current strict_fallback behavior for folder_list and web_search).

### 3. Reduce tool set per request (optional)

- **Intent-based filtering:** If intent is `search_web`, only pass **web_search** (and maybe tavily_extract, fetch_url) to the LLM, not all 72 tools. Reduces confusion.
- **Tiered tools:** "Core" tools (web_search, folder_list, document_read, run_skill, save_result_page, remind_me, cron_schedule, …) always in prompt; "Extended" tools only when intent or context suggests them.

### 4. Stronger prompting (already in progress)

- **Few-shot examples** in `config/prompts/tools/selection_examples.yml` — add more examples for search, list files, schedule, and **web_search only (no exec, no tavily_crawl)**.
- **Routing block** in system prompt — one line per intent: "When user says X, use tool Y only; do not use Z."
- **Force-include instruction** when intent matches — "You MUST call tool X in this turn; do not reply with only text."

### 5. Reject wrong tool when intent is clear

When we **know** the intent (e.g. search_web) and the model returns a **different** tool (e.g. exec or tavily_crawl), **do not run** that tool. Either:

- Clear the parsed tool_calls and run the intent's fallback (current approach for exec + search intent), or
- Run the **correct** tool (web_search) and ignore the wrong one.

So: one place defines "for search_web, only web_search is valid"; code enforces it.

## Implementation status

- **Done:** Routing rule "use web_search, not exec or tavily_crawl"; force-include for search phrases; **web_search fallback** when model returns no tool_calls and query matches search intent; **ignore parsed exec** for search-intent queries; **folder_list fallback** when model returns no tool_calls and query matches list-files intent.
- **Done:** Expanded search phrases (just search, give me results, 直接给结果, 搜一下结果).
- **Proposed:** Single config file `config/intent_tools.yml` (or a section in `skills_and_plugins.yml`) that defines all "obvious" intents with phrases, tool, args, and fallback_when_no_tool_call, and a single loop in `llm_loop` that (1) matches query to intents, (2) adds instructions and fallbacks, (3) when model returns no tool_calls, runs the matched intent's tool. This replaces the scattered ad-hoc phrases and fallbacks with one table.
- **Optional:** Intent-based tool filtering so the LLM only sees a subset of tools for that intent.

## Summary

To fix wrong tool/skill selection systematically:

1. **Define an intent → tool layer** (config-driven) for obvious intents.
2. **When intent matches, force the right tool** (instruction + fallback if model doesn't call it).
3. **Reject wrong tools** when intent is clear (e.g. don't run exec for search).
4. **Optionally reduce tools** sent to the LLM per intent.
5. **Keep few-shot examples and routing text** aligned with the same intents.

That way, obvious natural language ("上网搜", "list my files", "remind me in 5 min") always maps to the correct tool without relying on the LLM to choose among 70+ tools.
