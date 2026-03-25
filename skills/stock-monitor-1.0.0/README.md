# stock-monitor-1.0.0

A **watchlist + portfolio + alerts** skill for HomeClaw, inspired by the same patterns as OpenClaw-style skills that use **yfinance** (e.g. Yahoo Finance portfolio / finance skills on skill registries). **No API key** is required for the default path.

**Consolidated doc (same topics + Core pip/npm install):** [documentation/README.md](../../documentation/README.md)

## Natural language (what you can say)

### English

- “Show my stock watchlist / portfolio.”
- “Check my stock alerts now.”
- “Alert me if NVDA drops 3% today.” (then set a cron if you want it scheduled)
- “What happened to 0700.HK today? Give me context.”
- “Make this stock report a **magazine-style PDF**.”

### Chinese

- “看看我的自选股 / 组合今天怎么样？”
- “检查一下股票提醒规则有没有触发”
- “NVDA 跌 3% 就提醒我”
- “把自选股结果做成 **杂志风格 PDF**（排版更好看）”

## How it works (brief)

1. `config/watchlist.yml` lists **symbols** (Yahoo format: `NVDA`, `600519.SS`, `0700.HK`, …).
2. The script calls **yfinance** → **Yahoo Finance** (unofficial, delayed) for price, day %, and optional headlines.
3. **`portfolio`** prints a **Markdown** table in chat (same place as your other HomeClaw answers).
4. **`check`** runs your **YAML rules** (e.g. “down ≥ 3%”, “price above X”); if something fires, **cron** can **push** a message + short headlines—no separate app install for *that* path.

## What this skill is *for* (vs a dedicated stock app)

| Dedicated app (broker / 同花顺 / etc.) | This skill |
|----------------------------------------|------------|
| Real-time L2, fast charts, order execution | **Not** the goal—data is **delayed** and read-only. |
| Best UX for “watching the market” all day | Use an app; this won’t beat it. |
| — | **Natural language** in HomeClaw: “how’s my list today?”, “alert me if NVDA drops 3%”. |
| — | **One place** next to your assistant: brief snapshot + optional **cron** / **Companion** delivery. |
| — | **Lightweight rules** (YAML) + **headline snippets** when a rule fires—enough context to ask the LLM or **web_search** for more. |

**Honest takeaway:** treat this as **“assistant + scheduled glance + rule ping”**, not a trading terminal. The useful features to lean on are: **chat-native summary**, **push/cron when a rule hits**, **ties into your other skills** (search, email, etc.)—not millisecond charts.

## What you get

| Feature | How |
|--------|-----|
| **“How is my portfolio doing?”** | `run_skill` → `stock_monitor.py` with args **`["portfolio"]`** — Markdown table (prices, day %), optional holdings value/P&L from `config/watchlist.yml`. |
| **Volatility / price alerts** | Define rules in YAML; run **`["check"]`** manually or on a **cron** schedule. When a rule fires, output includes **Yahoo headlines** (via yfinance) for quick context. |
| **Deeper “why”** | Ask the assistant to **web_search** the ticker after **`["context", "SYMBOL"]`**, or read headline links. |

## Requirements

- **Python 3** + **`yfinance`** + **PyYAML**.
- **Network** access from the Core host to Yahoo Finance.

**Automatic install (default):** HomeClaw runs `pip install -r <skill>/requirements.txt` **once per Core process** before executing a Python skill script, when `tools.run_skill_requirements_txt` is `true` in `config/skills_and_plugins.yml` (default). Set it to `false` if you only want manual installs.

Manual install (optional):

```bash
pip install -r skills/stock-monitor-1.0.0/requirements.txt
```

Or install **all** HomeClaw deps from the repo root (includes `yfinance`):

```bash
pip install -r requirements.txt
```

After changing `requirements.txt`, **restart Core** so it can run `pip install` again (the install is cached per process).

## Chinese stock markets (A股 / 港股 / indices)

