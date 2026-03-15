# Tool description guidelines for accurate LLM selection

Local and smaller LLMs often select tools more accurately when descriptions are **short**, **action-oriented**, and **trigger-clear**. This doc explains how we refine tool descriptions and how to add or tune them.

---

## 1. Config: shorten descriptions for local LLMs

In **`config/skills_and_plugins.yml`** under **`tools`**:

```yaml
tools:
  # When > 0: tool descriptions sent to the LLM are shortened (use short_description if set, else truncate at sentence boundary). Helps local/smaller LLMs.
  description_max_chars: 200   # 0 = full description (default)
```

- **`0` or omit**: Full `description` is sent (default).
- **`> 0`** (e.g. **150–250**): For each tool we send either:
  - **`short_description`** if the tool has one and it fits within the limit, or
  - The full **`description`** truncated to `description_max_chars` at a sentence or word boundary.

Use **200** or **250** as a starting point for local/small models; increase if the model still confuses tools.

---

## 2. Two-tier descriptions

Each built-in tool has:

- **`description`**: Full text (when to use, parameters, caveats). Shown when `description_max_chars` is 0.
- **`short_description`** (optional): One-line cue for local LLMs. Used when `description_max_chars > 0` and it fits.

Example in code:

```python
ToolDefinition(
    name="remind_me",
    description="Schedule a ONE-SHOT reminder (single notification). USE THIS when the user says: 'remind me in N minutes', ...",
    short_description="Use when: user says 'remind me in N minutes', 'N分钟后提醒', 'at 9am', one-shot reminder. Pass minutes OR at_time; message = short label. Not for recurring → use cron_schedule.",
    parameters={...},
    execute_async=_remind_me_executor,
)
```

---

## 3. How to write good descriptions

### Full description (`description`)

- **Lead with “Use when:”** or a clear one-sentence trigger so the model can match user intent quickly.
- **Then** add parameter hints and caveats (path from folder_list, one-shot vs recurring, etc.).
- Prefer **short sentences**. Avoid long paragraphs.

### Short description (`short_description`)

- **One or two sentences**, under the chosen `description_max_chars` (e.g. ≤200).
- Start with **“Use when:”** and the main user trigger (e.g. “user says ‘remind me in N minutes’”, “user asks to list files in a folder”).
- Add **one** key disambiguation (e.g. “Not for recurring → use cron_schedule”) or main param (e.g. “Pass path from folder_list/file_find”).

### Triggers that help local LLMs

- **Explicit phrases**: “remind me in 5 minutes”, “list my documents”, “search the web for X”, “send me that file”.
- **Intent keywords**: “one-shot reminder”, “recurring”, “record a date”, “read/summarize document”, “save as PDF”.
- **Tool boundary**: “Not for X → use tool Y” to avoid wrong tool (e.g. remind_me vs cron_schedule, document_read vs file_read).

---

## 4. Which tools have short_description

The following have **short_description** for local-LLM mode:

- **route_to_tam**, **route_to_plugin**
- **remind_me**, **record_date**, **cron_schedule**
- **run_skill**
- **document_read**, **folder_list**, **file_find**
- **web_search**
- **save_result_page**, **get_file_view_link**

Others use **truncation** when `description_max_chars > 0` (first sentence or first N chars at a boundary). To add **short_description** for more tools, edit **`tools/builtin.py`** and add the optional `short_description="..."` argument to the corresponding **ToolDefinition**.

---

## 5. Summary

| Goal | Action |
|------|--------|
| Better tool selection for local LLMs | Set **`tools.description_max_chars: 200`** (or 150–250) in `skills_and_plugins.yml`. |
| Per-tool one-liner | Add **`short_description="Use when: ..."`** in **`tools/builtin.py`** for that tool. |
| Keep full text for cloud/large models | Leave **`description_max_chars: 0`** (default). |

Descriptions are sent to the LLM in the **tools** array of the chat completion request; shorter, trigger-first text usually improves accuracy for small/local models.

---

## 6. Few-shot tool selection examples

To further guide local/Qwen models, **few-shot examples** (User → Thought → Call) are injected into the system prompt when tools are present. They show how to map natural language to the right tool and arguments.

- **File**: `config/prompts/tools/selection_examples.yml` — edit this to add or change examples. Keep the **User / Thought / Call** format.
- **Config**: `tools.tool_selection_examples` in `skills_and_plugins.yml` (default **true**). Set to **false** to disable injection.
- **Content**: The YAML `content` block is appended after the routing block. We include **representative examples for all major tool categories** (file/document, scheduling, plugins, skills, memory, profile, web, knowledge base, sessions, time, models, image) so the model sees patterns for each category. Not every tool has an example—that would make the prompt very long; add more in the YAML if you need coverage for specific tools.

Example entry in the YAML:

```yaml
User: "What's inside the 'work' folder?"
Thought: User is exploring directory structure.
Call: folder_list(path="work")
```

This reduces "traps" where the model picks the wrong tool or wrong arguments for phrases like "find pictures of my cat" (file_find) vs "summarize my resume" (document_read).
