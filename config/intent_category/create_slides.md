---
id: create_slides
display_name: Create slides or presentation
enabled: true
priority: 52
classifier_description: "Build a slide deck or presentation from notes or a topic — PPT, generic slides, pitch deck, 演示文稿 — when HTML-only is not explicitly required."

category_tools:
  profile: minimal
  skills:
  - html-slides-1.0.0
  - ppt-generation-1.0.0
---

## Description
The user wants **slides in the broad sense**: PowerPoint-style, pitch deck, training deck, *生成PPT*, *做一套幻灯片*, “turn this outline into slides” **without** insisting on **HTML/Reveal/web-only** output. Planner or skills may choose **html-slides** or **ppt-generation** depending on workspace and phrasing.

## Positive examples
- “Turn this outline into a presentation.”
- “Make slides from the meeting notes in `notes.md`.”
- “生成十页 PPT 介绍 Q3 结果”
- “Create a pitch deck about our product.”
- “Speaker notes + bullets for each slide.”
- “把这份方案做成路演幻灯片。”
- “给我一个 8 页的投资人演示文稿结构。”

## Negative boundaries
- **create_html_slides**: User **explicitly** wants **HTML**, **Reveal.js**, **网页幻灯片**, or **web-based** deck only.
- **read_document**: Only **reading** source material — no slide output.
- **summarize_to_page**: **Single summary page**, not multi-slide structure.
- **generate_pdf**: **Linear PDF report** — not slide format (unless they say “slides as PDF” — then **create_slides** or **generate_pdf** by dominant ask).

## Workflow hints
- Skills `html-slides`, `ppt-generation`; planner picks path from user wording and available tools.
