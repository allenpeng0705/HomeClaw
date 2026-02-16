# Prompt Manager: config/prompts

Prompts are loaded by the central **PromptManager** (base/prompt_manager.py) with language and optional model overrides. See docs/PromptManagement.md for design.

## Layout

- **Section** = directory under `config/prompts/` (e.g. `orchestrator`, `chat`, `memory`, `tam`).
- **Name** = base name of the file (e.g. `intent`, `response`, `memory_check`).
- **Language** = optional suffix: `<name>.<lang>.yml` (e.g. `intent.en.yml`, `intent.cn.yml`).
- **Model** = optional: `<name>.<model>.<lang>.yml` for model-specific overrides.

**Resolution order:**  
`<section>/<name>.<model>.<lang>.yml` → `<section>/<name>.<lang>.yml` → `<section>/<name>.yml`

## YAML format

**Single system string (content):**
```yaml
content: |
  Your prompt here. Placeholders: {text}, {chat_history}, {context}.
  Use {{ and }} for literal braces in JSON examples.
```

**Chat messages (messages):**
```yaml
messages:
  - role: system
    content: "System instruction. Placeholders: {query}."
  - role: user
    content: "User part: {user_input}"
```

Placeholders in `content` or in each message `content` are filled via `get_content(..., **kwargs)` or `get_messages(..., **kwargs)`.

## Sections and prompts

| Section      | Name               | Placeholders              | Used by                    |
|-------------|--------------------|---------------------------|----------------------------|
| orchestrator| intent             | chat_history, text        | Orchestrator (TIME/OTHER)  |
| orchestrator| intent_and_plugin  | plugin_list, plugin_count, first_plugin_id, chat_history, text | Orchestrator (single-call) |
| chat        | response           | context                   | answer_from_memory (RAG)   |
| memory      | memory_check       | user_input                | process_memory_queue       |
| tam         | scheduling         | text, chat_history, ...  | TAM (future)               |

## Adding a new prompt

1. Create `config/prompts/<section>/<name>.<lang>.yml` (e.g. `orchestrator/intent.cn.yml`).
2. Use `content: |` for a single string or `messages:` for a list of {role, content}.
3. In code, call `pm.get_content("section", "name", lang=..., **kwargs)` or `pm.get_messages(...)` with fallback to existing in-code default when `use_prompt_manager` is false or file is missing.

## Config (core.yml)

- `use_prompt_manager: true` — use this layout; when false, all prompts use in-code defaults.
- `prompts_dir: config/prompts` — base directory.
- `prompt_default_language: en` — fallback when lang not provided.
- `prompt_cache_ttl_seconds: 0` — 0 = cache by load time; >0 = TTL in seconds.
