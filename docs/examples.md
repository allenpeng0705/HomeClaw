# Examples

Copy-paste scenarios to learn HomeClaw quickly.

## Example 1: Start Core + WebChat

```bash
python -m main start
python -m channels.run webchat
```

## Example 2: Local + cloud mix mode

In `config/llm.yml`:

```yaml
main_llm_mode: mix
main_llm_local: local_models/your_local_id
main_llm_cloud: cloud_models/your_cloud_id
```

Ask normal questions; HomeClaw routes local/cloud automatically.

## Example 3: Generate a better PDF (VMPrint)

Use tool call style:

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Report\n\nYour markdown content...",
    "path": "output/report.pdf",
    "output_format": "pdf",
    "vmprint_profile": "academic"
  }
}
```

Profiles:

- `academic`
- `manuscript`
- `screenplay`
- `literature`

Optional:

- `vmprint_style`

## Example 4: Export AST JSON (for advanced workflows)

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Draft\n\nContent...",
    "path": "output/draft.ast.json",
    "output_format": "ast_json",
    "vmprint_profile": "literature"
  }
}
```

## Example 4a: Export layout JSON scene graph

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Daily Brief\n\n- Headline 1\n- Headline 2",
    "path": "output/daily_brief.layout.json",
    "output_format": "layout_json",
    "vmprint_profile": "literature"
  }
}
```

## Example 4b: Browser preview artifact for channels/Companion

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Daily Brief\n\n## Top stories\n\n- Story A\n- Story B",
    "path": "output/daily_brief.preview.html",
    "output_format": "browser_preview_html",
    "vmprint_profile": "literature"
  }
}
```

Return the file link from `/files/out` so users can open it in browser from any channel or Companion.

## Example 4c: Daily brief uses browser preview by default

```json
{
  "tool": "run_skill",
  "arguments": {
    "skill_name": "magazine-render-1.0.0",
    "script": "render_magazine.py",
    "args": [
      "render-daily-brief-ast",
      "--title",
      "Daily Brief",
      "--theme",
      "dispatch",
      "--json",
      "{\"as_of\":\"2026-03-26\",\"items\":[{\"title\":\"Headline\",\"source\":\"RSS\",\"link\":\"https://example.com\"}]}",
      "--output_format",
      "browser_preview_html",
      "--out",
      "daily_brief.preview.html"
    ]
  }
}
```

## Example 4d: Magazine-style PDF for any content (skill)

If you want a more **beautiful / readable** output (magazine-style PDF) for any report-like content, use the `magazine-render-1.0.0` skill.

Render **Markdown** directly:

```json
{
  "tool": "run_skill",
  "arguments": {
    "skill_name": "magazine-render-1.0.0",
    "script": "render_magazine.py",
    "args": [
      "render-md",
      "--title",
      "Morning Brief",
      "--theme",
      "dispatch",
      "--profile",
      "literature",
      "--md",
      "# Morning Brief\n\n## Highlights\n\n- Item 1\n- Item 2\n\n## Links\n\n- [Example](https://example.com)\n",
      "--preview",
      "auto",
      "--out",
      "morning_brief.pdf"
    ]
  }
}
```

Or render a **structured JSON** payload via a built-in template (`daily_brief`, `weather`, `stock`):

```json
{
  "tool": "run_skill",
  "arguments": {
    "skill_name": "magazine-render-1.0.0",
    "script": "render_magazine.py",
    "args": [
      "render-json",
      "--template",
      "daily_brief",
      "--theme",
      "dispatch",
      "--profile",
      "literature",
      "--json",
      "{\"as_of\":\"2026-03-25\",\"items\":[{\"title\":\"Headline\",\"link\":\"https://example.com\",\"source\":\"RSS\"}]}",
      "--preview",
      "auto",
      "--out",
      "daily_brief.pdf"
    ]
  }
}
```

## Example 5: Federation basics

1. Set identity in `config/instance_identity.yml`
2. Add peers in `config/peers.yml`
3. In `config/core.yml`, enable federation:

```yaml
federation_enabled: true
peer_call_enabled: false
```

Use Companion for remote-friend messaging across instances.

## Example 6: Troubleshooting commands

```bash
python -m main doctor
python -m main portal
```

In Portal Guide, run VMPrint smoke test for PDF pipeline checks.

## Operator quick reference (VMPrint AST-first)

Use this when deciding output mode quickly:

- Structured JSON (`daily_brief|weather|stock`) -> `run_skill` `render-template-ast` -> `browser_preview_html` (default)
- Daily brief JSON -> `run_skill` `render-daily-brief-ast` -> `browser_preview_html` (default)
- Existing AST JSON 1.1 -> `run_skill` `render-ast` -> `browser_preview_html` (default)
- Markdown only -> `vmprint_render` -> `browser_preview_html` (fallback)
- User asks print/download/export -> use `pdf`
- Layout debug/QA -> use `layout_json`

Minimal copy-paste snippets:

```json
{
  "tool": "run_skill",
  "arguments": {
    "skill_name": "magazine-render-1.0.0",
    "script": "render_magazine.py",
    "args": ["render-template-ast", "--template", "stock", "--title", "Stock Brief", "--theme", "dispatch", "--json", "{\"items\":[{\"symbol\":\"NVDA\",\"name\":\"NVIDIA\",\"price\":\"100\",\"change_pct\":\"+1.2%\"}]}", "--output_format", "browser_preview_html", "--out", "stock_brief.preview.html"]
  }
}
```

```json
{
  "tool": "vmprint_render",
  "arguments": {
    "content": "# Long summary\n\n- item 1\n- item 2",
    "path": "output/summary.preview.html",
    "output_format": "browser_preview_html",
    "vmprint_profile": "literature"
  }
}
```
