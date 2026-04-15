---
id: summarize_to_page
display_name: Summarize to a viewable page
enabled: true
priority: 53
classifier_description: "Produce a summary as a saved, viewable page or hosted link (markdown/HTML result) — not necessarily PDF and not only inline chat text."

match_patterns:
  - (?i)summarize\s+documents?/
  - 总结\s*documents?/.*(md|markdown)

category_tools:
  tools:
  - document_read
  - save_result_page
---

## Description
The user wants a **digest of source material** delivered as a **persistent page or link** they can open later: *summary page*, *一页总结*, *save as result page*, executive brief in **save_result_page** form. Distinct from **chat-only** summary (**read_document** when they didn’t ask for a saved artifact) and from **PDF** (**generate_pdf**).

## Positive examples
- “Summarize `documents/long.md` and give me a page I can share.”
- “Condense the meeting notes into a short report page with headings.”
- “总结到一页里，给我链接”
- “Turn this thread into a one-pager on the result page.”
- “Executive summary — save it so I can open it in the browser.”
- “把这份调研压缩成一页网页摘要并给链接。”
- “请生成一个可分享的总结页面，不要 PDF。”

## Negative boundaries
- **generate_pdf**: User **explicitly** wants **PDF** export or print pipeline.
- **read_document**: They want **inline Q&A** or bullets **in chat** without asking for a **saved/hosted** page.
- **search_web**: Source material is the **web** — not a named local doc path.
- **create_slides**: They want **slide structure** (multiple slides), not a single scrollable page.

## Workflow hints
- Often `document_read` → compose markdown → `save_result_page` with the summary body.
