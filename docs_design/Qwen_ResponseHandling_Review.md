# Qwen / Qwen 3.5 response handling — review and behavior

---

## Official Qwen 3.5 tool_call format (reference)

**Sources:** [Qwen Function Calling](https://qwen.readthedocs.io/en/latest/framework/function_call.html), [llama.cpp function-calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md), [Qwen llama.cpp](https://qwen.readthedocs.io/en/latest/run_locally/llama.cpp.html).

- **Recommendation:** Qwen docs recommend **Hermes-style tool use** for Qwen3 to maximize function-calling performance.
- **Input:** OpenAI-style `tools` array: each tool has `type: "function"`, `function: { name, description, parameters }` (JSON Schema). We send this via the completion API; llama-server uses the model’s chat template (e.g. Jinja) to format it.
- **Model output (what the model is trained to produce):** The template expects the model to output tool calls in a structured way. Frameworks (Qwen-Agent, vLLM, llama-server) then **parse** that into:
  - `function_call` or `tool_calls[]` with **`name`** and **`arguments`** (arguments as a **JSON string**, e.g. `"{\"location\": \"San Francisco\"}"` for OpenAI compatibility).
- **Exact format we instruct and parse:** So that our parser and the model agree, we tell the model to output **exactly**:
  - **JSON:** `<tool_call>{"name": "tool_name", "arguments": {"key": "value"}}</tool_call>`
  - **XML:** `<tool_call><function>tool_name</function><key>value</key></tool_call>`
  We do **not** use `<tool>...</tool>` or `(key=value)`; those are not the Hermes/OpenAI-style format Qwen and llama.cpp use. See system prompt in `core/llm_loop.py` (tool_format_line for qwen35 / qwen3_style) and parser in `core/services/tool_helpers.py` (`parse_raw_tool_calls_from_content`, `_parse_one_tool_call_inner`).
- **llama-server:** Supports tool calls when started with `--jinja`; Qwen 2.5 uses Hermes 2 Pro format in llama.cpp. The server returns OpenAI-compatible `tool_calls` with `function.name` and `function.arguments` (string). For Qwen3, the embedded chat template in the GGUF includes tool support; the server parses the model’s raw output into `tool_calls`.

---

## Summary: What we did on Qwen 3.5 (plain language)

**Qwen 3.5** in HomeClaw means: you set **`qwen_mode: "qwen35"`** in **`llm.yml` → `llama_cpp`** (single entry point for all Qwen settings) so the app treats the local model as **Qwen 3.5 9B** and turns on extra behavior.

### 1. Qwen 3.5–specific behavior (request / prompt)

When **`qwen_model == "qwen35"`** and **tools are in use**:

| What | Purpose |
|------|--------|
| **Temperature** | Tool turn uses `tool_temperature` (default 0.1). |
| **Thinking off** | `enable_thinking: False` so the model doesn’t put the real reply inside `<think>` and leave `content` empty. |
| **Presence penalty** | `presence_penalty: 1.5` to reduce repetitive filler. |
| **Stop sequences** | We add `</think>` and `</tool_call>` so the server stops at the right place. |
| **System prompt** | A **&lt;tools&gt;** block tells the model: output only `<tool_call>{"name":"...","arguments":{...}}</tool_call>` or `NO_TOOL_REQUIRED`; no `<think>` or conversational text. |
| **GBNF grammar** | Optional file `config/grammars/qwen35_tools.gbnf` is loaded and sent to the server so the model **can only** output that tool-call format (no free text). Requires llama.cpp b8150+. |

So for **Qwen 3.5** we: (a) tell it how to format tool calls, (b) try to avoid `<think>` and free text in tool turns, and (c) optionally enforce that with a grammar.

### 2. Fixing “empty response” (applies to Qwen 3 and Qwen 3.5)

Some Qwen servers sometimes put the **actual reply** in a field other than `content` (e.g. **`reasoning_content`**) and leave **`content`** empty. If we only used `content`, the user would see an empty message.

**What we did:**

1. **Fallback when `content` is empty**  
   We look, in order, at: **`reasoning_content`**, **`reasoning`**, **`reason`**, **`output`**, **`text`**. The first non-empty one is used as the reply. That way we still show the answer when the server put it in one of these fields.

2. **When we do *not* use that fallback**  
   - If the message has **`tool_calls`**: the “reply” in those fields is usually “I will call tool X”, not the final answer, so we don’t show it.  
   - If the text is **short** (≤180 chars) **and** clearly about calling a tool (e.g. “需要调用”, “folder_list”, “document_read”, “tool_call”), we treat it as internal reasoning and don’t show it.

3. **Narrowing the “tool reasoning” filter (the fix for false empties)**  
   We used to skip **any** text that contained phrases like “步骤：” or “我需要先”. Many **normal** Chinese answers use those, so valid replies were dropped and the user saw empty.  
   **Change:** we only skip when the text is **short** (≤180 chars) **and** contains **strong** tool phrases (e.g. “需要调用”, “folder_list”, “document_read”, “tool_call”). Long text is **always** used, so real multi-sentence answers are no longer wrongly cleared.

4. **Extra keys**  
   We also use **`output`** and **`text`** as fallback keys in case your server puts the reply there.

**In short:**  
- **Qwen 3.5–specific:** stricter tool format, no thinking in tool turns, presence_penalty, stop tokens, optional GBNF grammar.  
- **Empty-response fix (Qwen 3 + 3.5):** when `content` is empty, use `reasoning_content` (or other keys) as the reply, but don’t show short “I’ll call a tool” reasoning; and we no longer drop normal answers that contain “步骤” or “我需要先”.

### 3. reasoning_budget: 0 vs -1 (tradeoff; neither is perfect)

| Setting | Pros | Cons |
|--------|------|------|
| **reasoning_budget: -1** (recommended) | Fewer truncation issues; we remove `</think>` from stop so the answer after `<think>` is not cut off. Model can reason then respond. | Some servers put the full reply in **reasoning_content** and leave **content** empty. We use reasoning_content as the reply and strip `<think>`, which reduces empty-content issues. If you still see empty replies, set **qwen_always_use_fallback_for_empty: true** (completion or tools_config). |
| **reasoning_budget: 0** | Thinking disabled; server is asked to put output in content. | With 0 some setups produce more **malformed tool output** ("response format was not recognized") or truncation. We added explicit tool-format examples in the system prompt and extraction from malformed `(text="...")` to mitigate. |

Recommendation: use **-1** unless you must disable `<think>`. If you use -1 and still see empty content, enable **qwen_always_use_fallback_for_empty: true**. If you use 0 and see "response format was not recognized", ensure the model gets the exact tool format (see Official Qwen 3.5 tool_call format above) and that echo is not in the tool set.

**Why is `content` sometimes empty when thinking is on?**  
When **reasoning_budget: -1**, the model outputs `<think>...</think>` then the actual reply. The **server** (llama.cpp / Qwen chat template) is supposed to split that: put the ` <think>` block in `reasoning_content` and the text after `</think>` in `content`. In practice, many setups **do not** do that split: they put the **entire** generation (including the part after `</think>`) into `reasoning_content` and leave `content` empty. So the root cause is **server/template behavior**: the response builder does not parse the model output and set `content` from the post-`</think>` text. We cannot fix that in HomeClaw. What we do: when `content` is empty and `reasoning_content` has text, we **use reasoning_content as the reply** and strip `<think>...</think>` before showing it. With **reasoning_budget != 0** we now **default** to always using that fallback (as if `qwen_always_use_fallback_for_empty: true`), so you should no longer see empty replies from this cause. Set `qwen_always_use_fallback_for_empty: false` in config if you want to restore the stricter filtering (and accept occasional empty content).

### 4. Optional tuning (accuracy vs empty replies)

If turning off thinking hurts accuracy or you still see empty replies, you can set (under **completion** in `llm.yml` or **tools_config** in `skills_and_plugins.yml`):

| Option | Effect |
|--------|--------|
| **`reasoning_budget`** | Set **`reasoning_budget: 0`** in llama_cpp to disable `<think>` (--reasoning-budget 0). Omit or set >0 (e.g. 1024) to allow thinking; we strip `<think>` from displayed/stored text and remove `</think>` from stop. Restart the llama.cpp server after changing. |
| **`qwen_always_use_fallback_for_empty: true`** | When `content` is empty, **always** use the first non-empty alternative (reasoning_content, etc.), and **skip** the “short and looks like tool reasoning” filter. Reduces empty replies; may occasionally show one line of internal reasoning. |

**Why replies looked truncated:** When reasoning_budget is not 0, the model outputs `<think>...</think>` then the answer. If **stop** included `</think>`, generation stopped there. Core removes `</think>` from stop when reasoning_budget is not 0. Set stop in **llm.yml** (`completion.stop`); do not add `</think>` when using thinking. If truncation persists, check `finish_reason=length` and raise `completion.max_tokens` and `llama_cpp.predict`.

---

## Where it lives

- **`base/util.py`**: `_openai_chat_completion_message_impl` (local/ollama HTTP path) and `_get_qwen_model()` / `get_qwen35_grammar()`.
- **`core/llm_loop.py`**: Qwen tool-format instructions, `_qwen35_grammar` for the tool loop, and mix fallback when local returns empty.

## What we do for Qwen / Qwen 3.5

1. **Config (single entry point: `llm.yml` → `llama_cpp`)**  
   - Set **`qwen_mode`**: `"qwen3"` or `"qwen35"`. Optional: `qwen35_grammar_path`, `qwen35_use_grammar`. Do not set Qwen in `tools_config` or `completion`.  
   - When tools are present: `tool_temperature` 0.1, `enable_thinking: False` for local/ollama.  
   - For qwen35: `presence_penalty` 1.5; **stop** sequences from `completion.stop` or `llama_cpp.stop` in llm.yml. For Qwen with tools: set `stop` to `["</tool_call>"]` when thinking is on, or `["</think>", "</tool_call>"]` when thinking is off.

2. **Tool format**  
   - In the system prompt we inject a line telling the model to use `<tool_call>{"name":"...","arguments":{...}}</tool_call>`.  
   - When `qwen_mode == "qwen35"` and tools are present, we pass a GBNF grammar (path from `llama_cpp.qwen35_grammar_path`, default `config/grammars/qwen35_tools.gbnf`) to constrain output.

3. **Empty `content` and `reasoning_content`**  
   - Some Qwen servers put the user-facing reply in `reasoning_content` and leave `content` empty.  
   - When **content** is empty we look for alternative content in this order:  
     `reasoning_content`, `reasoning`, `reason`, `output`, `text`.  
   - We **do not** use that alternative when:
     - The message has **tool_calls** (reasoning is about the call, not the final reply), or  
     - The alternative is **short** (≤180 chars) **and** clearly about calling a tool (phrases like “需要调用”, “folder_list”, “should call”, “tool_call”, etc.).  
   - If the alternative is **long** (>180 chars) we **always** use it, so normal long replies are not dropped just because they contain words like “步骤” or “我需要先”.

## Why the local model sometimes returned empty

- **Cause 1:** The server really returned empty `content` and no usable `reasoning_content` (e.g. model or template issue).  
- **Cause 2:** We were too aggressive in treating `reasoning_content` as “tool-calling reasoning” and cleared it. For example:
  - **“步骤：”** was in the skip list; many normal Chinese replies use “步骤：” and were wrongly dropped.  
  - Any length of text that contained one of those phrases was skipped; long, valid replies could be dropped.

## Changes made (review)

- **Narrow “tool reasoning” heuristic**  
  - Skip alternative content only when it is **short** (≤180 chars) **and** matches **strong** tool-related phrases (e.g. “需要调用”, “folder_list”, “document_read”, “should call”, “tool_call”).  
  - Removed from the skip list: “步骤：”, “我需要先” (too common in normal answers).  
  - Long alternative content (>180 chars) is **always** used, so real multi-sentence replies are kept.

- **More fallback keys**  
  - We also check **`output`** and **`text`** in the message, in case the server puts the reply there.

- **Necessity of the logic**  
  - **Yes.** Keeping the “empty content → use reasoning_content (or other alt keys)” fallback is necessary for servers that put the final answer in `reasoning_content`.  
  - Keeping the “skip when message has tool_calls” rule is necessary so we don’t show “I will call folder_list” as the user reply.  
  - The “skip when short and looks like tool reasoning” rule is kept but tightened so we only drop short, clearly tool-only reasoning and not real replies.

## Guarantee: `<think>...</think>` not stored anywhere

We ensure **`<think>...</think>`** (and any unclosed `<think>` or leading `</think>`) is **never** stored in:

| Storage | Where we strip |
|--------|-----------------|
| **Chat history** | `core/llm_loop.py`: `response = strip_reasoning_from_assistant_text(response)` before building `memory_turn_data` and before `core.chatDB.add(..., chat_message=message)`. **`core/core.py`**: `add_chat_history()` and `add_chat_history_by_role()` strip `ai_message` / `responder_text` before calling `chatDB.add`, so plugin or other callers never persist `<think>`. |
| **Memory (RAG / MemOS)** | `core/core.py` → `process_memory_queue` passes `memory_turn_data` (whose `assistant_message` is the already-stripped `response`) to `mem_instance.add()`. **`memory/mem.py`**: for list input, assistant content is stripped again with `strip_reasoning_from_assistant_text(content)` before building the string sent to embedding/vector store. **Defense in depth.** |
| **Cognee** | Same `memory_turn_data` (stripped at source). **`memory/cognee_adapter.py`**: when building the string for `cognee.add()`, assistant content is stripped with `strip_reasoning_from_assistant_text(content)` before appending. **Defense in depth.** |
| **Memos** | Same `memory_turn_data`. **`memory/memos_adapter.py`**: for assistant role we call `strip_reasoning_from_assistant_text(content)` before adding to the messages list. **Defense in depth.** |
| **Own RAG / embeddings** | Memory backend (mem, Cognee, or composite) receives the same list; all paths strip assistant content before embedding or sending to Cognee/Memos. So nothing inside `<think>` is ever embedded or indexed. |

**Implementation:** `base/util.py` → `strip_reasoning_from_assistant_text(text)` removes `<think>...</think>` (with optional whitespace in tags), handles unclosed `<think>` or leading `</think>`, and returns the rest. Used in llm_loop, core.py (add_chat_history, add_chat_history_by_role), mem.py, cognee_adapter.py, and memos_adapter.py as above.

---

## Files touched (Qwen 3.5 + storage guarantee)

| File | Changes |
|------|--------|
| **base/util.py** | `strip_reasoning_from_assistant_text`, `_get_qwen_model`, `get_qwen35_grammar`, empty-content fallback + tool-reasoning heuristic, `stop_extra` param, remove `</think>` from stop when reasoning_budget != 0. |
| **core/llm_loop.py** | Grammar only on tool-decision turn, `stop_extra` for `</tool_call>`, strip response before chat DB and memory_turn_data. |
| **core/core.py** | Strip in `add_chat_history` and `add_chat_history_by_role` before chatDB.add. |
| **llm/llmService.py** | `reasoning_budget` from config → --reasoning-budget N; when 0, add enable_thinking: false for Qwen. |
| **memory/mem.py** | Strip assistant content in `add()` when data is list. |
| **memory/cognee_adapter.py** | Strip assistant content before building string for cognee.add(). |
| **memory/memos_adapter.py** | Strip assistant content before appending to messages; fix append for user/assistant. |
| **config/grammars/qwen35_tools.gbnf** | Optional think block, then tool_call or NO_TOOL_REQUIRED; robust number/string. |
| **config/llm.yml** | stop / qwen35_stop removed; qwen_enable_thinking, qwen_always_use_fallback_for_empty; comments. |
| **docs_design/Qwen_ResponseHandling_Review.md** | Full review, guarantee table, logic review, files touched. |

---

## Logic review (consistency check)

| Area | Behavior | Correct? |
|------|----------|----------|
| **Stop** | From config only (`completion.stop` / `llama_cpp.stop`). `</tool_call>` added **only on tool-decision turns** via `stop_extra` (when grammar is used); not added after tool result so normal replies are not truncated. | ✓ |
| **Grammar** | Loaded when qwen35 and tools; passed **only when last message is from user** (tool-decision turn). After tool result we don’t pass grammar so the model can output free text. Grammar allows optional `<think>...</think>` then tool call or NO_TOOL_REQUIRED. | ✓ |
| **Empty content** | Fallback keys: `reasoning_content`, `reasoning`, `reason`, `output`, `text`. Skip only when message has tool_calls, or when short + strong tool phrases; `qwen_always_use_fallback_for_empty` can force using fallback. | ✓ |
| **Thinking** | `reasoning_budget: 0` → --reasoning-budget 0 and enable_thinking: false; omit or >0 → allow <think> (we strip it and remove </think> from stop). One grammar file allows optional think block. | ✓ |
| **Storage** | Response stripped in llm_loop before chat DB and before building memory_turn_data. Mem, Cognee, and Memos strip assistant content again before storing. | ✓ |

---

## Config reference

- **`config/llm.yml`** → **`llama_cpp`** only: `qwen_mode: "qwen35"` or `"qwen3"`, optional `qwen35_grammar_path`, `qwen35_use_grammar`. Do not set Qwen in `completion` or in `skills_and_plugins.yml`. Optional tool tuning (e.g. `tool_temperature`, `qwen3_tool_format_instruction`) may remain under tools/completion.
