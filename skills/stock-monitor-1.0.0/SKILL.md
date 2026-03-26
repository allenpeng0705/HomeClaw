---
name: stock-monitor
description: |
  Watchlist quotes, portfolio Markdown table (holdings optional), YAML volatility/price alerts. Quotes: AKShare (default, no token), optional TuShare (token), Yahoo/yfinance fallback or primary; headlines via Yahoo. Same Yahoo-style symbols (.SS .SZ .HK). Use for portfolio, stock checks, cron_schedule alerts.
homepage: https://github.com/allenpeng0705/HomeClaw
keywords: "stock portfolio NVDA AAPL ticker yfinance Yahoo Finance akshare tushare 股票 行情 持仓 alert cron BTC"
trigger:
  patterns: ["portfolio|watchlist|stock|ticker|NVDA|AAPL|shares|行情|股票|持仓|股价|涨跌|alert.*stock"]
  instruction: |
    The user asked about stocks, portfolio, or price alerts. Use run_skill(skill_name='stock-monitor-1.0.0', script='stock_monitor.py', args=[...]).
    Summary of holdings/watchlist: args=["portfolio"]. Evaluate alert rules from config: args=["check"]. Quick news for a symbol: args=["news", "SYMBOL"] or args=["context", "SYMBOL"] for price + headlines.
    Edit config/watchlist.yml for watchlist, optional holdings, and alerts. For recurring push alerts use cron_schedule with task_type run_skill and script stock_monitor.py args ["check"].
    Quotes use `quote_provider` in watchlist YAML: default **akshare** (no token), optional **tushare** (token), or **yfinance**; `quote_fallback_yfinance: true` retries Yahoo if primary fails. Headlines stay Yahoo. Not financial advice. For deeper "why" use web_search after context.
    If the user asks for prettier/magazine-style output:
    1) Run stock-monitor as usual to get output.
    2) Build structured stock JSON from the result (watchlist/items).
    3) Call AST-first renderer:
       run_skill(skill_name="magazine-render-1.0.0", script="render_magazine.py",
                args=["render-template-ast", "--template", "stock", "--title", "Stock Brief", "--theme", "dispatch", "--json", "<STOCK_JSON>", "--output_format", "browser_preview_html", "--out", "stock_brief.preview.html"])
    4) Create PDF only when user explicitly asks for print/download/export (same call with --output_format pdf and .pdf out file).
  auto_invoke:
    script: stock_monitor.py
    args: ["portfolio"]
---

# Stock monitor (multi-source quotes)

Quotes from **AKShare** (default, no token), optional **TuShare** (`tushare_token` or `TUSHARE_TOKEN`), and **Yahoo** via **yfinance** (fallback or `quote_provider: yfinance`). Headlines/news still use Yahoo. All sources are unofficial / delayed—not financial advice.

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

## Assistant reply format (important)

The script prints **ready-to-send Markdown** (pipe tables, optional holdings bullets). When you answer the user:

1. **Prefer pasting the tool output unchanged** (full table + footer line about Yahoo/yfinance). A one-line intro in the user’s language is fine (e.g. 以下为您的自选股行情).
2. **Do not** “improve” the table with ASCII/box-drawing trees (`├──`, `┌`, `▼`), merged cells, or made-up symbols (e.g. AAPLE). Small local models often garble tables; copying the tool text avoids that.
3. **Do not** invent portfolio totals or currencies; if the tool shows a total, repeat it exactly; if it does not, do not guess.
4. If the user asked “yesterday” and `portfolio` only shows **today’s** day change, say that clearly—the script does not fetch historical OHLC in `portfolio` mode.

## FAQ (why tickers look “wrong”)

- **US names (e.g. AAPL) in the chat but not in my YAML:** The script only prints symbols from **`watchlist` + `holdings`**. If the assistant message lists Apple/NVDA but the **tool result** footer says only `300418.SZ, 688049.SS`, the extras were **hallucinated** by the model—compare the **Tool (run_skill)** block and use the verbatim-copy rule above.
- **I edited YAML but the table didn’t change:** Confirm Core runs the skill under `skills/stock-monitor-1.0.0/` and you are not overriding the path with env **`HOMECLAW_STOCK_MONITOR_CONFIG`** / **`STOCK_MONITOR_CONFIG`** pointing at another file. The `portfolio` output ends with a line showing which file and tickers were used.
- **`watchlist` must be a YAML list** (`- "300418.SZ"`). A single string or bad indentation can yield an empty list so only `holdings` appear.

## Configure

Edit **`config/watchlist.yml`** (see **`watchlist.example.yml`**):

- **`quote_provider`** — `akshare` (default), `tushare`, or `yfinance`. **`quote_fallback_yfinance`** (default true) tries Yahoo when the primary source fails (e.g. US ticker). **`tushare_token`** or env **`TUSHARE_TOKEN`** / **`TSPRO_TOKEN`** for TuShare. Per-symbol: `{ symbol: "NVDA", quote_provider: yfinance }` on watchlist / holdings / alerts.
- **watchlist** — Yahoo tickers: US (`NVDA`), China SSE (`.SS`), Shenzhen (`.SZ`), HK (`.HK`), indices (`000001.SS`, `^HSI`), crypto (`BTC-USD`). Details in **README.md**.
- **holdings** — optional `symbol`, `shares`, optional `avg_cost` for P&L lines.
- **Portfolio table** rows = **union of `watchlist` and `holdings` symbols only**. A symbol that appears **only** under **`alerts:`** is **not** shown in `portfolio` output (add it to `watchlist` or `holdings` if you want a quote).
- **alerts** — rules with `id`, `symbol`, and one of:
  - `day_change_pct_at_or_below` / `day_change_pct_at_or_above`
  - `price_at_or_above` / `price_at_or_below`
- **alert_cooldown_hours** — same alert does not re-fire every minute (default 24).

## Push (cron)

Use **`cron_schedule`** with `task_type="run_skill"`, `skill_name="stock-monitor-1.0.0"`, `script="stock_monitor.py"`, `args=["check"]`. When rules fire, output includes headline snippets; optional **`post_process_prompt`** can summarize.

## Limits

- **Not** real-time Level 2; suitable for casual monitoring.
- **Yahoo** rate limits / outages may apply; **AKShare**/**TuShare** depend on upstream sites and your token tier.
- **Not financial advice.**

Dependencies: **`requirements.txt`** in this folder (`pip install -r skills/stock-monitor-1.0.0/requirements.txt` if needed). Human-oriented setup: **`README.md`**.
