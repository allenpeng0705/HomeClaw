# Intent category docs

One markdown file per intent category. HomeClaw **loads category ids, classifier one-liners, `match_patterns`, and `category_tools`** from these files by default (`intent_category_docs_dir` defaults to `config/intent_category` relative to the project root).

Set **`intent_router.intent_category_docs_dir: ""`** in `skills_and_plugins.yml` to **disable** this overlay and use only YAML `categories` / `category_descriptions` / `category_tools`.

## Frontmatter (YAML between `---`)

| Field | Purpose |
|--------|---------|
| `id` | Category id. |
| `display_name` | Human label. |
| `enabled` | `false` excludes the category. |
| `priority` | Sort order (higher first) and tie-break for pattern matching. |
| `classifier_description` | One line for the **classifier LLM** prompt. If omitted, first line of `## Description` is used. |
| `match_patterns` | Optional **`re.search` regex strings** (fast path before semantic/classifier). |
| `category_tools` | Same shape as YAML: `{ profile: minimal }` or `{ tools: [...], skills: [...] }`. Merged with sparse YAML `category_tools` if present (**markdown wins** on the same id). |
| `dag_key`, `planner_skip`, `tool_profile` | Reserved / optional metadata. |

## Body sections

**Description**, **Positive examples**, **Negative boundaries**, **Workflow hints** — used for semantic retrieval and documentation.

## Files

See `*.md` in this directory (excluding `_template.md`, `README.md`).
