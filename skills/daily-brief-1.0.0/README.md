# daily-brief-1.0.0

RSS-based **Daily Brief** for HomeClaw: aggregate public feeds (English + Chinese), optional keyword filter. **AST-first VMPrint preview output by default** (Markdown only on explicit request). **No API keys**—only HTTP requests to RSS URLs.

Full agent-oriented instructions are in **`SKILL.md`**. This README is for humans: setup, commands, scheduling, and real-life usage.

## Natural language (what you can say)

### English

- “Daily brief, 25 items, all sources.”
- “Morning report for Chinese tech news.”
- “RSS digest filtered to AI.”
- “List the configured daily brief feeds.”
- “Daily brief, make it **magazine-style**, and give me a browser preview link.”
- “Daily brief, and export a **PDF** for printing.”

### Chinese

- “今日新闻 / 每日简报（25条，中文）”
- “RSS 新闻订阅，筛选 AI 相关”
- “列出 daily brief 的 RSS 源”
- “把今日新闻做成 **杂志风格**，给我浏览器预览链接”
- “把今日新闻导出成 **PDF**（用于下载/打印）”

## Requirements

- **Python 3.10+** (recommended; script uses `from __future__ import annotations` and stdlib `datetime.timezone` patterns).
- **`feedparser`** — parse RSS/Atom feeds.
- **`PyYAML`** — read `config/feeds.yaml`.
- Network access from the machine running Core (or wherever you run the script) to fetch feeds.

Install **only this skill’s dependencies** (from the skill folder):

```bash
cd skills/daily-brief-1.0.0
pip install -r requirements.txt
```

If you already installed **HomeClaw from the repo root**, root `requirements.txt` already pulls in `feedparser` and `PyYAML`, so no extra step is needed.

```bash
# from repo root (full project)
pip install -r requirements.txt
```

## Configure feeds

Edit **`config/feeds.yaml`**:

- Each entry needs **`name`**, **`url`**, and **`lang`** (`en` or `cn`).
- Add or remove sources anytime; some sites change feed URLs.

Default feeds include English (e.g. Hacker News, Ars Technica) and Chinese (Solidot, IT之家, 少数派, 36氪).

## Commands

From the repo root (paths may vary):

```bash
# List configured feeds
python3 skills/daily-brief-1.0.0/scripts/fetch_rss.py list

# Fetch merged headlines (examples)
python3 skills/daily-brief-1.0.0/scripts/fetch_rss.py fetch --max 25 --lang all
python3 skills/daily-brief-1.0.0/scripts/fetch_rss.py fetch --max 20 --lang cn
python3 skills/daily-brief-1.0.0/scripts/fetch_rss.py fetch --max 20 --lang en
python3 skills/daily-brief-1.0.0/scripts/fetch_rss.py fetch --max 20 --lang all --filter AI
```

Via **`run_skill`** (from chat or tools):

```text
run_skill(skill_name="daily-brief-1.0.0", script="fetch_rss.py", args=["fetch", "--max", "25", "--lang", "cn"])
```

Output is Markdown plus a JSON block. Items are **interleaved across feeds** so one busy source does not dominate the list.

## VMPrint output default for Daily Brief

Daily brief uses VMPrint AST path by default and returns:

- **`browser_preview_html`** (best reading experience in channels/Companion)

Generate **PDF** only when users explicitly ask for download/print/export.

## Scheduling (cron)

Use HomeClaw’s **`cron_schedule`** with `task_type="run_skill"`:

- **`cron_expr`**: e.g. `0 8 * * *` for 08:00 daily (server time—adjust for your timezone).
- **`skill_name`**: `daily-brief-1.0.0`
- **`script`**: `fetch_rss.py`
- **`args`**: e.g. `["fetch", "--max", "25", "--lang", "all"]`
- Optional **`post_process_prompt`**: ask the model to turn the raw digest into a short “Morning Report” (bullets, grouped by topic).

Delivery uses Core’s normal path (**Companion WebSocket**, push notification, **last channel**), depending on how your instance is set up. See **`docs_design/CorePushToChannelsAndCompanion.md`**.

## Limits

- **RSS only** (titles, links, short descriptions)—not full article text or full web search.
- **Keyword “search”** is `--filter` on title/summary text only.
- Respect site terms and rate limits; keep `--max` reasonable.

## Robustness (implementation notes)

The script is designed to fail safely:

- **HTTP(S) only** for feed URLs and for item links shown in output (filters out `file://`, `localhost`, and obvious local targets to reduce SSRF mistakes in `feeds.yaml`).
- **Per-feed network timeout** (default 25s) and **response size cap** (5 MiB per feed) so a slow or huge feed cannot hang or exhaust memory.
- **Real User-Agent** string so fewer feeds block the default client.
- **YAML errors** are reported; invalid `feeds.yaml` does not crash Core— the skill exits with a clear message.
- **Partial success**: if some feeds fail, others still contribute; warnings are listed in the Markdown and JSON output.
- **`--max`** is capped (100) to keep chat payloads bounded.
- **`--lang`** uses only matching feeds when computing per-feed limits (fixed logic vs counting all feeds).
- **Titles/summaries** are normalized to a single line for stable Markdown and logging.

---

## Real-life usage examples (via HomeClaw)

### 1. Quick “what’s new” in chat

Ask in **WebChat, Telegram, Discord, or Companion**:

- *“Run the daily brief for Chinese tech news, max 15 items.”*  
  → `args`: `["fetch", "--max", "15", "--lang", "cn"]`

- *“Morning headlines in English only, 20 items.”*  
  → `["fetch", "--max", "20", "--lang", "en"]`

- *“RSS digest filtered to AI.”*  
  → `["fetch", "--max", "20", "--lang", "all", "--filter", "AI"]`

You get the digest in the same conversation thread.

### 2. Before work: global + China snapshot

Ask for a **single combined digest**, then a short summary for standup:

- *“Daily brief: 25 items, all languages, then summarize into 5 bullets for my standup.”*

Flow: **`run_skill`** → raw output → model summarizes (or you read the list as-is).

### 3. Scheduled “Morning Report”

Set **cron** (e.g. weekdays 08:00) to run **`fetch`**, optionally with **`post_process_prompt`** so the output is a short Markdown report instead of a raw list—useful for **commute / breakfast** reading without manual triggers.

### 4. Niche tracking with `--filter`

Examples:

- English feeds + `--filter security`
- Chinese feeds + `--filter` keywords you care about (e.g. a company or product name)

Useful when you want **theme-focused** headlines without a paid news API.

### 5. Ops: verify feeds

- *“List the RSS feeds for daily-brief.”*  
  → `args`: `["list"]`  
  Confirms **`config/feeds.yaml`** before you rely on automation.

### 6. Deep dive after the digest

After you see the list:

- *“Summarize the third link with fetch_url.”*

RSS gives **breadth**; **`fetch_url`** (or other tools) gives **depth** on one article.

### 7. Same Core, different people

Each user can use different schedules, `--lang`, and `--filter` values; cron delivery can be tied to **user context** so Companion and last-channel behavior stay per user.

---

## See also

- **`SKILL.md`** — trigger patterns, **`cron_schedule`** field names, and agent instructions
- **`skills/README.md`** — bundled skills index
- **`docs_design/CorePushToChannelsAndCompanion.md`** — how proactive messages reach Companion and channels
