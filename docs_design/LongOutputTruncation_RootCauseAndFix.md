# Long Output Truncation: Root Cause and Fix

## Problem

When the user asks for a long document (HTML slides, Markdown report, summarized text), the result can be **truncated**:

- **Empty or broken HTML file**: The model called `save_result_page` with a huge `content` argument; the **tool-call arguments** were cut off by the API, so we saved incomplete HTML (e.g. missing `</html>`, no body).
- **Long Markdown or plain text cut off**: The model replied with a long message in the **content** field; the reply hit the **max_tokens** limit and stopped mid-sentence.

So both “long content in a tool call” and “long content in the message” can be truncated.

---

## Root Cause

### 1. Single-response token cap

Every LLM completion has a **per-response** limit: `max_tokens`. The **entire** response counts against this:

- Message **content** (text/markdown the model generates).
- All **tool_calls** (name + arguments). The arguments are serialized as JSON (e.g. `{"title":"...","content":"<!DOCTYPE html>...","format":"html"}`). That JSON is part of the same token stream.

So if the model generates:

1. Some text (e.g. “现在生成完整的HTML代码：”),
2. One tool call `save_result_page` with `content` = 30,000 tokens of HTML,

then the **total** tokens (text + tool call JSON) are capped by `max_tokens`. With `max_tokens = 8192` (e.g. DeepSeek), the tool call is cut off partway through the `content` string → truncated HTML → empty or broken file.

### 2. Where the cap comes from

- **Config**: A single value **`completion.max_tokens`** controls the per-response limit for **every** turn (no separate "long" override). Set it high (e.g. 32768) in `config/llm.yml` to reduce truncation of slides/reports.
- **If you don't set `max_tokens`**: Core uses **`completion.max_tokens`** first; if that is not set, it falls back to **`llama_cpp.predict`** (the server default from `--predict`); if neither is set, it uses **8192**. So omitting `max_tokens` means the effective limit is whatever `predict` is (for local) or 8192 (when no completion or predict is set). To avoid truncation, set `completion.max_tokens` explicitly (e.g. 32768).
- **Provider (cloud)**: Some cloud APIs have a hard max (e.g. 8192). Core does not override the request above that; the provider may reject or cap. For local, the limit is your config and what the local server allows.

So the root cause is: **long content (HTML, Markdown, or text) is being produced in a single response whose total length is bounded by `max_tokens`.** When that content is placed inside a **tool call’s arguments**, it shares the same budget and gets truncated. When it is placed in **message content**, it can still be truncated if it exceeds `max_tokens`.

---

## Why it affects both “file” and “text”

- **File (save_result_page / file_write)**  
  The model puts the document in the **tool argument** (`content`). The whole response (content + tool_calls) is one token stream → truncation in the middle of the JSON → broken/empty file.

- **Plain text or Markdown in chat**  
  The model puts the document in **message content**. The same `max_tokens` limit applies. If the document is longer than that (e.g. 15K tokens on an 8K cap), the reply is cut off.

So the **same** root cause (single-response token limit) applies to both “generate a file” and “generate long text/markdown”.

---

## Fix options (design)

### A. Don’t put long content in tool arguments

- **Guidance**: Tell the model to put **long** HTML/Markdown in the **message content** (e.g. in a ` ```html ... ``` ` or ` ```markdown ... ``` ` block), not inside `save_result_page(..., content=...)`.
- **System behavior**: When we see long document-like content in the assistant message (e.g. ```html or ```markdown, or long text that looks like a report), we **save it to a file** and return the link. We already do this for HTML (extract and `save_result_page`). We can **generalize** to Markdown and long plain text.
- **Effect**: Long content is no longer limited by the size of a single tool-call argument; it lives in the message body. We still have the **message** token limit, but we can set `max_tokens` high (e.g. 32768) and save whatever we get and return a link, so the user always gets a file when we detect “document”.

### B. Detect truncation and react

- **finish_reason**: Most APIs set `finish_reason = "length"` when the model stopped because it hit `max_tokens`. We can read this from the completion response (for both local and cloud, if the proxy returns it).
- **Actions**:  
  - **Log**: When `finish_reason == "length"`, log a clear WARNING so we know the response was truncated.  
  - **Tool calls**: If we have `finish_reason == "length"` and the last tool call’s arguments look truncated (e.g. save_result_page content without `</html>`), we already reject saving and ask the model to put content in the message; we can also **avoid executing** the truncated tool call or retry with “put the full content in your message in a code block”.  
  - **Content**: If the reply is content-only and `finish_reason == "length"`, we could save the truncated content to a file and tell the user “Response was cut off; partial content saved at …”.

### C. Chunked generation (advanced)

- Model calls `file_write` or a custom “append” tool multiple times with chunks. Requires a clear convention and model compliance; more complex. Defer unless needed.

### D. Increase max_tokens where possible

- A single **`completion.max_tokens`** is used for every turn. Set it to 32768 (or higher) in config to reduce truncation. Cloud providers with a hard 8K cap will still limit the response; local can use the full value if the server supports it.

---

## Local vs cloud: why there is a limit, and how to raise it for local

**Why there is always a limit**

The completion API (and the local server) need a **stopping condition**: “stop after this many tokens.” Without `max_tokens`, the model could generate indefinitely. So there is always *some* per-response cap.

**Local: we do not impose the 8192 cap**

