# Prompt Management: Current State and Refinement Proposal

## 1. Current state: how prompts are managed

### 1.1 Sources and usage

| Source | Content | Used by | Language / model selection |
|--------|---------|---------|----------------------------|
| **memory/prompts.py** | `RESPONSE_TEMPLATE`, `MEMORY_CHECK_PROMPT`, `MEMORY_SUMMARIZATION_PROMPT`, `ADD_MEMORY_PROMPT`, `UPDATE_MEMORY_PROMPT`, `MEMORY_DEDUCTION_PROMPT`, `MEMORY_ANSWER_PROMPT` (Python string constants) | Core `answer_from_memory` (RESPONSE_TEMPLATE), Core `process_memory_queue` (MEMORY_CHECK_PROMPT), memory pipeline (others) | None. Single English/mixed EN+CN text. |
| **core/prompts/prompt_en.yml**, **prompt_cn.yml** | YAML: `Prompts: { section: [ { name, prompt: [ { role, content } ] } ] }`. Sections: EMAIL (entrypoint), core (choose_agent). Placeholders: `{subject}`, `{body}`, `{query}`, `{all_capabilities}`. | `Core.prompt_template(section, prompt_name)` — file chosen by `main_llm_language()` (en → prompt_en.yml, cn → prompt_cn.yml). Referenced in refactor doc; email channel may use different path. | Language only (en/cn via main_llm_language). No model-specific variant. |
| **core/orchestrator.py** | `create_prompt(text, chat_history)` and `create_combined_intent_and_plugin_prompt(text, chat_history, plugin_infos)` — long Python f-strings. | Orchestrator `translate_to_intent`, `translate_to_intent_and_plugin` | None. English only, hardcoded. |
| **core/tam.py** | `create_prompt(text, chat_history)` — long Python f-string; plus inline `prompt_template` for cron/reminder parsing. | TAM `process_intent` (scheduling LLM call) | None. English only, hardcoded. |
| **core/core.py** | Hardcoded user-message wrapper in `answer_from_memory`: `"Please provide a response to my input: '{query}'..."`. Routing block built in code (unified flow). | Main chat, unified routing | None. |
| **config/workspace/** | IDENTITY.md, AGENTS.md, TOOLS.md — injected as system-prompt blocks. | `answer_from_memory` (workspace bootstrap) | Not prompt “templates”; content is loaded as-is. |
| **skills/** | SKILL.md per skill — name/description (and optionally body) injected as system block. | `answer_from_memory` (skills block) | Not per-prompt language/model. |

### 1.2 Selection logic today

- **Language:** Only for YAML prompts: `prompt_<main_llm_language>.yml` (e.g. `prompt_en.yml`, `prompt_cn.yml`). Main chat and orchestrator/TAM do not use this; they use Python strings.
- **Model:** No model-specific prompts. Same text for all LLMs.
- **Dynamic selection:** No request-level or session-level override (e.g. user locale, A/B prompt).

### 1.3 Pain points

1. **Maintainability:** Long prompts live in Python (orchestrator, TAM, memory/prompts.py). Edits require code changes and mix content with logic.
2. **Multi-language:** Only EMAIL/core YAML is language-aware. Main response template, orchestrator, TAM, and memory prompts are single-language or mixed.
3. **No model-specific prompts:** Cannot tune system/instruction text per model (e.g. shorter for small context, different style for different APIs).
4. **Scattered entry points:** No single place to list or override prompts; `prompt_template()` exists but is not used for orchestrator, TAM, or main chat.
5. **Duplication:** Many commented-out variants in memory/prompts.py; no clear “one source of truth” per use case.

---

## 2. Refinement proposal: easier to maintain, dynamic, multi-language, model-aware

### 2.1 Goals

- **Easy to maintain:** Prompts in files (YAML or markdown), not buried in code. Optional UI or script to edit.
- **Dynamically selected:** Resolve prompt by (section, name) plus optional (language, model).
- **Multi-language:** Support per-language variants (e.g. en, cn, es) with fallback to a default.
- **Model-aware (optional):** Allow overrides per model or model family (e.g. “short_system” for 4k models).

### 2.2 Central prompt loader (new module)

Add a small **prompt manager** (e.g. `base/prompt_manager.py` or `core/prompts/loader.py`) that:

1. **Loads from a structured layout**, e.g.:
   - `config/prompts/<section>/<name>.<lang>.yml` (or `.md`), e.g.  
     `config/prompts/orchestrator/intent.en.yml`,  
     `config/prompts/orchestrator/intent.cn.yml`,  
     `config/prompts/chat/response.en.yml`,  
     `config/prompts/tam/scheduling.en.yml`
   - Or a single YAML per section with keys: `name`, `language`, optional `model`, and `content` (or `messages`).

2. **Resolution order:** For a request `(section, name, language=None, model=None)`:
   - Prefer: `<section>/<name>.<model>.<lang>.yml` (if model-specific exists)
   - Else: `<section>/<name>.<lang>.yml`
   - Else: `<section>/<name>.yml` (default)
   - Language from: argument → request/session metadata → `main_llm_language()` → `"en"`.

3. **Format:** Same as current YAML prompts where useful: list of `{ role, content }` with optional placeholders like `{text}`, `{chat_history}`, `{context}`. For single system-string prompts (orchestrator, TAM), one file with `content: "..."` and placeholders.

4. **API:** e.g. `get_prompt(section, name, lang=None, model=None, **kwargs)` → returns rendered string or list of messages; `kwargs` used to `.format()` placeholders.

### 2.3 What to move into the new system

| Current | Proposed |
|--------|----------|
| memory/prompts.py (RESPONSE_TEMPLATE, MEMORY_*) | `config/prompts/memory/response.<lang>.yml`, `memory_check.<lang>.yml`, etc. |
| orchestrator create_prompt / create_combined_* | `config/prompts/orchestrator/intent.<lang>.yml`, `intent_and_plugin.<lang>.yml` |
| TAM create_prompt | `config/prompts/tam/scheduling.<lang>.yml` |
| Core user-message wrapper | `config/prompts/chat/user_message.<lang>.yml` or inline in chat section |
| core/prompts/prompt_en.yml, prompt_cn.yml | Migrate to `config/prompts/email/entrypoint.<lang>.yml`, `config/prompts/core/choose_agent.<lang>.yml` (or keep under new loader with section EMAIL/core) |

### 2.4 Backward compatibility and rollout

- Keep existing Python constants as **fallbacks**: if the loader does not find a file for (section, name, lang), use current in-code default (orchestrator, TAM, memory).
- Introduce **config flag** (e.g. `use_prompt_manager: true` in core.yml): when true, Core and orchestrator/TAM call the loader first; when false, behavior unchanged.
- Migrate one section at a time (e.g. orchestrator → TAM → memory → chat).

### 2.5 Optional: model-specific overrides

- Add optional naming: `<name>.<model_family>.yml` (e.g. `response.gpt4o.yml`) or a manifest that maps model id → prompt variant.
- Loader resolves `model` from current LLM name (e.g. `Util().main_llm()` or per-call `llm_name`); if a model-specific file exists, use it; else fall back to language default.

### 2.6 Config sketch (core.yml)

```yaml
# Optional: use central prompt manager for system/instruction prompts
use_prompt_manager: false
prompts_dir: config/prompts   # base dir for section/name/lang/model layout
prompt_default_language: en   # fallback when lang not in request/metadata
```

---

## 3. Summary

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Maintainability** | Prompts in Python + two YAML files | All prompts in config/prompts (YAML/md), single loader |
| **Dynamic selection** | Only language for EMAIL/core YAML | (section, name, language, model) with fallback chain |
| **Multi-language** | Only prompt_en/cn for EMAIL/core | Per-section, per-name language variants + default |
| **Model support** | None | Optional model-specific files or manifest |
| **Backward compatibility** | N/A | Fallback to current in-code prompts; feature flag |

Implementing the central prompt manager and migrating orchestrator and TAM prompts first gives the largest maintainability gain with limited risk; then memory and chat can follow.

---

## 4. Implementation (done)

- **base/prompt_manager.py**: `PromptManager` with `get_content`, `get_messages`, `get_raw`, `get_path`, `list_prompts`, `clear_cache`. Resolution: `<section>/<name>.<model>.<lang>.yml` → `<name>.<lang>.yml` → `<name>.yml`. Placeholder formatting with `{{`/`}}` for literal braces. Optional cache (TTL or mtime). Optional `required_placeholders` validation. Factory: `get_prompt_manager(prompts_dir, default_language, cache_ttl_seconds)`.
- **Config**: `use_prompt_manager`, `prompts_dir`, `prompt_default_language`, `prompt_cache_ttl_seconds` in core.yml and CoreMetadata.
- **config/prompts/**:
  - **orchestrator/intent.en.yml**, **intent_and_plugin.en.yml** — orchestrator intent and combined intent+plugin.
  - **chat/response.en.yml** — main chat RAG system template (placeholder: context).
  - **memory/memory_check.en.yml** — should user input be stored (placeholder: user_input).
  - **tam/scheduling.en.yml** — TAM scheduling JSON (placeholders: current_datetime, chat_history, text).
- **Wired**: Orchestrator `create_prompt` and `create_combined_intent_and_plugin_prompt` use prompt manager when `use_prompt_manager` is true, with in-code fallback. Core `answer_from_memory` (response template) and `process_memory_queue` (memory_check) use prompt manager with fallback. TAM `create_prompt` uses prompt manager with fallback.
- **config/prompts/README.md**: Layout, format, and section/name table.
