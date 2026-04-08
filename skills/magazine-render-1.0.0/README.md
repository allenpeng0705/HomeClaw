# magazine-render-1.0.0

Generic **VMPrint-powered document UI renderer** for HomeClaw outputs.

This skill is designed to be reusable across domains (daily brief, weather, stock monitor, etc.). Prefer AST-first generation. You provide either:

- **Structured JSON** (preferred, with built-in template such as `daily_brief`, `weather`, `stock`, `web_search` for Tavily-style `results`), or
- **AST JSON 1.1** directly, or
- **Markdown** (fallback path),

and it produces one of:

- **PDF** (download/print),
- **layout JSON scene graph** (advanced),
- **browser preview HTML** (channel-friendly link target),

using **VMPrint** (`draft2final` + VMPrint CLI).

Default policy for long/formatted output:
- primary: `browser_preview_html`
- secondary: `pdf` only when explicitly requested

## Natural language (what you can say)

You typically use this after you already have some content (daily brief, weather report, stock report, meeting notes) and you want a prettier output.

### English

- “Make this a **magazine-style PDF**.”
- “Format this nicely and **export as PDF**.”
- “Make it pretty and readable as a PDF.”
- “Use the **dispatch** theme and include a cover preview image.”
- “Generate a browser preview link for this daily brief.”

### Chinese

- “把这个做成 **杂志风格 PDF**。”
- “排版更好看，并 **导出 PDF**。”
- “用 **dispatch** 主题，顺便生成一张封面预览图。”
- “把这个生成可在浏览器打开的预览链接。”

## Requirements

- VMPrint installed and built under `tools/vmprint` (HomeClaw installers do this).
- Node.js on PATH for the Core process (so `node` can run the VMPrint CLI).

## Usage (CLI)

From repo root:

```bash
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-md --title "Daily Brief" --md "# Hello\n\nThis is a report." --out "daily_brief.pdf"
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-template-ast --template weather --title "Weather Brief" --json '{"location":"Beijing","now":{"condition":"Cloudy","temp":"18C"},"forecast":[{"day":"Fri","summary":"Cloudy","high":"21C","low":"14C"}]}' --output_format browser_preview_html --out "weather_brief.preview.html"
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-ast --ast '{"documentVersion":"1.1","layout":{"pageSize":"LETTER","margins":{"top":72,"right":72,"bottom":72,"left":72},"fontFamily":"Arimo","fontSize":12,"lineHeight":1.4},"styles":{"h1":{"fontSize":24,"fontWeight":"bold"}},"elements":[{"type":"h1","content":"Hello AST"}]}' --output_format browser_preview_html --out "daily_brief.preview.html"
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-daily-brief-ast --json '{"as_of":"2026-03-26","items":[{"title":"Headline","source":"RSS","link":"https://example.com"}]}' --output_format layout_json --out "daily_brief.layout.json"
python3 skills/magazine-render-1.0.0/scripts/render_magazine.py render-template-ast --template web_search --title "Search" --json '{"query":"example","results":[{"title":"Hit","url":"https://a","content":"Snippet text"}]}' --output_format browser_preview_html --out "search.preview.html"
# With browser preview, a sibling search.layout.json is written by default (--no-also-layout-json to skip).
```

The HomeClaw `run_skill` path is described in `SKILL.md`.

