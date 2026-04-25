---
name: magazine-render
description: |
  Generic VMPrint renderer for HomeClaw document UI runtime. Use when the user asks for a more beautiful / readable / magazine-like report layout.
  Supports AST-first rendering (render-template-ast / render-ast) plus Markdown fallback. Prefer browser preview HTML for long/formatted responses; use PDF when explicitly requested.
  Output is saved under the user's sandbox output folder and returned as a link for Companion and all channels.
homepage: https://github.com/allenpeng0705/HomeClaw
trigger:
  patterns:
    - "magazine\\s*(pdf|style|layout|render)"
    - "(make|get|give).*(magazine|broadsheet|editorial).*(pdf|output|layout)"
    - "export.*magazine.*pdf"
    - "排版.*杂志|杂志.*PDF|杂志.*风格.*导出"
  instruction: |
    The user wants a prettier / more readable report output. Use AST-first VMPrint rendering for better UI control.

    Daily brief / news digest with pretty-layout intent — two steps:
    1) Fetch digest (optionally narrow with --feed NAME to select specific sources, --filter KEYWORD, --lang en|cn|all):
       run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch-vmprint", "--max", "20", "--lang", "all"])
       Example with specific feed: args=["fetch-vmprint", "--feed", "36", "--max", "15", "--lang", "all"]
    2) Convert digest JSON -> VMPrint artifact:
       run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-daily-brief-ast", "--title", "Daily Brief", "--theme", "dispatch", "--json", "<DAILY_BRIEF_JSON>", "--output_format", "browser_preview_html", "--out", "daily_brief.preview.html"])
    Return highlights + preview link; do not stop at raw Markdown.

    You have four modes:

    1) Template JSON → AST → artifact (recommended):
       - If you have structured data (daily_brief/weather/stock/web_search), use AST templates first. `web_search` expects Tavily-like JSON: `query` + `results[]` with `title`, `url`, `content` or `snippet`.
       - Call:
         run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-template-ast", "--template", "daily_brief|weather|stock|web_search", "--title", "<TITLE>", "--theme", "dispatch|minimal", "--json", "<JSON_TEXT>", "--output_format", "browser_preview_html|pdf|layout_json", "--out", "<FILENAME>"])
       - Browser preview also writes sibling `<stem>.layout.json` by default (flat scene graph for CI/tools); add `--no-also-layout-json` in args to skip.

    2) AST JSON 1.1 → artifact:
       - Use when upstream already has VMPrint AST and you want deterministic layout runtime output.
       - Call:
         run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-ast", "--ast", "<AST_JSON>", "--output_format", "browser_preview_html|pdf|layout_json", "--out", "<FILENAME>"])

    3) Daily brief data JSON -> dedicated AST template -> artifact:
       - Use for channel-friendly browser preview + optional PDF from one layout model.
       - Call:
         run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-daily-brief-ast", "--title", "<TITLE>", "--theme", "dispatch|minimal", "--json", "<DAILY_BRIEF_JSON>", "--output_format", "browser_preview_html|pdf|layout_json", "--out", "<FILENAME>"])

    4) Markdown fallback:
       - Use only when structured JSON/AST is unavailable.
       - Call:
         run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-md", "--title", "<TITLE>", "--theme", "dispatch|minimal", "--profile", "literature", "--md", "<MARKDOWN>", "--preview", "auto|none", "--out", "<FILENAME>.pdf"])

    Output rules:
    - Always include a short 3–6 bullet “Top highlights” in chat.
    - For long/formatted responses, prefer `browser_preview_html` as primary link.
    - Generate PDF only when user asks for print/download/export.
    - If VMPrint/Node is missing, explain the actionable fix: install VMPrint via install.sh/install.ps1, ensure Node is on PATH, and build draft2final + vmprint cli.
    - If preview image is requested but unavailable, still return the PDF (preview is best-effort).
---

# magazine-render-1.0.0

This is a reusable formatting skill for **AST-first VMPrint UI output**. It can render browser previews, PDFs, and layout JSON from structured JSON or AST.

## Scripts (run_skill)

| Action | Args |
|--------|------|
| Render template JSON -> AST artifact | `["render-template-ast", "--template", "daily_brief|weather|stock|web_search", "--title", "Report", "--theme", "dispatch", "--json", "{...}", "--output_format", "browser_preview_html|pdf|layout_json", "--out", "report.preview.html"]` |
| Render AST JSON 1.1 | `["render-ast", "--ast", "{...}", "--output_format", "pdf|layout_json|browser_preview_html", "--out", "brief.preview.html"]` |
| Daily brief JSON -> AST template | `["render-daily-brief-ast", "--title", "Daily Brief", "--theme", "dispatch", "--json", "{...}", "--output_format", "pdf|layout_json|browser_preview_html", "--out", "brief.layout.json"]` |
| Markdown fallback to PDF | `["render-md", "--title", "My Report", "--theme", "dispatch", "--profile", "literature", "--md", "# ...", "--preview", "auto", "--out", "report.pdf"]` |

Notes:
- `--out` is a **filename**, saved under the user's output folder (sandbox). The tool returns a view link when configured.
- Prefer **AST-first template mode** when structured JSON is available.
- Named themes: `dispatch` (masthead like a newspaper) or `minimal`.
- Preview image: `--preview auto` tries to generate a PNG thumbnail of the first page (macOS `qlmanage` or `pdftoppm` if installed). If it fails, you still get the PDF.
- For channels + Companion, prefer `browser_preview_html` output and share the returned file link.

