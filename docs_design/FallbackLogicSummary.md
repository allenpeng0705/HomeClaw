# Fallback logic summary (LLM/tools response flow)

**Policy: use fallbacks as few as possible.** If the model returns no tool_calls, it may really mean no tools; we only auto-invoke when the user intent clearly matches a specific fallback (e.g. "list images" → file_find only, not web search).

When the model returns **no tool_calls** or **empty content**, Core applies several fallbacks in order. This doc summarizes the order and how we **select** which one runs so we avoid wrong or weird responses (e.g. web search when the user wanted local file list).

## When does the "no tool_calls" branch run?

- After an LLM call that returned a message with **no** `tool_calls` (and possibly empty `content`).
- So we're either in the first turn (user said something, model replied with text only) or in a **follow-up turn** after we ran tools and called the LLM again (model then replied with empty or text only).

## How we select which fallback runs (avoid wrong tool)

- **Local file/folder intent:** If the query clearly asks for **local** files or folders (e.g. "list images", "list files", "documents folder", "文件列表", "图片"), we:
  - **force_include:** Only run `folder_list` or `file_find` from the auto_invoke list; **skip** `run_skill` and any other tool so we never run web search for those queries.
  - **route_to_plugin fallback:** We do **not** call `_infer_route_to_plugin_fallback` when local-file intent is detected, so we never route to web_search for "list images" or "search my files".
- **No special case for images:** Images are files. "List images" is handled like "list documents": we add `folder_list(path="images")` when the query mentions images (or 图片), same as we add `folder_list(path="documents")` for documents. One unified list-folder intent.
- **General:** We run at most one fallback from the list; the first that matches and runs wins. Intent filtering (local-file-only when applicable) ensures we don't run the wrong tool (e.g. web search).

## Fallback order (inside the "no tool_calls" branch)

Rough order of evaluation; the first that sets `response` and doesn’t fall through wins.

1. **Raw tool_call in content**  
   If content contains `<tool_call>` / `</tool_call>` but we didn’t parse it →  
   `response = "The assistant tried to use a tool but the response format was not recognized. Please try again."`

2. **Default**  
   `response = content_str` (model’s reply) if non-empty, else `None`.

3. **Last tool was file_find or folder_list and content is empty**  
   If `response` is still empty and `last_tool_name in ("file_find", "folder_list")` and we have `last_tool_result_raw` → format that JSON as a user-friendly list and set `response` to that.  
   *(So “list images” → file_find ran, second LLM returned empty → we still show the file list.)*

4. **Unhelpful check**  
   `unhelpful_for_auto_invoke` = content empty/short or contains phrases like "no tool", "i cannot", "please try again", etc.

5. **force_include_auto_invoke**  
   - Built from query rules (e.g. “list folder”, “create image”) and optionally `always_run`.  
   - **run_force_include** = we have force_include items **and** (unhelpful **or** any item has `always_run`).  
   - If **run_force_include**: run the first matching tool (e.g. `folder_list`, `run_skill`), then set `response` from the tool result (or keep model reply in some cases).  
   - If we don’t run force_include or it didn’t run any tool → fall through to the big `else` below.

6. **Else (no force_include run)**  
   - **remind_me fallback**: if query looks like a reminder and we didn’t already run remind_me → run remind_me, set `response` from result or clarification message.  
   - **remind_me clarification**: if query looks like reminder but needs time → `response =` clarification question.  
   - **cron_schedule fallback**: if query looks like recurring schedule → run cron_schedule, set `response` from result.  
   - **route_to_plugin / run_skill fallback**: if `response` still None or same as `content_str` and reply looks unhelpful → infer plugin/skill from query, run `route_to_plugin` or `run_skill`, set `response` from result or "Done." / error message.  
   - **document summarization fallback**: if query looks like “summarize a doc” → file_find + document_read + LLM summary.  
   - **folder_list fallback**: if query matches list-folder phrases (e.g. “list files”, “documents folder”) → run folder_list, set `response` to formatted list or “Directory is empty…”.  
   - Otherwise: `response = content_str`.

After the loop we **break** with whatever `response` is set.

## After the tool loop: final empty response

If **response is None or empty** after the loop:

1. **err_hint**  
   If we have an LLM error hint → return `"Sorry, something went wrong. {hint} Please try again. (...)"`.

2. **last_tool_name set, no err_hint**  
   Previously we always returned:  
   `"Done. What would you like to do next? (已完成。还需要什么？)"`  
   That was wrong when we had usable tool output (e.g. run_skill or file_find returned text) but didn’t assign it to `response`.  
   **Fix (see code):** If we have `last_tool_result_raw` that is usable (non-empty, not error-like), use it as the response instead of "Done...". Only show "Done..." when we really have nothing to show.

3. **No last_tool_name, no err_hint**  
   Return generic: `"Sorry, something went wrong and please try again. (...)"`.

## What makes fallbacks “unstable” or wrong?

- **Too many conditions:** unhelpful, force_include, remind_me, cron, route_to_plugin, document, folder_list, and final "Done." all overwrite `response` in different orders, so one path can overwrite a good reply.
- **“Done…” too broad:** Returning "Done. What would you like to do next?" whenever `last_tool_name` is set and response is empty can hide real tool output (e.g. skill result) that we should have shown.
- **force_include vs. good content:** If the model returned a good short reply but we mark it “unhelpful” (e.g. &lt; 100 chars), we may run force_include and replace it with something else (e.g. folder_list when the user didn’t ask for a list).

## Stability improvements (implemented or recommended)

1. **Use last_tool_result_raw when response is empty**  
   In the final empty-response block: if `last_tool_name` is set and `last_tool_result_raw` is a non-empty string and not error-like, set `response = last_tool_result_raw` (or a truncated/sanitized version) instead of returning "Done...". Only return "Done..." when there is no usable tool output.

2. **Narrow “unhelpful”**  
   Avoid treating short but valid replies (e.g. “OK”, “Done”) as unhelpful so we don’t trigger force_include or route_to_plugin fallback unnecessarily.

3. **Prefer one clear path per intent**  
   e.g. “list folder” → force_include folder_list or folder_list fallback, not both with different conditions; same for remind_me vs cron_schedule.

4. **Log which fallback set response**  
   So in logs we can see e.g. “response from: last_tool_result_raw (file_find)” vs “response from: force_include folder_list” vs “response from: Done. What would you like…”.

See `core/llm_loop.py` (branch `if not tool_calls:` and block `if response is None or ...`) for the exact code.
