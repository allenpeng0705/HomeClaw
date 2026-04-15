---
id: create_html_slides
display_name: HTML / web slide deck
enabled: true
priority: 54
classifier_description: "Create an HTML or web-based slide deck (Reveal-style, single-page deck, 网页演示) — not generic PPT unless they also say HTML/web."

category_tools:
  tools:
  - document_read
  - run_skill
  - save_result_page
  - file_read
  - file_understand
  skills:
  - html-slides-1.0.0
---

## Description
The user wants **slides as web/HTML**: Reveal.js-style, static HTML deck, *网页幻灯片*, *用 html 做演示*, hosted page with slide sections. Often **document_read → run_skill(html-slides) → save_result_page**. Prefer this over **create_slides** when **HTML**, **web**, or **Reveal** is explicit.

## Positive examples
- “Convert this markdown to HTML slides.”
- “Make a Reveal.js deck from `docs/talk.md`.”
- “用 html-slides 做一套可在浏览器全屏播放的幻灯片”
- “Web-based presentation — one `index.html` I can open locally.”
- “Speaker view not needed — simple web deck.”
- “我只要网页幻灯片，不要 PPT 文件。”
- “做一个可以浏览器打开的 reveal 风格演示稿。”

## Negative boundaries
- **create_slides**: **PPT / PowerPoint / generic slides** with **no** HTML emphasis.
- **generate_pdf**: **PDF** export as the main deliverable.
- **summarize_to_page**: **One long page**, not slide sections/navigation.
- **read_document**: No **slide artifact** requested.

## Workflow hints
- `document_read` → `run_skill(html-slides)` → `save_result_page` when a hosted link is needed.
