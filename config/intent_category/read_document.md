---
id: read_document
display_name: Read or understand a document
enabled: true
priority: 55
classifier_description: "Read, summarize inline, extract, or explain a specific local file or attachment — workspace path, documents/, share/, PDF/Office — not 'search the web' and not only a view link."

match_patterns:
  - (?i)read\s+(the\s+)?file\s+
  - (?i)show\s+(me\s+)?(the\s+)?(contents?|content)\s+of\s+
  - (?i)open\s+documents?/
  - 读一下\s*documents?/
  - 读一下\s*share/
  - 打开\s*documents?/.*\.(md|txt|pdf|docx)

category_tools:
  tools:
  - document_read
  - file_read
  - file_understand
  - folder_list
  - file_find
  - get_file_view_link
---

## Description
The user wants to **ingest or reason about the contents** of a **specific file**: open it, summarize **in chat**, answer questions, extract tables, compare sections, *读一下*, *打开文件*, *这篇 PDF 说了什么*. The object is **local/workspace (or attached) content**, not a generic internet search. If they mainly want a **hosted summary page** or **PDF export**, see **summarize_to_page** / **generate_pdf**.

## Positive examples
- “Read `documents/notes.md` and give me three bullet takeaways.”
- “What does section 2 of the PDF in `share/` say?”
- “读一下 documents/report.md 并列出风险点”
- “Compare chapter 1 vs chapter 3 in this doc.”
- “Extract all dates mentioned in `legal/draft.docx`.”
- “What’s in the attached file?” (when an attachment exists)
- “把这份招股书读一下并总结三点风险。”
- “请解释这份合同第4条在说什么。”

## Negative boundaries
- **search_web**: No **local file** focus — user wants **internet** facts.
- **list_files**: They only want **names in a folder**, not **inside-file** content.
- **get_file_link**: They want a **link to download/view**, not analysis of text.
- **summarize_to_page** / **generate_pdf**: They want a **deliverable artifact** (page/PDF) more than inline Q&A — use those when format is explicit.
- **coding**: They want to **change code** or **run the project**, not only read a doc (unless read-first is clearly secondary).

## Workflow hints
- `document_read`, `file_read`, `file_understand`; use `folder_list` / `file_find` when the path is fuzzy; `get_file_view_link` only if a view URL is needed alongside reading.