The skill uses **Yahoo Finance** symbols (same as on [finance.yahoo.com](https://finance.yahoo.com)). You do **not** need a separate “China mode”—add the right **suffix** to the numeric code.

| Market | Yahoo suffix | Examples |
|--------|----------------|----------|
| **沪市** Shanghai (SSE) | **`.SS`** | `600519.SS` (贵州茅台), `601318.SS` (中国平安). STAR 科创板: `688xxx.SS`. |
| **深市** Shenzhen (SZSE) | **`.SZ`** | `000001.SZ`, `300750.SZ` (创业板用 `.SZ`). |
| **港股** Hong Kong | **`.HK`** | `0700.HK` (腾讯), `9988.HK` (阿里巴巴), `3690.HK` (美团). |
| **主要指数** | — | `000001.SS` 上证综指, `399001.SZ` 深证成指, `399006.SZ` 创业板指, `^HSI` 恒生指数. |

**Tips**

- Look up the exact symbol on Yahoo Finance (search the company name + “Yahoo Finance”) if a code fails.
- A股数据多为**延时**；部分小盘股或 Yahoo 未收录的代码会**无报价**。
- Alerts / portfolio use the **same** `symbol` strings (e.g. `symbol: 600519.SS`).

## Configuration

1. Edit **`config/watchlist.yml`** (a default file ships with sample tickers; see **`watchlist.example.yml`** for commented examples).
2. **watchlist** — symbols Yahoo understands (`NVDA`, `600519.SS`, `0700.HK`, `BTC-USD`, …).
3. **holdings** (optional) — `symbol`, `shares`, optional `avg_cost` for unrealized P&L in the portfolio view.
4. **alerts** — one or more rules with:

   - `id` — stable string (used for cooldown).
   - `symbol` — ticker.
   - **At most one** trigger type per rule (examples):

     - `day_change_pct_at_or_below: -3` — fire if the day’s % change is ≤ −3%.
     - `day_change_pct_at_or_above: 5`
     - `price_at_or_above: 100000` (e.g. BTC-USD).
     - `price_at_or_below: 50`

5. **alert_cooldown_hours** — default `24` so cron jobs do not spam the same alert every run.

State (last fire time) is stored under **`data/alert_state.json`** (created automatically).

### Notifications: price above / below and other triggers

**Yes — this is already what the `alerts:` block is for.** Each rule has an `id`, a `symbol`, and **one** numeric trigger (first match wins):

| You want to know when… | Use this field | Example value |
|------------------------|----------------|---------------|
| Price is **lower than** X | `price_at_or_below` | `150.0` |
| Price is **higher than** X | `price_at_or_above` | `200.0` |
| The **day’s % change** is very negative | `day_change_pct_at_or_below` | `-3.0` (means ≤ −3%) |
| The **day’s % change** is very positive | `day_change_pct_at_or_above` | `5.0` |

Prices are compared to the **last quote** Yahoo returns (same as the portfolio table)—**not** real-time L2.

**To actually *notify* you** (not only when you manually run `check`), add a **`cron_schedule`** job with `task_type="run_skill"`, `script="stock_monitor.py"`, `args=["check"]` on whatever cadence you want (e.g. hourly during market hours). When a rule fires, Core delivers the script output (headlines + trigger reason) through your usual HomeClaw path (Companion / last channel / push, depending on setup). Use **`post_process_prompt`** if you want a shorter ping.

**Spam control:** `alert_cooldown_hours` (default 24) means the same `id` won’t fire again until the cooldown passes—even if cron runs every 5 minutes.

**Not in v1 (would need extra logic / data):** volume spikes, 52-week high/low breaks, moving-average crosses, or exchange-specific “special” events—those could be future extensions.

### Optional: custom config path

Set **`HOMECLAW_STOCK_MONITOR_CONFIG`** (or **`STOCK_MONITOR_CONFIG`**) to an absolute path to a YAML file with the same schema.

## Commands (run_skill args)

```text
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["portfolio"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["check"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["news", "NVDA"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["context", "AAPL"])
```

- **portfolio** — Markdown table + optional holdings section.
- **check** — evaluate alerts; prints Markdown when something fires; exit code `1` when at least one rule fired (useful for scripting). Add **`--json`** as a second arg for JSON output.
- **news** / **context** — headlines; **context** is a short combined “price + headlines” summary.

## CLI (debug)

From repo root:

```bash
python3 skills/stock-monitor-1.0.0/scripts/stock_monitor.py portfolio
python3 skills/stock-monitor-1.0.0/scripts/stock_monitor.py check
python3 skills/stock-monitor-1.0.0/scripts/stock_monitor.py context NVDA
```

## Push notifications (cron)

Use HomeClaw **`cron_schedule`** with:

- `task_type`: `run_skill`
- `skill_name`: `stock-monitor-1.0.0`
- `script`: `stock_monitor.py`
- `args`: `["check"]`  
- Optional **`post_process_prompt`**: e.g. “Summarize triggered alerts in 2 bullets for a push notification.”

Use a cron expression that matches how often you want to **evaluate** rules (e.g. every hour during market hours). Cooldown still prevents duplicate notifications for the same rule.

Delivery follows Core’s normal path (Companion / last channel / push), depending on your instance.

## Robustness (implementation)

- **Quotes:** Invalid or NaN prices are dropped; Markdown table cells avoid raw `|` / newlines breaking layout.
- **Alert rules:** Bad numeric thresholds are ignored; cooldown state is written with **atomic replace** (temp file + `os.replace`).
- **Portfolio:** One quote fetch per symbol per run (cached for the watchlist + holdings sections).
- **Core:** `run_skill` installs **pip** / **npm** dependencies under a **lock** so concurrent skill runs do not double-install the same `requirements.txt` / `package.json`.

## Alpha Vantage (optional, future)

This skill **defaults to yfinance only**. If you need exchange-grade limits or a vendor SLA, you can extend the script to call **Alpha Vantage** with an API key stored in a keyed skill config or env—see HomeClaw’s pattern for **keyed skills** in `config/core.yml` / user config. Not implemented in v1.

## OpenClaw / ecosystem

Public skill registries list **yahoo-finance**, **yahoofinance**, and **portfolio-tracker**-style skills that combine **yfinance** with Markdown reports. This skill follows the same idea: **watchlist YAML + run_skill + cron + optional LLM polish**, aligned with HomeClaw’s **daily-brief** and **weather** patterns.

## Disclaimer

Market data is **delayed / unofficial**; **not financial advice**. Verify critical prices on your broker.
