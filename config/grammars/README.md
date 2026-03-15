# Grammars (GBNF)

GBNF grammars are used to constrain LLM output for specific models or tool-calling modes.

## Tool call formats (with or without grammar)

Parsing supports both formats in model output:
- **JSON**: `<tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>`
- **XML**: `<tool_call><function>tool_name</function><key>value</key>...</tool_call>` (one tag per argument; also accepts `<function=name>`). Multiple `<tool_call>...</tool_call>` blocks are parsed in order. When using grammar (qwen35), only JSON is constrained by the grammar; without grammar the model may use either format.

## qwen35_tools.gbnf

Used when **`qwen_mode: "qwen35"`** (Qwen 3.5 9B) is set in **`llm.yml` → `llama_cpp`** and tools are present. The grammar allows:

1. **Optional** `<think>...</think>` block (when **reasoning_budget** is not 0 the model may emit thinking first).
2. Then either `<tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>` or **NO_TOOL_REQUIRED**.

So one grammar works for both cases: when **reasoning_budget: 0** the model won't emit `<think>`, so the optional block matches zero times. When reasoning_budget is omitted or >0, the model can output `<think>...</think>` and the grammar accepts it instead of breaking. No need for separate grammar files. **Configuration (single entry point):** In **`llm.yml`** under **`llama_cpp`** set `qwen_mode: qwen35`. Optional: `qwen35_grammar_path` (default: `config/grammars/qwen35_tools.gbnf`), `qwen35_use_grammar: true` to enable grammar (default: false; we parse JSON and XML without grammar). Do not set Qwen in `skills_and_plugins.yml` or under `completion`.

**When the grammar is used:** Only on **tool-decision** turns (when the last message is from the user). When the last message is a tool result, the grammar is **not** sent, so the model’s normal reply (e.g. final answer, summary) is never constrained by this file. Default is no grammar. To enable, set **`qwen35_use_grammar: true`** under **`llama_cpp`** in `llm.yml`.

### When is the grammar applied?

- **Only on tool-decision turns:** when the **last message** in the conversation is from the **user** (e.g. first turn with "你好", or user sent a new message). In that case the model must choose: call a tool or not.
- **Not applied after tool results:** when the last message is from **tool** (we are "continuing after tools ran"), the grammar is **not** sent. The model then generates free-form text (final answer, summary, etc.) and is not constrained by the GBNF.

So the grammar constrains only the **"should I call a tool?"** decision; it does not constrain the model's normal conversational reply.

### How to enable and set the grammar file

1. In **`config/llm.yml`** under **`llama_cpp`**:
   - Set **`qwen35_use_grammar: true`** to enable grammar (default is `false`).
   - Optionally set **`qwen35_grammar_path`** (default: `config/grammars/qwen35_tools.gbnf`). If **reasoning_budget** is not 0, the code may load `qwen35_tools_with_think.gbnf` from the same directory if it exists.
2. The grammar is loaded at runtime by `Util.get_qwen35_grammar()` and sent to the **local** llama.cpp server in the completion request. Per llama.cpp server API: the **string content** of the .gbnf file is passed in the top-level **`"grammar"`** field of the JSON payload (not inside `extra_body`). **Important:** Many llama.cpp servers return 400 "Cannot use custom grammar constraints with tools" when both `grammar` and `tools` are present. We therefore **do not send grammar** when the request includes tools (local/ollama); the model then uses prompt-based tool format and we parse JSON/XML `<tool_call>` from the response. Cloud/LiteLLM backends typically do not support grammar and will ignore or reject it.

### Side effects of using the grammar

**Benefits:**

- **No malformed output:** The model cannot emit invalid JSON, stray tags (e.g. `<response>`, `</reponse>`), or mixed text. Output is strictly either `<tool_call>{"name":"...","arguments":{...}}</tool_call>` or the literal **NO_TOOL_REQUIRED**.
- **Predictable parsing:** Easier to parse and no "response format not recognized" from hybrid or truncated tool_call.

**Costs / caveats:**

- **NO_TOOL_REQUIRED is not a user-facing reply:** When the model outputs the literal `NO_TOOL_REQUIRED`, the code treats it as "no tool needed" and **retries the turn without tools** to get the actual reply (e.g. "你好！需要什么帮助？"). If that retry fails, the user sees a short fallback like "What can I help you with?" instead of the literal `NO_TOOL_REQUIRED`.
- **Backend support:** Only backends that accept a grammar (e.g. llama.cpp with GBNF) use it; cloud APIs usually do not. We send grammar as the top-level `"grammar"` field for local/ollama (per llama.cpp server API). If you still see malformed tool_call output with grammar enabled, verify your llama.cpp server version supports grammar on `/v1/chat/completions` when `tools` are present.
- **Empty name still valid in grammar:** The GBNF allows any valid JSON object, so `"name": ""` is still grammatically valid. The executor/parser still rejects tool_calls with an empty or missing `name`.
- **Constrained decoding:** The model cannot add extra explanation in the same turn as the tool decision; the actual reply comes from the next (no-tools) call or from the next turn after tool results.

Requires llama.cpp b8150+ when grammar is enabled.
