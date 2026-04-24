---
name: daily-brief
description: |
  RSS-based "Daily Brief" / news headline digest: aggregate free public feeds (English + Chinese), optional keyword filter. AST-first VMPrint output by default (browser preview link), Markdown only on explicit request. No API keys. Edit config/feeds.yaml to add or change sources.
retry_safe: true
homepage: https://github.com/allenpeng0705/HomeClaw
trigger:
  patterns:
    - "daily\\s*brief|morning\\s*report|RSS|新闻订阅|rss\\s*feed|headline\\s*digest|今日新闻|每日简报"
  instruction: |
    The user wants a news digest from RSS.

    Default behavior (AST-first VMPrint):
    1) Run daily-brief VMPrint path by default:
       run_skill(skill_name='daily-brief-1.0.0', script='fetch_rss.py', args=['fetch-vmprint', '--max', '25', '--lang', 'all'])
       - For Chinese-only use --lang cn; English-only use --lang en.
       - To narrow topics use --filter KEYWORD (matches title/summary).
       - For a one-line feed list use args=['list'].
    2) Reply with 3–6 highlight bullets + the returned preview link. Keep in-chat text concise; the link is the primary formatted view.

    VMPrint uses magazine-render skill if available; falls back to plain Markdown if not installed.
    Markdown/text-only fallback: use plain output only when user explicitly asks for no link/no HTML.

    PDF generation: only when user explicitly asks for download/print/export.
---

# Daily Brief (RSS news digest)

Aggregate **public RSS feeds** into one Markdown report. **No API keys**, no paid news APIs—only HTTP fetch of RSS URLs.

Human-oriented setup, CLI examples, cron examples, and real-life usage scenarios: **`README.md`** in this folder.

## Configure feeds

Edit **`config/feeds.yaml`** in this skill folder:

- **`lang`**: `en` or `cn` — selects feeds when using `--lang en|cn|all`.
- Add or remove **`name`** + **`url`** pairs. Some sites change feed URLs; update if a feed breaks.

Default mix includes **English** (e.g. Hacker News, Ars Technica) and **Chinese** (Solidot, IT之家, 少数派, 36氪).

## Scripts (run_skill)

| Action | Args |
|--------|------|
| List configured feeds | `["list"]` |
| Fetch merged headlines (Markdown) | `["fetch", "--max", "30", "--lang", "all"]` |
| Fetch + VMPrint preview artifact (default) | `["fetch-vmprint", "--max", "20", "--lang", "all"]` |
| Chinese feeds only | `["fetch", "--max", "25", "--lang", "cn"]` |
| English feeds only | `["fetch", "--max", "25", "--lang", "en"]` |
| Keyword filter (title/summary) | `["fetch", "--max", "20", "--lang", "all", "--filter", "AI"]` |

Example:

```text
run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch", "--max", "25", "--lang", "cn"])
```

Output includes Markdown headlines plus a JSON block for tooling. Items are **interleaved across feeds** so one busy source does not fill the whole list.

## Scheduling (cron + optional LLM polish)

Use **`cron_schedule`** with `task_type="run_skill"` to run every morning. Optional **`post_process_prompt`** turns the raw list into a short “Morning Report” (pick top 5, group by theme).

Example (daily 08:00 server time; adjust cron for your timezone):

- `cron_expr`: `0 8 * * *`
- `task_type`: `run_skill`
- `skill_name`: `daily-brief-1.0.0`
- `script`: `fetch_rss.py`
- `args`: `["fetch", "--max", "25", "--lang", "all"]`
- `post_process_prompt` (optional): `Turn the following RSS digest into a concise Morning Report: 3–6 bullets, group by topic, keep links.`

Delivery uses **`deliver_to_user`** (Companion WebSocket + push + last channel) when the cron job runs.

## Limits

- **RSS only** — titles, links, and usually short descriptions. This is **not** full web search; use **`web_search`** or add APIs for that.
- **Site terms / rate limits** — avoid hammering feeds; keep `--max` reasonable.
- **Paywalls** — following links for full text may require **`fetch_url`** separately.
- **Network** — each feed fetch uses a timeout and a max response size; only `http`/`https` URLs are allowed. See **`README.md`** for robustness details.

## Dependencies

**`feedparser`** and **`PyYAML`** — install with `pip install -r requirements.txt` in this skill directory, or use the repo root `requirements.txt` for a full HomeClaw install.
