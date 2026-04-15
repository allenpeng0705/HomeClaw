---
id: stock_monitor
display_name: Stocks and watchlist
enabled: true
priority: 58
classifier_description: "Stock quotes, watchlist, portfolio, 自选股, 持仓, A股港股美股 tickers — market data and stock-monitor skill, not general headline news alone."

match_patterns:
  - (?i)\bportfolio\b
  - (?i)\bwatchlist\b
  - 自选股
  - 持仓
  - 股票行情

category_tools:
  tools:
  - run_skill
  - web_search
  - time
  skills:
  - stock-monitor-1.0.0
  - magazine-render-1.0.0
---

## Description
The user wants **markets data**: live or latest **quotes**, **watchlist** table, **portfolio** P&L, **自选股**, **持仓**, indices, “how is NVDA”, **ticker** lookups. The **stock-monitor** path is primary. **General news** without a **price/position** focus belongs in **news_digest** or **search_web**.

## Positive examples
- “What’s on my watchlist at close?”
- “AAPL and MSFT last price and day change.”
- “自选股今日涨跌一览”
- “Show my portfolio summary.”
- “S&P 500 vs Nasdaq today — numbers.”
- “帮我看一下 NVDA 和 TSLA 现在涨跌幅。”
- “我的持仓今天哪只回撤最大？”

## Negative boundaries
- **news_digest**: **Headline digest / 今日新闻** without **symbols, positions, or price tables** as the main ask.
- **search_web**: **Why** a sector moved (macro essay) — **search_web**; **numbers for my tickers** — **stock_monitor**.
- **general_chat**: Casual “stocks are wild” with **no data request** — chat.
- **weather**: Obvious boundary — not finance.

## Workflow hints
- `run_skill(stock-monitor)` for tables; `web_search` for contextual “why”; `magazine-render` if PDF magazine path is used.
