# Tools: parameters that must be inferred by the LLM

This document reviews built-in tools for the same class of issue as **folder_list**: the LLM may call a tool with **empty or missing parameters** even though the value should be **extracted from the user's message**. Relying on static (keyword) inference in the Core is brittle; the LLM should be the one inferring and passing these parameters.

---

## Summary

| Tool | Issue | Schema change | Description change |
|------|--------|----------------|-------------------|
| **folder_list** | path was optional; LLM often sent `{}` | ✅ Done: `required: ["path"]` | ✅ "Extract folder name from user message; use '.' for root" |
| **file_find** | path optional; "search in images" could get root | Add `required: ["path"]` (use '.' if no folder) | "Extract path from user message when they name a folder" |
| **web_extract** | `required: []`; executor needs urls/url | Kept `required: []` (one of urls/url; schema can't express "one of") | "You MUST pass urls or url; extract from user message" |
| **web_crawl** | `required: []`; executor: "url is required" | Add `required: ["url"]` | "Extract start URL from user message" |
| **tavily_extract** | `required: []`; executor: "urls is required" | Add `required: ["urls"]` | "Extract URL(s) from user message" |
| **tavily_research** | `required: []`; executor: "input is required" | Add `required: ["input"]` | "Extract research topic from user message" |
| **apply_patch** | `required: []`; executor: "patch is required" | Add `required: ["patch"]` | "Pass the unified diff content" |
| **channel_send** | `required: []`; executor: "text or message is required" | Add `required: ["text"]` (or message) | "Message to send; extract or compose from context" |
| **image** (vision) | `required: []`; executor: "path or image or url is required" | Add `required: ["path"]` (or document url) | "Path from folder_list/file_find, or url for image URL" |
| **remind_me** | Only `message` required; minutes/at_time often omitted | Keep; executor already errors | Description already says "Supply minutes OR at_time" |

---

## Tools already in good shape

- **file_read, document_read, file_write, file_edit, get_file_view_link**: `path` (and content where needed) are required; descriptions tell the LLM to use path from folder_list/file_find or extract filename.
- **web_search, knowledge_base_search, run_skill, route_to_plugin, exec, fetch_url, http_request, webhook_trigger**: Critical params (query, url, skill_name, plugin_id, command, etc.) are required.
- **remind_me, record_date, cron_schedule**: Required fields are set; reminders already have strong descriptions for extracting time from the user message.
- **save_result_page, markdown_to_pdf, knowledge_base_add**: title/content, content/path, content are required.

---

## Tools with optional critical params (fixed or to fix)

1. **file_find**  
   - **Risk:** User says "find PDFs in documents" → LLM calls `file_find(pattern="*.pdf")` with no path → search runs at root.  
   - **Fix:** Require `path`; description: "Extract from user message: the folder they said (e.g. documents, images) or '.' for sandbox root. Never omit."

2. **web_extract**  
   - **Risk:** User says "summarize https://example.com/article" → LLM calls `web_extract()` with no urls.  
   - **Fix:** Require `urls` (or accept single URL in urls); description: "Extract URL(s) from the user's message. Never call without urls or url."

3. **web_crawl**  
   - **Risk:** User says "crawl docs.example.com" → LLM calls `web_crawl()` with no url.  
   - **Fix:** `required: ["url"]`; description: "Extract the start URL from the user's message."

4. **tavily_extract**  
   - **Risk:** Same as web_extract.  
   - **Fix:** `required: ["urls"]` (or document that a single URL can be passed as urls); description: "Extract URL(s) from the user's message."

5. **tavily_research**  
   - **Risk:** User says "research the best LLMs in 2025" → LLM calls `tavily_research()` with no input.  
   - **Fix:** `required: ["input"]`; description: "Extract the research question or topic from the user's message. Use input, query, or question."

6. **apply_patch**  
   - **Risk:** LLM generates a patch but calls `apply_patch()` with no patch/content.  
   - **Fix:** `required: ["patch"]`; description: "Unified diff content (or use content as alias). Do not call without patch content."

7. **channel_send**  
   - **Risk:** LLM decides to send a follow-up but calls `channel_send()` with no text.  
   - **Fix:** `required: ["text"]` (or "message"); description: "Message text to send. Extract or compose from context; do not call with empty text."

8. **image** (vision)  
   - **Risk:** User says "describe this image" with an attachment → LLM calls `image()` with no path/url.  
   - **Fix:** Require one of path/url (path when file is in sandbox); description: "Path to image (from folder_list/file_find) or url. Extract from user message or attachment context."

---

## Principle

- **Required in schema:** Any parameter without which the tool would fail or do the wrong thing should be in `required`, so the LLM is forced to output a value.
- **Describe extraction:** Parameter descriptions should say to "extract from the user's message" (or from context, e.g. path from a previous folder_list result) so the model infers the value instead of omitting it.
- **No static inference in Core:** Avoid filling in parameters in the Core with keyword logic; the LLM should pass them. Static fallbacks can be wrong (e.g. "I don't want images" matching "images") or incomplete (e.g. custom folder names).

---

## Reference

- Tool definitions: `tools/builtin.py` (ToolDefinition, parameters, required).
- folder_list fix: path required; description and force-include instructions tell the LLM to extract folder name from the user message.
- Selection examples: `config/prompts/tools/selection_examples.yml` (few-shot for tool choice and parameter extraction).
