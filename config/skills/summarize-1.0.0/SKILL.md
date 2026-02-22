---
name: summarize
description: Summarize URLs or files with the summarize CLI (web, PDFs, images, audio, YouTube).
homepage: https://summarize.sh
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
