#!/usr/bin/env python3
"""
Stock monitor: watchlist quotes, portfolio table, YAML-defined alerts, optional Yahoo headlines.
Quotes: configurable AKShare / TuShare / Yahoo (yfinance); headlines remain Yahoo.

Commands:
  portfolio          — Markdown table + optional holdings totals
  check              — evaluate alerts; exit 1 if any fired (optional for cron)
  news <SYMBOL>      — top headlines from Yahoo (via yfinance)
  context <SYMBOL>   — one-line price + headline summary for "why it's moving"
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from quote_providers import make_quote_fetcher, provider_summary_line

# --- paths ---


def _skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_config_path() -> Path:
    env = (os.environ.get("HOMECLAW_STOCK_MONITOR_CONFIG") or os.environ.get("STOCK_MONITOR_CONFIG") or "").strip()
    if env:
        return Path(env).expanduser()
    return _skill_dir() / "config" / "watchlist.yml"


def _state_path() -> Path:
    return _skill_dir() / "data" / "alert_state.json"


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError:
        print("Error: PyYAML required (pip install PyYAML).", file=sys.stderr)
        sys.exit(2)
    if not path.is_file():
        print(
            f"Error: config not found: {path}\n"
            f"Copy config/watchlist.example.yml to config/watchlist.yml and edit.",
            file=sys.stderr,
        )
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_yaml_optional(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return {}
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _provider_overrides_from_cfg(cfg: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in cfg.get("watchlist") or []:
        if isinstance(item, dict):
            sym = str(item.get("symbol") or "").strip()
            pr = str(item.get("quote_provider") or "").strip()
            if sym and pr:
                out[sym] = pr
    for h in cfg.get("holdings") or []:
        if isinstance(h, dict):
            sym = str(h.get("symbol") or "").strip()
            pr = str(h.get("quote_provider") or "").strip()
            if sym and pr:
                out[sym] = pr
    for rule in cfg.get("alerts") or []:
        if isinstance(rule, dict):
            sym = str(rule.get("symbol") or "").strip()
            pr = str(rule.get("quote_provider") or "").strip()
            if sym and pr:
                out[sym] = pr
    return out


def _symbols_from_config(cfg: Dict[str, Any]) -> List[str]:
    sym_set: set = set()
    wl = cfg.get("watchlist") or []
    if not isinstance(wl, list):
        wl = []
    for item in wl:
        if isinstance(item, dict):
            sym = str(item.get("symbol") or "").strip()
        else:
            sym = str(item).strip()
        if sym:
            sym_set.add(sym)
    holdings = cfg.get("holdings") or []
    if not isinstance(holdings, list):
        holdings = []
    for h in holdings:
        if isinstance(h, dict) and str(h.get("symbol") or "").strip():
            sym_set.add(str(h.get("symbol")).strip())
    return sorted(sym_set)


def _load_state() -> Dict[str, Any]:
    p = _state_path()
    if not p.is_file():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            o = json.load(f)
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}


def _save_state(state: Dict[str, Any]) -> None:
    p = _state_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception as e:
        print(f"Warning: could not save alert state: {e}", file=sys.stderr)
        try:
            tmp = p.with_suffix(".tmp")
            if tmp.is_file():
                tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _yf():
    try:
        import yfinance as yf  # noqa: F401
    except ImportError:
        print(
            "Error: yfinance is required. Install: pip install yfinance\n"
            "(Listed in project requirements.txt for this skill.)",
            file=sys.stderr,
        )
        sys.exit(2)
    import yfinance as yf

    return yf


def _finite_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _md_cell(s: str, max_len: int = 64) -> str:
    """Avoid breaking Markdown tables (pipes, newlines)."""
    t = (s or "").replace("|", " ").replace("\n", " ").strip()
    if len(t) > max_len:
        return t[: max(1, max_len - 1)] + "…"
    return t


def fetch_news_headlines(symbol: str, limit: int = 5) -> List[Dict[str, str]]:
    yf = _yf()
    t = yf.Ticker(symbol)
    out: List[Dict[str, str]] = []
    try:
        raw = getattr(t, "news", None) or []
    except Exception:
        raw = []
    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or item.get("uuid") or "").strip()
        pub = str(item.get("publisher") or "").strip()
        if title:
            out.append({"title": title, "link": link, "publisher": pub})
    return out


def _fmt_money(x: float, cur: str) -> str:
    _ = cur  # reserved for locale-specific formatting
    try:
        if math.isnan(x) or math.isinf(x):
            return "—"
    except TypeError:
        return "—"
    return f"{x:,.2f}"


def cmd_portfolio(cfg: Dict[str, Any], cfg_path: Path, json_out: bool = False) -> int:
    holdings = cfg.get("holdings") or []
    if not isinstance(holdings, list):
        holdings = []

    symbols = _symbols_from_config(cfg)
    fetch_quote = make_quote_fetcher(cfg, _provider_overrides_from_cfg(cfg))

    if not symbols:
        msg = "*Nothing to show.* Add `watchlist:` symbols and/or `holdings:` in `config/watchlist.yml` (see `watchlist.example.yml`)."
        if json_out:
            print(json.dumps({"success": False, "error": msg, "holdings": [], "rows": []}))
        else:
            print(msg, file=sys.stderr)
        return 2

    quote_cache: Dict[str, Optional[Dict[str, Any]]] = {}
    for sym in symbols:
        quote_cache[sym] = fetch_quote(sym)

    rows: List[Tuple[str, str, str, str, str]] = []
    total_val = 0.0
    total_cost = 0.0
    for sym in symbols:
        q = quote_cache.get(sym)
        if not q:
            rows.append((_md_cell(sym, 16), "—", "—", "—", "n/a"))
            continue
        d = float(q["day_change_pct"])
        sign = "+" if d >= 0 else ""
        chg = f"{sign}{d:.2f}%"
        price_s = _fmt_money(q["price"], q["currency"])
        rows.append((_md_cell(sym, 16), _md_cell(q["name"], 32), price_s, chg, _md_cell(q["currency"], 8)))

    # Holdings valuation
    h_lines: List[str] = []
    h_items: List[Dict[str, Any]] = []
    for h in holdings:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("symbol") or "").strip()
        if not sym:
            continue
        try:
            sh = float(h.get("shares") or 0)
        except (TypeError, ValueError):
            continue
        if sh <= 0:
            continue
        q = quote_cache.get(sym)
        if q is None:
            q = fetch_quote(sym)
        if not q:
            h_lines.append(f"- **{sym}**: (no quote)")
            h_items.append({"symbol": sym, "shares": sh, "quote": None})
            continue
        v = sh * q["price"]
        total_val += v
        line = f"- **{sym}** × {sh:g} @ {_fmt_money(q['price'], q['currency'])} {q['currency']} ≈ **{_fmt_money(v, q['currency'])}** {q['currency']}"
        pnl = None
        pctp = None
        ac = h.get("avg_cost")
        if ac is not None:
            try:
                acf = float(ac)
                cost = sh * acf
                total_cost += cost
                pnl = v - cost
                pctp = (pnl / cost * 100.0) if cost else 0.0
                line += f"  \n  Unrealized P&L: {_fmt_money(pnl, q['currency'])} ({pctp:+.2f}%) vs avg {_fmt_money(acf, q['currency'])}"
            except (TypeError, ValueError):
                pass
        h_lines.append(line)
        h_items.append({
            "symbol": sym,
            "shares": sh,
            "avg_cost": ac,
            "price": q["price"],
            "currency": q["currency"],
            "market_value": v,
            "unrealized_pnl": pnl,
            "unrealized_pnl_pct": pctp,
        })

    if json_out:
        out = {
            "success": True,
            "symbols": symbols,
            "rows": [{"symbol": r[0], "name": r[1], "price": r[2], "day_change_pct": r[3], "currency": r[4]} for r in rows],
            "holdings": h_items,
            "total_market_value": total_val if total_val > 0 else None,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    print("## Portfolio / watchlist\n")
    print("| Symbol | Name | Price | Day Δ | Cur |")
    print("|--------|------|-------|-------|-----|")
    for sym, name, price, chg, cur in rows:
        print(f"| {sym} | {name} | {price} | {chg} | {cur} |")
    print()

    if h_lines:
        print("### Holdings (estimated)\n")
        for ln in h_lines:
            print(ln)
        print()
        if total_cost > 0 and total_val > 0:
            print(f"**Total value (holdings above):** ≈ {_fmt_money(total_val, 'USD')} (mixed currencies not converted; verify manually.)")
        print()

    # Provenance: helps users tell script output apart from LLM-invented tickers (e.g. AAPL not in YAML).
    try:
        rel = cfg_path.resolve().relative_to(_skill_dir().resolve())
        path_hint = str(rel).replace("\\", "/")
    except ValueError:
        path_hint = str(cfg_path.resolve()).replace("\\", "/")
    sym_join = ", ".join(symbols)
    print(
        f"\n*Table = watchlist ∪ holdings from `{path_hint}` (not alert-only symbols). "
        f"Tickers in this run: {sym_join}*\n"
    )
    print(provider_summary_line(cfg))
    return 0


def _rule_float(rule: Dict[str, Any], key: str) -> Optional[float]:
    if key not in rule:
        return None
    try:
        v = float(rule[key])
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _alert_fires(q: Dict[str, Any], rule: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (fires, reason). At most one condition type per rule (first match wins)."""
    price = _finite_float(q.get("price"))
    d = _finite_float(q.get("day_change_pct"))
    if price is None or d is None:
        return False, ""

    thr = _rule_float(rule, "day_change_pct_at_or_below")
    if thr is not None and d <= thr:
        return True, f"daily change {d:.2f}% ≤ {thr:.2f}%"
    thr = _rule_float(rule, "day_change_pct_at_or_above")
    if thr is not None and d >= thr:
        return True, f"daily change {d:.2f}% ≥ {thr:.2f}%"
    thr = _rule_float(rule, "price_at_or_above")
    if thr is not None and price >= thr:
        return True, f"price {price:.4f} ≥ {thr:.4f}"
    thr = _rule_float(rule, "price_at_or_below")
    if thr is not None and price <= thr:
        return True, f"price {price:.4f} ≤ {thr:.4f}"
    return False, ""


