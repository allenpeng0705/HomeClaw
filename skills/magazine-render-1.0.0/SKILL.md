---
name: magazine-render
description: |
  Generic magazine-style PDF renderer (VMPrint draft2final) for HomeClaw. Use when the user asks for a more beautiful / readable / magazine-like report layout (PDF).
  Accepts either Markdown (render-md) or structured JSON + template (render-json). Output is saved under the user's sandbox output folder and returned as a link.
  Supports named themes (e.g. dispatch-style masthead) and optional PNG preview generation (best-effort).
homepage: https://github.com/allenpeng0705/HomeClaw
trigger:
  patterns:
    - "magazine\\s*(pdf|style|layout)?"
    - "make\\s*(this|it)?\\s*(pretty|beautiful|readable|nic(er|ely)|well\\s*formatted)"
    - "format\\s*(this|it)?\\s*(nicely|beautifully)"
    - "export\\s*(this|it)?\\s*as\\s*pdf"
    - "render\\s*(this|it)?\\s*as\\s*pdf"
    - "杂志\\s*风格|杂志\\s*排版|排版\\s*更\\s*好看|导出\\s*pdf|生成\\s*pdf"
  instruction: |
    The user wants a prettier / more readable report output (PDF). Use the magazine-render skill to create a magazine-style PDF using VMPrint.

    You have two modes:

    1) Markdown → PDF (recommended, most reliable):
       - If you already have the report content in your context, convert it to a clean Markdown magazine layout (masthead, date, sections, short bullets, links).
       - Call:
         run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                 args=["render-md", "--title", "<TITLE>", "--theme", "dispatch|minimal", "--profile", "literature", "--md", "<MARKDOWN>", "--preview", "auto|none", "--out", "<FILENAME>.pdf"])
       - The script saves to the user's output folder and returns a link automatically.

    2) Structured JSON → template → PDF:
       - Use when you have structured data (e.g. RSS items list, weather JSON, stock portfolio JSON).
       - Call:
         run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                 args=["render-json", "--template", "daily_brief|weather|stock", "--theme", "dispatch|minimal", "--profile", "literature", "--json", "<JSON_TEXT>", "--preview", "auto|none", "--out", "<FILENAME>.pdf"])

    Output rules:
    - Always include a short 3–6 bullet “Top highlights” in chat.
    - Always keep links in the PDF (do not strip URLs).
    - If VMPrint/Node is missing, explain the actionable fix: install VMPrint via install.sh/install.ps1, ensure Node is on PATH, and build draft2final.
    - If preview image is requested but unavailable, still return the PDF (preview is best-effort).
---

# magazine-render-1.0.0

This is a reusable formatting skill: it turns Markdown or structured JSON into a **magazine-style PDF** using **VMPrint**.

## Scripts (run_skill)

| Action | Args |
|--------|------|
| Render Markdown to PDF | `["render-md", "--title", "My Report", "--theme", "dispatch", "--profile", "literature", "--md", "# ...", "--preview", "auto", "--out", "report.pdf"]` |
| Render JSON template to PDF | `["render-json", "--template", "daily_brief", "--theme", "dispatch", "--profile", "literature", "--json", "{...}", "--preview", "auto", "--out", "daily_brief.pdf"]` |

Notes:
- `--out` is a **filename**, saved under the user's output folder (sandbox). The tool returns a view link when configured.
- Prefer **Markdown mode** unless you already have clean structured JSON.
- Named themes: `dispatch` (masthead like a newspaper) or `minimal`.
- Preview image: `--preview auto` tries to generate a PNG thumbnail of the first page (macOS `qlmanage` or `pdftoppm` if installed). If it fails, you still get the PDF.

