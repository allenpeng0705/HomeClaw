---
id: generate_pdf
display_name: Generate or export PDF
enabled: true
priority: 53
classifier_description: "Export or generate a PDF from markdown or a document — print-ready file, report as PDF, 导出pdf, printable version."

category_tools:
  tools:
  - document_read
  - markdown_to_pdf
---

## Description
The user wants **PDF as the output format**: convert markdown or an existing doc to PDF, “print this to PDF”, *生成pdf*, *打印版*, *导出*, formal report file. Usually **read source → render markdown → `markdown_to_pdf`** (or equivalent). If they only want a **web page** without PDF, use **summarize_to_page** or **read_document**.

## Positive examples
- “Export `documents/report.md` to `output/report.pdf`.”
- “Turn the summary into a PDF I can email.”
- “把这份笔记导出成 pdf”
- “Give me a printable A4 version of this doc.”
- “Combine these three chapters into one PDF.”
- “把 `meeting_notes.md` 转成 PDF 发给我。”
- “请生成一份可打印的 PDF 周报。”

## Negative boundaries
- **summarize_to_page**: **Viewable page / link**, no insistence on **.pdf** or printing.
- **read_document**: **Discuss** content in chat — no export artifact requested.
- **create_slides**: **Slide deck** — prefer when **slides** are the dominant format (unless they explicitly want “slides as PDF”).
- **send_email**: They want to **email** something — may chain; **generate_pdf** when **PDF creation** is the explicit first step.

## Workflow hints
- `document_read` → generate or normalize markdown → `markdown_to_pdf` with destination path.
