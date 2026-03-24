# Stock monitor skill (HomeClaw)

This page consolidates how the **stock-monitor** skill works, how it compares to dedicated finance apps, Chinese market symbols, **notifications** (price / % rules + cron), dependencies, and limits.

**Skill folder:** `skills/stock-monitor-1.0.0/` — see also **`README.md`**, **`SKILL.md`**, and **`config/watchlist.example.yml`** there for copy-paste examples.

---

## How it works

1. **`config/watchlist.yml`** lists **symbols** in **Yahoo Finance** form (e.g. `NVDA`, `600519.SS`, `0700.HK`).
2. The script uses **yfinance** → **Yahoo Finance** (unofficial, **delayed**) for price, day % change, and optional headlines.
3. **`portfolio`** prints a **Markdown** table in chat (optional **holdings** with rough P&L if you set shares / `avg_cost`).
4. **`check`** evaluates **YAML alert rules** (price above/below, big up/down day). With **`cron_schedule`** + **`run_skill`**, you can **notify** yourself when a rule fires (Companion / last channel / push, depending on your HomeClaw setup).

---

## What this skill is for (vs a dedicated stock app)

| Dedicated app (broker / 同花顺 / etc.) | This skill |
|----------------------------------------|------------|
| Real-time L2, charts, **trading** | **Not** the goal—data is **delayed** and **read-only**. |
| Best UX for watching the market all day | Use an app; this does not replace it. |
| — | **Natural language** in HomeClaw and a **single place** next to your assistant. |
| — | **YAML rules** + optional **cron push** + **headline snippets** when something triggers. |

**Positioning:** **assistant + scheduled glance + rule ping**, not a trading terminal. Strong fits: **chat snapshot**, **notify when a line is crossed**, chaining **web_search** or other tools after an alert.

---

## Features

| Feature | How |
|--------|-----|
| Portfolio / watchlist | `run_skill` → `stock_monitor.py` **`["portfolio"]`** — Markdown table; optional holdings from YAML. |
| **Alerts & notifications** | Rules in **`alerts:`**; run **`["check"]`** manually or via **`cron_schedule`**. Fired output can include Yahoo **headlines**. |
| News / context | **`["news", "SYMBOL"]`** or **`["context", "SYMBOL"]`** for price + headlines. |

---

## Chinese stock markets (A股 / 港股 / indices)

Use the same symbols as [finance.yahoo.com](https://finance.yahoo.com)—no separate “China mode”.

| Market | Yahoo suffix | Examples |
|--------|----------------|----------|
| **沪市** Shanghai (SSE) | **`.SS`** | `600519.SS`, `601318.SS`, 科创板 `688xxx.SS` |
| **深市** Shenzhen (SZSE) | **`.SZ`** | `000001.SZ`, `300750.SZ` |
| **港股** Hong Kong | **`.HK`** | `0700.HK`, `9988.HK`, `3690.HK` |
| **主要指数** | — | `000001.SS` 上证综指, `399001.SZ` 深证成指, `399006.SZ` 创业板指, `^HSI` 恒生 |

A股数据多为**延时**；若代码无报价，到 Yahoo 上核对该股的准确 ticker。

---

## Configuration (`watchlist.yml`)

1. **`watchlist`** — list of tickers.
2. **`holdings`** (optional) — `symbol`, `shares`, optional `avg_cost` for P&L lines.
3. **`alerts:`** — list of rules; each needs **`id`**, **`symbol`**, and **one** trigger field (see below).
4. **`alert_cooldown_hours`** — default **24** so the same rule does not spam on every cron tick.
5. State is stored in **`skills/stock-monitor-1.0.0/data/alert_state.json`** (atomic write).

**Optional env:** `HOMECLAW_STOCK_MONITOR_CONFIG` or `STOCK_MONITOR_CONFIG` = absolute path to a YAML file with the same schema.

---

## Notifications: price above / below and other triggers

Each alert rule uses **one** numeric condition (evaluated in a fixed order in code):

| You want to know when… | YAML field | Example |
|------------------------|------------|---------|
| Price **≤** X | `price_at_or_below` | `150.0` |
| Price **≥** X | `price_at_or_above` | `200.0` |
| Day’s % change **≤** −X% | `day_change_pct_at_or_below` | `-3.0` |
| Day’s % change **≥** +X% | `day_change_pct_at_or_above` | `5.0` |

Comparison uses the **same delayed last quote** as the portfolio table—not real-time L2.

### Getting an actual **notification** (not only manual `check`)

1. Define rules under **`alerts:`** in **`watchlist.yml`**.
2. Add a **`cron_schedule`** task with **`task_type`**: **`run_skill`**, **`skill_name`**: **`stock-monitor-1.0.0`**, **`script`**: **`stock_monitor.py`**, **`args`**: **`["check"]`** (cadence e.g. hourly during market hours).
3. When a rule fires, Core delivers the script output like other cron tasks. Optional **`post_process_prompt`** can shorten the message for push.

**Spam control:** **`alert_cooldown_hours`** prevents the same **`id`** from firing again until the cooldown passes.

**Not in v1:** volume spikes, 52-week high/low, moving-average crosses—would need extra logic/data.

---

## `run_skill` commands

```text
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["portfolio"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["check"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["check", "--json"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["news", "NVDA"])
run_skill(skill_name="stock-monitor-1.0.0", script="stock_monitor.py", args=["context", "AAPL"])
```

**CLI (debug),** from repo root:

```bash
python3 skills/stock-monitor-1.0.0/scripts/stock_monitor.py portfolio
python3 skills/stock-monitor-1.0.0/scripts/stock_monitor.py check
python3 skills/stock-monitor-1.0.0/scripts/stock_monitor.py context NVDA
```

---

## Requirements & dependency install

- **Python:** `yfinance`, **PyYAML** (see **`skills/stock-monitor-1.0.0/requirements.txt`**).

**Core auto-install (all skills):** In **`config/skills_and_plugins.yml`** under **`tools:`**:

- **`run_skill_requirements_txt`**: **`true`** (default) — if **`<skill>/requirements.txt`** exists, Core runs **`pip install -r`** once per Core process before **`.py`** skill scripts. Set **`false`** to install manually only.
- **`run_skill_npm_install`**: **`true`** (default) — if **`<skill>/package.json`** exists, Core runs **`npm install`** in that folder before **`.js` / `.ts`** skill scripts (requires **`npm`** on `PATH`). Set **`false`** to disable.

Install only this skill’s Python deps:

```bash
pip install -r skills/stock-monitor-1.0.0/requirements.txt
```

Or full project deps: **`pip install -r requirements.txt`**. After changing **`requirements.txt`**, restart Core so a fresh install can run (cached per process).

---

## Robustness (implementation notes)

- Invalid / NaN prices are dropped; Markdown table cells are sanitized.
- Bad alert thresholds are ignored; alert state file uses **atomic replace** (temp + `os.replace`).
- Portfolio caches one quote per symbol per run.
- Concurrent **`run_skill`** runs serialize **pip** / **npm** installs with a lock so the same **`requirements.txt`** / **`package.json`** is not installed twice in parallel.

---

## Ecosystem & future

- Similar patterns exist in OpenClaw-style registries (**yahoo-finance**, **portfolio-tracker** skills using **yfinance**).
- **Alpha Vantage** or other vendors are **not** built in; you could extend the script and use HomeClaw **keyed** config for API keys.

---

## Disclaimer

Market data is **delayed / unofficial**; **not financial advice**. Verify prices with your broker.
