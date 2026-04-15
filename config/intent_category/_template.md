---
id: category_id
display_name: Category Name
enabled: true
priority: 50
classifier_description: "One precise line for the semantic classifier: when to pick this category vs others."
# Optional fast-path regex (intent router may use these):
# match_patterns:
#   - "(?i)example\\s+pattern"
category_tools:
  profile: minimal
  # or:
  # tools: [tool_a, tool_b]
  # skills: [skill-folder-1.0.0]
---

## Description
2–4 sentences: what this category means, primary user goal, and how it differs from adjacent categories.

## Positive examples
- Typical query (English)
- Typical query (中文 or mixed)
- Edge case that still belongs here
- Short imperative (“Do X with Y”)

## Negative boundaries
- **other_category_id**: When the user’s real goal is Y, not X — be specific.
- **another_id**: Similar confusion — one line each.

## Workflow hints
- Preferred tools, DAG/skills if any, or “planner decides”.