- Core does **not** cap `max_tokens` for **local** requests. For **cloud** (`mtype == "litellm"`), many providers (e.g. DeepSeek) enforce their own limit (e.g. 8192); Core sends whatever you set in config and the provider may reject or cap.
- For **local** (llama.cpp, Ollama, etc.), the limit is:
  1. What you set in **config** (`completion.max_tokens` in `config/llm.yml`), or if omitted, **`llama_cpp.predict`**, or if both omitted, **8192**; and  
  2. What your **local server** allows (e.g. llama.cpp may have its own `--predict` or server-side max).

**How to reduce truncation when running locally**

1. **Set `max_tokens` in config**  
   In `config/llm.yml` under `completion`, set `max_tokens` to a high value (e.g. `32768` or `65536`) when you need long slides/reports. This applies to **every** turn. If you omit it, Core uses `llama_cpp.predict` (server default) or 8192, which may truncate long outputs.

2. **Make sure the local server accepts it**  
   For llama.cpp server, the server typically uses the `max_tokens` from each request. If the server or your `llama_cpp.predict` (or equivalent) caps the response length, that becomes the effective limit. Check your server docs and config (e.g. `predict` in `llm.yml` under `llama_cpp`) so the server can generate up to your configured `max_tokens`.

3. **Optional: prefer long content in the message**  
   Even with a high local limit, very long HTML (e.g. 50K tokens) may still hit it. The other approach—having the model put long HTML/Markdown in a ```html or ```markdown block in the message and letting Core save it—avoids putting that entire blob in a single tool call and works the same for local and cloud.

**Summary**

| Where the model runs | max_tokens source (all turns) | Who sets the limit |
|----------------------|-------------------------------|---------------------|
| **Local** (llama.cpp, etc.) | `completion.max_tokens`; if unset → `llama_cpp.predict`; if still unset → 8192 | You (config) + local server |
| **Cloud** (e.g. DeepSeek) | Same; provider may enforce its own cap (e.g. 8192) | You (config) + provider |

So when the tool runs locally, set **`completion.max_tokens`** (e.g. 32768) in config and ensure your local server supports that value. If you don’t set it, you get `predict` or 8192.

**When mix mode selects cloud but the next turn needs long output**

If the **cloud** model is chosen for the task (e.g. first turn does document_read, run_skill), the turn that **generates** the long content (HTML, report) would normally still use cloud and hit the 8192 cap. To avoid that, Core **prefers local for that specific turn** when both are configured:

- When the last message is a **tool** result and the last tool was **document_read** or **run_skill**, the next turn is likely to generate long output (slides, report).
- If we're currently on **cloud** and **main_llm_local** is set, we **switch to local for this turn only**. That turn then uses **`completion.max_tokens`** from config (no cloud cap), so long HTML/slides are much less likely to truncate.
- The rest of the chain can still use cloud (e.g. first turn); only the “generate long content” turn uses local.

So even when the “complex task” is handled by cloud, the **long-generation** turn uses local when available, and the cloud cap no longer applies for that turn.

---

## Chosen approach (summary)

1. **Document the root cause** (this file) so we don’t treat truncation as a one-off “HTML bug”.
2. **Keep “long content in message, not in tool args”** in prompts and tool descriptions (already added for HTML; can extend to Markdown).
3. **Generalize “save long content”**: When the assistant message contains long document-like content (HTML in ```html, or Markdown in ```markdown, or long markdown-like text), **save it to a file** and return the link. This covers:
   - Long HTML (already done),
   - Long Markdown (new),
   - Long plain text that looks like a report (new, optional).
4. **Detect truncation**: Read `finish_reason` from the completion response; when it is `"length"`, log a WARNING and optionally skip executing obviously truncated tool calls or save partial content with a note.
5. **Keep save_result_page guards**: Reject saving HTML that doesn’t contain `</html>`; recover full HTML from message content when the tool call was truncated (already implemented).

This addresses the root cause by (a) not relying on huge tool arguments, (b) saving long content from the message when we detect it, and (c) making truncation visible and actionable.

---

## Implementation (done)

- **base/util.py**: When building the assistant message from the completion response, attach `_finish_reason` from `choices[0].finish_reason`. When `finish_reason == "length"`, log a WARNING that the response was truncated.
- **core/llm_loop.py**: (1) When appending the assistant message, strip `_finish_reason` so it is not sent back to the API; keep it in a local variable `_last_finish_reason` for the tool loop. (2) When executing `save_result_page`, if `_last_finish_reason == "length"`, log a WARNING that content may be incomplete. (3) **Markdown/long-document fallback**: If the model returns no tool_calls and the reply contains a long ```markdown ... ``` block (> 500 chars) or the reply is long (> 4000 chars) and looks like a document (starts with `#` or contains `## `), save it via `save_result_page(..., format='markdown')` and return the link (same as the existing HTML fallback).
- **tools/builtin.py**: Reject truncated HTML in `save_result_page` (content without `</html>`) and ask the model to put full HTML in message content (already implemented earlier).
- **Prompt**: Prefer putting very long HTML in a ```html block in the message (already added).
- **core/llm_loop.py (prefer local for long-output turn)**: In mix mode, when the last message is a tool result and the last tool was `document_read` or `run_skill`, and we're currently using cloud, switch to **local** for this turn. That way the turn that generates HTML/slides/reports uses local and honors **`completion.max_tokens`** (e.g. 32768) when you have both local and cloud configured.
