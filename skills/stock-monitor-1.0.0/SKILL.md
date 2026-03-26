---
name: stock-monitor
description: |
  Watchlist quotes, portfolio Markdown table (holdings optional), YAML volatility/price alerts, and Yahoo headlines via yfinance (no API key). Supports US, HK, and China A-shares via Yahoo symbols (.SS Shanghai, .SZ Shenzhen, .HK Hong Kong). See skill README for 沪深港股 examples. Use for portfolio, stock checks, cron_schedule alerts.
homepage: https://github.com/allenpeng0705/HomeClaw
keywords: "stock portfolio NVDA AAPL ticker yfinance Yahoo Finance 股票 行情 持仓 alert cron BTC"
trigger:
  patterns: ["portfolio|watchlist|stock|ticker|NVDA|AAPL|shares|行情|股票|持仓|股价|涨跌|alert.*stock"]
  instruction: |
    The user asked about stocks, portfolio, or price alerts. Use run_skill(skill_name='stock-monitor-1.0.0', script='stock_monitor.py', args=[...]).
    Summary of holdings/watchlist: args=["portfolio"]. Evaluate alert rules from config: args=["check"]. Quick news for a symbol: args=["news", "SYMBOL"] or args=["context", "SYMBOL"] for price + headlines.
    Edit config/watchlist.yml for watchlist, optional holdings, and alerts. For recurring push alerts use cron_schedule with task_type run_skill and script stock_monitor.py args ["check"].
    Data is delayed/unofficial Yahoo via yfinance—not financial advice. For deeper "why" use web_search after context.
    If the user asks for prettier/magazine-style output:
    1) Run stock-monitor as usual to get output.
    2) Build structured stock JSON from the result (watchlist/items).
    3) Call AST-first renderer:
       run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-template-ast", "--template", "stock", "--title", "Stock Brief", "--theme", "dispatch", "--json", "<STOCK_JSON>", "--output_format", "browser_preview_html", "--out", "stock_brief.preview.html"])
    4) Create PDF only when user explicitly asks for print/download/export (same call with --output_format pdf and .pdf out file).
---

# Stock monitor (yfinance)

Near–real-time quotes and alerts using **Yahoo Finance** through **yfinance** (unofficial; no API key).

## run_skill

| User intent | Args |
|-------------|------|
| How is my portfolio / watchlist | `["portfolio"]` |
| Run alert rules (cron or manual) | `["check"]` or `["check", "--json"]` |
| News for a ticker | `["news", "NVDA"]` |
| Price + short “why” (headlines) | `["context", "NVDA"]` |

```text
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["portfolio"])
```

## Configure

Edit **`config/watchlist.yml`** (see **`watchlist.example.yml`**):

- **watchlist** — Yahoo tickers: US (`NVDA`), China SSE (`.SS`), Shenzhen (`.SZ`), HK (`.HK`), indices (`000001.SS`, `^HSI`), crypto (`BTC-USD`). Details in **README.md**.
- **holdings** — optional `symbol`, `shares`, optional `avg_cost` for P&L lines.
- **alerts** — rules with `id`, `symbol`, and one of:
  - `day_change_pct_at_or_below` / `day_change_pct_at_or_above`
  - `price_at_or_above` / `price_at_or_below`
- **alert_cooldown_hours** — same alert does not re-fire every minute (default 24).

## Push (cron)

Use **`cron_schedule`** with `task_type="run_skill"`, `skill_name="stock-monitor-1.0.0"`, `script="stock_monitor.py"`, `args=["check"]`. When rules fire, output includes headline snippets; optional **`post_process_prompt`** can summarize.

## Limits

- **Not** real-time Level 2; suitable for casual monitoring.
- **Yahoo** rate limits / outages may apply.
- **Not financial advice.**

Dependencies: **`requirements.txt`** in this folder (`pip install -r skills/stock-monitor-1.0.0/requirements.txt` if needed). Human-oriented setup: **`README.md`**.
