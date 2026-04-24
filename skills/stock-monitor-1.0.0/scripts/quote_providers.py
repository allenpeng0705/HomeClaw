"""
Quote backends for stock-monitor: yfinance, AKShare, TuShare.
Symbols use Yahoo-style tickers (.SS / .SZ / .HK, ^HSI, US plain, BTC-USD).
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# East Money / AKShare daily hist (A-shares): 收盘, 涨跌幅, 涨跌额
_C_CLOSE = "\u6536\u76d8"
_C_PCT = "\u6da8\u8dcc\u5e45"
_C_AMT = "\u6da8\u8dcc\u989d"
# stock_individual_info_em rows (item column)
_I_NAME = "\u80a1\u7968\u7b80\u79f0"


def _finite_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _today_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _quote_dict(
    symbol: str,
    name: str,
    price: float,
    previous_close: float,
    day_change_pct: float,
    currency: str,
) -> Dict[str, Any]:
    return {
        "symbol": symbol.strip(),
        "name": name,
        "price": price,
        "previous_close": previous_close,
        "day_change_pct": day_change_pct,
        "currency": currency,
    }


def fetch_quote_yfinance(symbol: str) -> Optional[Dict[str, Any]]:
    """Latest price, day change % vs previous close, name, currency (Yahoo via yfinance)."""
    try:
        import yfinance as yf

        sym = symbol.strip()
        t = yf.Ticker(sym)
        hist = t.history(period="10d")
        if hist.empty or "Close" not in hist.columns:
            return None
        last_row = hist.iloc[-1]
        price = _finite_float(last_row.get("Close"))
        if price is None or price <= 0:
            return None
        prev_row = hist.iloc[-2] if len(hist) > 1 else last_row
        prev_close = _finite_float(prev_row.get("Close"))
        if prev_close is None or prev_close <= 0:
            prev_close = price

        try:
            fi = t.fast_info
            if fi is not None:
                lp = None
                pc = None
                if hasattr(fi, "get"):
                    lp = fi.get("last_price") or fi.get("lastPrice")
                    pc = fi.get("previous_close") or fi.get("previousClose")
                if lp is None:
                    lp = getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None)
                if pc is None:
                    pc = getattr(fi, "previous_close", None) or getattr(fi, "previousClose", None)
                lp_f = _finite_float(lp) if lp is not None else None
                pc_f = _finite_float(pc) if pc is not None else None
                if lp_f is not None and lp_f > 0:
                    price = lp_f
                if pc_f is not None and pc_f > 0:
                    prev_close = pc_f
        except Exception:
            pass

        chg_pct = ((price - prev_close) / prev_close * 100.0) if prev_close else 0.0
        chg_f = _finite_float(chg_pct)
        if chg_f is None:
            chg_f = 0.0

        info: Dict[str, Any] = {}
        try:
            info = t.info or {}
            if not isinstance(info, dict):
                info = {}
        except Exception:
            info = {}

        name = str(info.get("shortName") or info.get("longName") or sym)
        cur = str(info.get("currency") or "USD")

        return _quote_dict(sym, name, price, prev_close, chg_f, cur)
    except Exception:
        return None


def _ak_last_from_cn_hist(df: Any) -> Optional[Dict[str, float]]:
    """Parse last row from stock_zh_a_hist / stock_hk_hist / stock_us_hist (Chinese columns)."""
    if df is None or getattr(df, "empty", True):
        return None
    try:
        last = df.iloc[-1]
        price = _finite_float(last[_C_CLOSE])
        pct = _finite_float(last[_C_PCT])
        chg_amt = _finite_float(last[_C_AMT])
        if price is None or price <= 0 or pct is None:
            return None
        prev = price - chg_amt if chg_amt is not None else price / (1.0 + pct / 100.0) if pct != -100 else price
        if prev is None or prev <= 0:
            prev = price
        return {"price": price, "day_change_pct": pct, "previous_close": prev}
    except Exception:
        return None


def _ak_last_from_en_index(df: Any) -> Optional[Dict[str, float]]:
    if df is None or getattr(df, "empty", True) or "close" not in df.columns:
        return None
    try:
        last = df.iloc[-1]
        price = _finite_float(last["close"])
        if price is None or price <= 0:
            return None
        if len(df) >= 2:
            prev = _finite_float(df.iloc[-2]["close"])
        else:
            prev = price
        if prev is None or prev <= 0:
            prev = price
        pct = ((price - prev) / prev * 100.0) if prev else 0.0
        pf = _finite_float(pct)
        if pf is None:
            pf = 0.0
        return {"price": price, "day_change_pct": pf, "previous_close": prev}
    except Exception:
        return None


def _ak_hk_index_last(df: Any) -> Optional[Dict[str, float]]:
    if df is None or getattr(df, "empty", True):
        return None
    try:
        col = "latest" if "latest" in df.columns else "close" if "close" in df.columns else None
        if not col:
            return None
        last = df.iloc[-1]
        price = _finite_float(last[col])
        if price is None or price <= 0:
            return None
        if len(df) >= 2:
            prev = _finite_float(df.iloc[-2][col])
        else:
            prev = price
        if prev is None or prev <= 0:
            prev = price
        pct = ((price - prev) / prev * 100.0) if prev else 0.0
        pf = _finite_float(pct)
        if pf is None:
            pf = 0.0
        return {"price": price, "day_change_pct": pf, "previous_close": prev}
    except Exception:
        return None


def _ak_a_share_name(code: str) -> str:
    try:
        import akshare as ak

        df = ak.stock_individual_info_em(symbol=code)
        if df is None or getattr(df, "empty", True) or "item" not in df.columns or "value" not in df.columns:
            return code
        for _, row in df.iterrows():
            if str(row["item"]).strip() == _I_NAME:
                v = str(row["value"]).strip()
                return v or code
    except Exception:
        pass
    return code


def _ak_us_em_candidates(plain: str) -> List[str]:
    u = plain.strip().upper()
    if not u or not re.match(r"^[A-Z.\-]{1,16}$", u):
        return []
    # East Money US codes: try common exchange prefixes
    return [f"{p}.{u}" for p in ("105", "106", "107", "108")]


def fetch_quote_akshare(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        import akshare as ak
    except ImportError:
        return None

    sym = symbol.strip()
    su = sym.upper()
    start = "20250101"
    end = _today_yyyymmdd()

    # --- Mainland indices (Yahoo-style) ---
    if su == "000001.SS":
        try:
            df = ak.stock_zh_index_daily_em(symbol="sh000001", start_date=start, end_date=end)
            bar = _ak_last_from_en_index(df)
            if bar:
                return _quote_dict(sym, "\u4e0a\u8bc1\u6307\u6570", bar["price"], bar["previous_close"], bar["day_change_pct"], "CNY")
        except Exception:
            pass
        return None

    m399 = re.fullmatch(r"(\d{6})\.SZ", su)
    if m399 and m399.group(1).startswith("399"):
        code = m399.group(1)
        try:
            df = ak.stock_zh_index_daily_em(symbol=f"sz{code}", start_date=start, end_date=end)
            bar = _ak_last_from_en_index(df)
            if bar:
                return _quote_dict(sym, f"Index {code}", bar["price"], bar["previous_close"], bar["day_change_pct"], "CNY")
        except Exception:
            pass
        return None

    if su == "^HSI" or su == "^HSCEI":
        # HSI works with symbol HSI; HSCEI try same API name
        idx = "HSI" if su == "^HSI" else "HSCEI"
        try:
            df = ak.stock_hk_index_daily_em(symbol=idx)
            bar = _ak_hk_index_last(df)
            if bar:
                return _quote_dict(sym, idx, bar["price"], bar["previous_close"], bar["day_change_pct"], "HKD")
        except Exception:
            pass
        return None

    # --- HK stock ---
    mhk = re.fullmatch(r"(\d{1,5})\.HK", su)
    if mhk:
        code = mhk.group(1).zfill(5)
        try:
            df = ak.stock_hk_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
            bar = _ak_last_from_cn_hist(df)
            if bar:
                return _quote_dict(sym, sym, bar["price"], bar["previous_close"], bar["day_change_pct"], "HKD")
        except Exception:
            pass
        return None

    # --- A-share .SS / .SZ (stocks; 000001.SS handled above) ---
    ma = re.fullmatch(r"(\d{6})\.(SS|SZ)", su)
    if ma:
        code = ma.group(1)
        try:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
            bar = _ak_last_from_cn_hist(df)
            if bar:
                nm = _ak_a_share_name(code)
                return _quote_dict(sym, nm, bar["price"], bar["previous_close"], bar["day_change_pct"], "CNY")
        except Exception:
            pass
        return None

    # --- US: plain ticker ---
    if re.fullmatch(r"[A-Z]{1,5}", su):
        for em_sym in _ak_us_em_candidates(su):
            try:
                df = ak.stock_us_hist(symbol=em_sym, period="daily", start_date=start, end_date=end, adjust="")
                bar = _ak_last_from_cn_hist(df)
                if bar:
                    return _quote_dict(sym, su, bar["price"], bar["previous_close"], bar["day_change_pct"], "USD")
            except Exception:
                continue
        return None

    return None


def _tushare_token_resolve(cfg_token: Optional[str]) -> str:
    t = (cfg_token or "").strip()
    if t:
        return t
    return (os.environ.get("TUSHARE_TOKEN") or os.environ.get("TSPRO_TOKEN") or "").strip()


def _yahoo_to_tushare_stock_ts(su: str) -> Optional[str]:
    if su.endswith(".SS"):
        return su[:-3] + ".SH"
    if su.endswith(".SZ"):
        return su[:-3] + ".SZ"
    return None


def fetch_quote_tushare(symbol: str, token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    try:
        import tushare as ts
    except ImportError:
        return None

    sym = symbol.strip()
    su = sym.upper()
    pro = ts.pro_api(token)

    def _from_daily_df(df: Any, name: str, cur: str) -> Optional[Dict[str, Any]]:
        if df is None or getattr(df, "empty", True):
            return None
        try:
            df = df.sort_values("trade_date")
            last = df.iloc[-1]
            price = _finite_float(last.get("close"))
            pct = _finite_float(last.get("pct_chg"))
            pre = _finite_float(last.get("pre_close"))
            if price is None or price <= 0:
                return None
            if pct is None and pre is not None and pre > 0:
                pct = (price - pre) / pre * 100.0
            if pct is None:
                pct = 0.0
            if pre is None or pre <= 0:
                pre = price / (1.0 + pct / 100.0) if pct != -100 else price
            pf = _finite_float(pct)
            if pf is None:
                pf = 0.0
            return _quote_dict(sym, name, price, pre, pf, cur)
        except Exception:
            return None

    end = _today_yyyymmdd()
    start = "20250101"

    if su == "000001.SS":
        try:
            df = pro.index_daily(ts_code="000001.SH", start_date=start, end_date=end)
            q = _from_daily_df(df, "\u4e0a\u8bc1\u6307\u6570", "CNY")
            if q:
                return q
        except Exception:
            pass
        return None

    m399 = re.fullmatch(r"(\d{6})\.SZ", su)
    if m399 and m399.group(1).startswith("399"):
        code = m399.group(1)
        try:
            df = pro.index_daily(ts_code=f"{code}.SZ", start_date=start, end_date=end)
            q = _from_daily_df(df, f"Index {code}", "CNY")
            if q:
                return q
        except Exception:
            pass
        return None

    ts_stock = _yahoo_to_tushare_stock_ts(su)
    if ts_stock:
        try:
            df = pro.daily(ts_code=ts_stock, start_date=start, end_date=end)
            q = _from_daily_df(df, ts_stock.split(".")[0], "CNY")
            if q:
                return q
        except Exception:
            pass
        return None

    mhk = re.fullmatch(r"(\d{1,5})\.HK", su)
    if mhk:
        code = mhk.group(1).zfill(5) + ".HK"
        try:
            df = pro.hk_daily(ts_code=code, start_date=start, end_date=end)
            q = _from_daily_df(df, code, "HKD")
            if q:
                return q
        except Exception:
            pass
        return None

    return None


def _normalize_provider(p: str) -> str:
    x = (p or "").strip().lower()
    if x in ("yahoo", "yfinance", "yf"):
        return "yfinance"
    if x in ("akshare", "ak"):
        return "akshare"
    if x in ("tushare", "ts", "tu"):
        return "tushare"
    return x


def _fetch_by_provider(symbol: str, provider: str, tushare_token: str) -> Optional[Dict[str, Any]]:
    p = _normalize_provider(provider)
    if p == "yfinance":
        return fetch_quote_yfinance(symbol)
    if p == "akshare":
        return fetch_quote_akshare(symbol)
    if p == "tushare":
        return fetch_quote_tushare(symbol, tushare_token)
    return None


def make_quote_fetcher(
    cfg: Dict[str, Any],
    overrides: Optional[Dict[str, str]] = None,
) -> Callable[[str], Optional[Dict[str, Any]]]:
    """
    Build fetch_quote(symbol) using cfg:
      quote_provider: akshare | tushare | yfinance (default akshare)
      quote_fallback_yfinance: bool (default true)
      tushare_token: optional; else TUSHARE_TOKEN / TSPRO_TOKEN env
    overrides: symbol -> provider for per-row watchlist/holdings.
    """
    default_p = _normalize_provider(str(cfg.get("quote_provider") or "akshare"))
    if default_p not in ("yfinance", "akshare", "tushare"):
        default_p = "akshare"

    try:
        fb = cfg.get("quote_fallback_yfinance")
        if fb is None:
            fallback = True
        else:
            fallback = bool(fb)
    except Exception:
        fallback = True

    tok = _tushare_token_resolve(str(cfg.get("tushare_token") or ""))
    ov = {k: _normalize_provider(v) for k, v in (overrides or {}).items() if v}

    def fetch(symbol: str) -> Optional[Dict[str, Any]]:
        sym = symbol.strip()
        p = ov.get(sym) or default_p
        if p not in ("yfinance", "akshare", "tushare"):
            p = default_p
        if p == "tushare" and not tok:
            q = None
        else:
            q = _fetch_by_provider(sym, p, tok)
        if q is None and fallback and p != "yfinance":
            q = fetch_quote_yfinance(sym)
        return q

    return fetch


def provider_summary_line(cfg: Dict[str, Any]) -> str:
    p = _normalize_provider(str(cfg.get("quote_provider") or "akshare"))
    if p not in ("yfinance", "akshare", "tushare"):
        p = "akshare"
    try:
        fb = cfg.get("quote_fallback_yfinance")
        fallback = True if fb is None else bool(fb)
    except Exception:
        fallback = True
    bits = [p]
    if fallback and p != "yfinance":
        bits.append("Yahoo fallback")
    provider_str = "/".join(bits)
    return f"*Data: quotes primary **{provider_str}** (see `quote_provider` in YAML); headlines still Yahoo. Not financial advice.*"
