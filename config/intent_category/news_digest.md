---
id: news_digest
display_name: News RSS and daily brief
enabled: true
priority: 57
classifier_description: "Headlines, RSS digest, daily or morning brief, 今日新闻, 简报 — curated news product, not a one-off arbitrary web search."

match_patterns:
  - 今日新闻简报
  - 每日简报
  - (?i)\b(daily\s+brief|morning\s+brief|rss\s+digest)\b

category_tools:
  tools:
  - run_skill
  - web_search
  - time
  skills:
  - daily-brief-1.0.0
  - magazine-render-1.0.0
---

## Description
The user wants **news as a bundle**: daily brief, morning paper, *今日新闻*, *头条*, RSS aggregation, **magazine-style** layout, “what happened in tech today” as a **digest**, not a single ad-hoc fact lookup (**search_web**). Often tied to **daily-brief** / similar skills.

## Positive examples
- “Give me today’s tech headlines.”
- “今日新闻简报（国内国际都要）”
- “Summarize my RSS feeds for the last 24 hours.”
- “Morning digest of world news.”
- “What’s new in AI this week?” (when framed as **headlines/overview**, not deep research)
- “给我一份伊美冲突的最新新闻简报。”
- “帮我整理今日国际新闻要点并按主题分组。”

## Negative boundaries
- **search_web**: **One specific question** (“when did X happen?”) or **deep dive** — not a digest framing.
- **stock_monitor**: **Tickers, quotes, portfolio** — financial data table; **market news** alone can be fuzzy — prefer **stock_monitor** when **symbols and prices** are central.
- **weather**: **Forecast** only — **weather** category.
- **general_chat**: Opinion on a news story **without** asking for a **brief/headlines** product.
- **get_file_link**: “发给我” with no explicit filename/path should not hijack digest queries.

## Workflow hints
- `run_skill(daily-brief)`; `magazine-render` when PDF/magazine output is configured; `web_search` / `time` as supplements.
