---
name: vmprint-ast-layout-1.0.0
description: |
  Author or debug VMPrint JSON AST 1.1 (layouts, tables, zone-map, strip, scripting). The full practitioner guide
  ships with VMPrint at tools/vmprint/documents/SKILL.md — read that file on demand; do not invent AST keys.
homepage: https://github.com/cosmiciron/vmprint
trigger:
  patterns:
    - "vmprint.*ast|documentinput|documentVersion|zone-map|stripLayout|emit-layout|layout_json"
    - "VMPrint.*(table|footer|header|story|drop.?cap|column.?span)"
  instruction: |
    When the user needs custom VMPrint layout or AST fixes, the canonical reference is the bundled file
    tools/vmprint/documents/SKILL.md (same content as upstream vmprint documents/SKILL.md). Use document_read or
    file_read on that path from the project/repo root (or the path under your configured file_read_base if VMPrint
    lives there). Then use vmprint_render (output_format ast_json/layout_json/browser_preview_html) or
    magazine-render render-ast / render-template-ast. Never guess keys — the SKILL lists exact interfaces and common pitfalls.
---

# VMPrint AST layout (pointer skill)

This skill has **no script**. It tells you where the real spec lives.

## Canonical doc (read on demand)

**Path (typical clone):** `tools/vmprint/documents/SKILL.md`

That file is **~1300 lines** (AST 1.1, geometry, styles, scripting, pitfalls). HomeClaw does **not** inject it into every prompt — load it with **document_read** / **file_read** when you are authoring or debugging AST.

## HomeClaw tools to use after reading

| Goal | Tool / skill |
|------|----------------|
| Markdown → PDF / preview | `markdown_to_pdf`, `vmprint_render` |
| Structured JSON → AST → artifact | `run_skill` → `magazine-render-1.0.0` → `render-template-ast` / `render-daily-brief-ast` / `web_search` template |
| Raw AST 1.1 → PDF / layout / preview | `vmprint_render` or `render-ast` in magazine-render |
| Policy (when to use VMPrint in chat) | `docs/response-output-policy.md` |

## Quick reminders (not a substitute for the full SKILL)

- `documentVersion` must be `"1.1"`.
- Prefer templates and validators in **magazine-render** over huge free-form AST from the model.
- Root may include scripting keys: `methods`, `scriptVars`, `onBeforeLayout`, `onAfterSettle` — see the bundled SKILL for syntax.