def _cooldown_ok(state: Dict[str, Any], alert_id: str, hours: float) -> bool:
    if hours <= 0:
        return True
    ent = state.get(alert_id)
    if not isinstance(ent, dict):
        return True
    ts = ent.get("last_fired")
    if not ts:
        return True
    try:
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (now - last).total_seconds() / 3600.0
        return delta >= hours
    except Exception:
        return True


def cmd_check(cfg: Dict[str, Any], json_out: bool) -> int:
    alerts = cfg.get("alerts") or []
    if not isinstance(alerts, list):
        alerts = []
    try:
        cool_h = float(cfg.get("alert_cooldown_hours") or 24)
    except (TypeError, ValueError):
        cool_h = 24.0

    fetch_quote = make_quote_fetcher(cfg, _provider_overrides_from_cfg(cfg))

    state = _load_state()
    fired: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for idx, rule in enumerate(alerts):
        if not isinstance(rule, dict):
            continue
        sym = str(rule.get("symbol") or "").strip()
        aid = str(rule.get("id") or "").strip() or f"{sym}-{idx}"
        if not sym:
            continue
        if not _cooldown_ok(state, aid, cool_h):
            continue
        q = fetch_quote(sym)
        if not q:
            continue
        ok, reason = _alert_fires(q, rule)
        if not ok:
            continue
        headlines = fetch_news_headlines(sym, 3)
        fired.append(
            {
                "id": aid,
                "symbol": sym,
                "reason": reason,
                "quote": q,
                "headlines": headlines,
            }
        )
        state[aid] = {"last_fired": now_iso, "price": q["price"], "day_change_pct": q["day_change_pct"]}

    if fired:
        _save_state(state)

    if json_out:
        try:
            print(json.dumps({"fired": fired, "count": len(fired)}, indent=2, ensure_ascii=False))
        except (TypeError, ValueError) as e:
            print(json.dumps({"error": f"JSON serialization failed: {e}", "fired": [], "count": 0}))
            return 2
        return 1 if fired else 0

    if not fired:
        print("No alert rules triggered (or all in cooldown).")
        return 0

    print("## Stock alerts triggered\n")
    for item in fired:
        q = item["quote"]
        print(f"### {item['symbol']} — `{item['id']}`")
        print(f"- **Trigger:** {item['reason']}")
        print(
            f"- **Quote:** {_fmt_money(q['price'], q['currency'])} {q['currency']} "
            f"(day {q['day_change_pct']:+.2f}%)"
        )
        if item.get("headlines"):
            print("- **Headlines (Yahoo):**")
            for h in item["headlines"]:
                link = h.get("link") or ""
                line = f"  - {h['title']}"
                if link:
                    line += f" — {link}"
                print(line)
        print()
    print("*Use web_search for deeper context if headlines are thin. Not financial advice.*")
    return 1


