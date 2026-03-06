---
name: summarize
description: Summarize URLs or files with the summarize CLI (web, PDFs, images, audio, YouTube).
homepage: https://summarize.sh
trigger:
  patterns: ["summarize|summary|summarise|summarize\\s+(this\\s+)?(url|link|page|article|file)|总结|摘要"]
  instruction: "The user asked to summarize a URL, link, page, or file. Use run_skill(skill_name='summarize-1.0.0', ...) with the URL or path in args, or use the skill's instructions (summarize CLI). When the summary is long and in Markdown, call markdown_to_pdf if available and return the PDF link so the user gets a downloadable report without having to ask."
---

# Summarize

Fast CLI to summarize URLs, local files, and YouTube links. On HomeClaw the model runs this via terminal; ensure the `summarize` binary is on PATH (install per your platform).

## Quick start

```bash
summarize "https://example.com" --model <model>
summarize "/path/to/file.pdf" --model <model>
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto
```

## Model and API key (use HomeClaw mix mode)

Use the **same model and API key** as HomeClaw Core so behavior matches your main LLM:

- **Config:** `config/core.yml` — `main_llm_local`, `main_llm_cloud`, and each cloud model’s `api_key_name` (e.g. `GEMINI_API_KEY`).
- **Key:** Set that env var where Core (and the terminal) run, e.g. `GEMINI_API_KEY` or `OPENAI_API_KEY`. No need to set multiple provider keys unless you use multiple cloud models.
- **Model:** Pass the same LiteLLM-style model id to `summarize --model <id>`, e.g. `google/gemini-2.5-flash` or `openai/gpt-4o`, matching Core’s `main_llm_cloud` / `main_llm_local`.

Example (Core using Gemini 2.5 Flash):

```bash
# Key already set for Core
summarize "https://example.com" --model google/gemini-2.5-flash
```

## Useful flags

- `--length short|medium|long|xl|xxl|<chars>`
- `--max-output-tokens <count>`
- `--extract-only` (URLs only)
- `--json` (machine readable)
- `--firecrawl auto|off|always` (fallback extraction)
- `--youtube auto` (Apify fallback if `APIFY_API_TOKEN` set)

## Config

Optional config file: `~/.summarize/config.json` — set `model` to the same id you use with Core (e.g. `google/gemini-2.5-flash`).

Optional services:
- `FIRECRAWL_API_KEY` for blocked sites
- `APIFY_API_TOKEN` for YouTube fallback

## Output

- **Response:** Return the summary as **plain text** or **Markdown** in your reply so the user sees it in chat.
- **Saving to file:** If the user wants the summary saved, run `summarize` (via terminal/exec) and then use **file_write** with path **output/summary_<slug>.md** (e.g. `output/summary_article-name.md`). That path goes to the user's private output folder (`workspace/{user_id}/output/` or `companion/output/`). You can paste the summarize CLI stdout into the file, or run summarize and capture output then write it. Prefer returning the summary in your reply; add "Also saved to output/…" or a link when you save. Response can be plain text, Markdown, or text with a link to the saved file.

## Long summaries → PDF (automatic)

When the summary is **long** (multiple sections, several paragraphs, or clearly structured in Markdown) and the user did not ask only for a brief reply:

1. **Always** return the summary in your reply so the user sees it in chat.
2. **If the tool `markdown_to_pdf` is available:** Call it with the Markdown content and an output path such as **output/summary_&lt;descriptive_slug&gt;.pdf** (e.g. `output/summary_report.pdf`). Then in your reply **include the PDF file link** (e.g. "PDF saved: [open PDF](link)") so the user can open or download it. You do not need to ask the user first—producing a PDF for long summaries is part of this skill so they get both the inline summary and a downloadable PDF.
3. If `markdown_to_pdf` is not available, you may still save the long summary as Markdown with **file_write** to **output/summary_&lt;slug&gt;.md** and return that link.

The user does not have to say "PDF" or "markdown"; they only ask to summarize a document or long text. When the result is long, automatically offer the PDF link when the tool is available.
