# Grammars (GBNF)

GBNF grammars are used to constrain LLM output for specific models or tool-calling modes.

## qwen35_tools.gbnf

Used when **`qwen_model: "qwen35"`** (Qwen 3.5 9B) and tools are present. Forces the model to output only:

```xml
<tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>
```

so it cannot emit conversational text or `<think>` blocks. Configure path via **`tools.qwen35_grammar_path`** in `skills_and_plugins.yml` (default: `config/grammars/qwen35_tools.gbnf`).

Requires llama.cpp b8150+ for full Qwen 3.5 support.
