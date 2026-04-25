---
name: ppt-generation
description: "Create PowerPoint (.pptx) from outline, source text, documents, or structured slides. Call run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=[...]). Output is saved to the user's private output folder and Core appends the open link. For 乔布斯-style single HTML use skill html-slides-1.0.0."
keywords: "ppt powerpoint presentation 演示 幻灯片 生成 PPT"
trigger:
  patterns:
    - "生成.*PPT|做个PPT|做.*PPT"
    - "create.*ppt|make.*presentation|\\.pptx"
    - "做.*(幻灯片|PPT)"
    - "powerpoint"
  instruction: >
    The user asked to create a PPT or PowerPoint. Use run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=['--capability', '<outline|source|presentation|documents>', ...]).
    Choose capability by content: outline (markdown ## / -), source (raw text or JSON), presentation (main_title + slides JSON), documents (paths or document_contents).
    Prefer --slides-file (path to JSON file) over passing raw JSON in --slides when the JSON is large, to avoid shell-escaping issues.
    Use --dry-run to preview slides without writing a file.
    Include the link Core returns in your reply.
---

# PPT Generation (PowerPoint .pptx)

Generate **.pptx** files by calling **run_skill** with script `create_pptx.py`. Output is saved to the user's (or companion's) private output folder; the script prints JSON and **Core appends the open link** — include that link in your reply.

For **乔布斯-style / 极简 / 竖屏 / single-page HTML** slides, use skill **html-slides-1.0.0** instead.

## run_skill usage

```text
run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=[...])
```

**args** must include `--capability` and the parameters for that capability (see below).

## When to use which capability

| User has / asks for | --capability | Main args |
|---------------------|--------------|-----------|
| Markdown outline (## titles, - bullets) | `outline` | `--outline "## Title\n- Point"` or `--outline-file <path>` |
| Raw text, web search result, or pasted content | `source` | `--source "<text or JSON>"` or `--source-file <path>` |
| Already have title + slides (e.g. from your parsing) | `presentation` | `--main_title "..."` `--subtitle "..."` `--slides '[{"title":"A","bullets":["b"]}]'` or `--slides-file <path>` |
| One or more documents (paths or pre-read content) | `documents` | `--document_paths '["path.md"]'` and/or `--document_contents '[{"title":"A","content":"..."}]'` |

Common optional: `--output_filename report.pptx`, `--language en`, `--dry-run`.

## Examples

**From outline:**
```text
args: ["--capability", "outline", "--outline", "## Intro\n- Point A\n- Point B\n## Conclusion\n- Summary"]
```

**From raw source (e.g. web search or pasted text):**
```text
args: ["--capability", "source", "--source", "<paste the text or JSON array of {title, content}>"]
```

**From structured slides (inline JSON — for small arrays):**
```text
args: ["--capability", "presentation", "--main_title", "Q4 Report", "--subtitle", "Summary", "--slides", "[{\"title\":\"Sales\",\"bullets\":[\"Item 1\",\"Item 2\"]}]"]
```

**From structured slides (file — preferred for large JSON):**
```text
args: ["--capability", "presentation", "--main_title", "Q4 Report", "--subtitle", "Summary", "--slides-file", "/path/to/slides.json"]
```

**Preview / dry-run (no file written):**
```text
args: ["--capability", "presentation", "--main_title", "Q4 Report", "--slides-file", "/path/to/slides.json", "--dry-run"]
```

**From documents (paths relative to project/workspace):**
```text
args: ["--capability", "documents", "--document_paths", "[\"report.md\", \"summary.txt\"]"]
```
Or pass content you already read: `--document_contents '[{"title":"Doc 1","content":"..."}]'`

## Output

The script prints JSON with `success`, `path`, `message`, and when run via Core `output_rel_path`. Core appends the open link to the tool result. Tell the user the presentation was created and give them the link.

On `--dry-run`, `success` is `true` and `path`/`output_rel_path` are absent — the model should describe what would be created without claiming a file was saved.

## Language / font support

`--language zh` uses system CJK fonts for better Chinese rendering. Default is `en`.

## Do not

- Use this skill for HTML/乔布斯-style slides (use **html-slides-1.0.0**).
- Claim the file was created without calling run_skill; only the tool result contains the real path/link.
- Pass large JSON inline in `--slides`; use `--slides-file` instead to avoid shell-escaping errors.

## Dependencies

Install in the same Python used by Core / run_skill:

```bash
pip install python-pptx
```

Or from the skill folder: `pip install -r scripts/requirements.txt` if present.
