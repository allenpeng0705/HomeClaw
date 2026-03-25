# magazine-render-1.0.0

Generic **magazine-style PDF renderer** for HomeClaw outputs.

This skill is designed to be reusable across domains (daily brief, weather, stock monitor, etc.). You provide either:

- **Markdown** (a report / digest), or
- **Structured JSON** (then pick a built-in template such as `daily_brief`, `weather`, `stock`),

and it produces a **PDF** using **VMPrint** (draft2final).

## Natural language (what you can say)

You typically use this after you already have some content (daily brief, weather report, stock report, meeting notes) and you want a prettier output.

### English

- “Make this a **magazine-style PDF**.”
- “Format this nicely and **export as PDF**.”
- “Make it pretty and readable as a PDF.”
- “Use the **dispatch** theme and include a cover preview image.”

### Chinese

- “把这个做成 **杂志风格 PDF**。”
- “排版更好看，并 **导出 PDF**。”
- “用 **dispatch** 主题，顺便生成一张封面预览图。”

## Requirements

- VMPrint installed and built under `tools/vmprint` (HomeClaw installers do this).
- Node.js on PATH for the Core process (so `node` can run the VMPrint CLI).

## Usage (CLI)

From repo root:

```bash
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-md \
  --title "Daily Brief" \
  --md "# Hello\n\nThis is a report." \
  --out "daily_brief.pdf"
```

The HomeClaw `run_skill` path is described in `SKILL.md`.

