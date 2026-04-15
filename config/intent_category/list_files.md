---
id: list_files
display_name: List or browse files
enabled: true
priority: 55
classifier_description: "List directory contents, browse folders, find filenames or patterns, or 'what files are in …' — structure discovery, not reading file contents."

match_patterns:
  - (?i)list\s+files\s+in\s+
  - (?i)what'?s\s+in\s+(folder|directory)\s+
  - 有哪些文件
  - 里有什么文件

category_tools:
  tools:
  - folder_list
  - file_find
  - document_read
  - get_file_view_link
---

## Description
The user wants to **see what exists** under a path: directory listing, glob patterns, “what’s in `documents/`”, tree-style browsing, *有哪些文件*, *列出*, *ls*, *搜索文件名*. The goal is **inventory and navigation**, not parsing the text inside a specific document (that is **read_document**).

## Positive examples
- “List files in `documents/`.”
- “What’s in the output folder?”
- “Show everything under `share/images` recursively.”
- “Find all `.pdf` under `reports/`.”
- “有哪些 pdf 在 documents 里”
- “Does `config/` contain a `settings.yml`?”
- “我都有哪些文件？”
- “帮我看看 images 目录里有什么。”

## Negative boundaries
- **read_document**: User wants **content**, summary, or Q&A **inside** a named file.
- **get_file_link**: User wants a **single file’s share/view link**, not a folder listing.
- **search_web**: **Internet** lookup, not local filesystem.
- **coding**: User wants to **edit or run** the project — prefer **coding** unless they only asked to **list** paths.

## Workflow hints
- `folder_list` and `file_find`; `document_read` / `get_file_view_link` only as follow-ups after listing.