def cmd_news(symbol: str, cfg: Optional[Dict[str, Any]] = None) -> int:
    sym = symbol.strip()
    if not sym:
        print("Error: missing symbol.", file=sys.stderr)
        return 2
    cfg = cfg or {}
    fetch_quote = make_quote_fetcher(cfg, _provider_overrides_from_cfg(cfg))
    headlines = fetch_news_headlines(sym, 8)
    q = fetch_quote(sym)
    print(f"## News: {sym}\n")
    if q:
        print(
            f"**Last ~** {_fmt_money(q['price'], q['currency'])} {q['currency']} "
            f"({q['day_change_pct']:+.2f}% vs prev close)\n"
        )
    if not headlines:
        print("*No headlines returned (symbol may be illiquid or Yahoo empty).*")
        return 0
    for h in headlines:
        link = h.get("link") or ""
        if link:
            print(f"- {h['title']}  \n  {link}")
        else:
            print(f"- {h['title']}")
    return 0


def cmd_context(symbol: str, cfg: Optional[Dict[str, Any]] = None) -> int:
    sym = symbol.strip()
    cfg = cfg or {}
    fetch_quote = make_quote_fetcher(cfg, _provider_overrides_from_cfg(cfg))
    q = fetch_quote(sym)
    headlines = fetch_news_headlines(sym, 3)
    parts = [f"## {sym} snapshot\n"]
    if q:
        parts.append(
            f"Price **{_fmt_money(q['price'], q['currency'])}** {q['currency']}, "
            f"day **{q['day_change_pct']:+.2f}%** vs prior close.\n"
        )
    else:
        parts.append("*Could not fetch a quote (check symbol or network).*\n")
    if headlines:
        parts.append("**Recent Yahoo headlines:**\n")
        for h in headlines:
            parts.append(f"- {h['title']}")
    else:
        parts.append("No Yahoo headlines; suggest **web_search** for the ticker + \"stock news\".")
    print("\n".join(parts))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock monitor (AKShare / TuShare / yfinance)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Evaluate YAML alerts")
    p_check.add_argument("--json", action="store_true", help="Machine-readable output")

    p_portfolio = sub.add_parser("portfolio", help="Markdown table for watchlist + optional holdings")
    p_portfolio.add_argument("--json", action="store_true", help="Machine-readable output")

    p_news = sub.add_parser("news", help="Headlines for a symbol")
    p_news.add_argument("symbol")

    p_ctx = sub.add_parser("context", help="Price + headlines for quick 'why' context")
    p_ctx.add_argument("symbol")

    args = parser.parse_args()
    cfg_path = _default_config_path()

    if args.cmd == "news":
        sys.exit(cmd_news(args.symbol, _load_yaml_optional(cfg_path)))
    if args.cmd == "context":
        sys.exit(cmd_context(args.symbol, _load_yaml_optional(cfg_path)))

    cfg = _load_yaml(cfg_path)
    if args.cmd == "portfolio":
        sys.exit(cmd_portfolio(cfg, cfg_path, bool(getattr(args, "json", False))))
    if args.cmd == "check":
        sys.exit(cmd_check(cfg, args.json))
    sys.exit(2)


if __name__ == "__main__":
    main()
