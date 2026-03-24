#!/usr/bin/env python3
"""
Fetch current weather from wttr.in (no API key). Used by run_skill.

Accepts a city name OR a full natural-language question; extracts the place when possible.
When run via Core, HOMECLAW_SERVER_DATETIME / HOMECLAW_SERVER_TIMEZONE label the request
with the HomeClaw host clock (wttr still returns conditions for the named place).

Usage:
  python get_weather.py Beijing
  python get_weather.py "weather in London"
  python get_weather.py --full "What's the forecast for Tokyo tomorrow?"
  python get_weather.py --location "New York"
"""
from __future__ import annotations

import argparse
import re
import sys
from typing import List
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    import ssl
except ImportError:
    ssl = None

# Reasonable HTTP timeout (seconds)
_TIMEOUT_SEC = 30
_USER_AGENT = "HomeClaw-weather/1.0 (+https://github.com/allenpeng0705/HomeClaw)"


def fetch_weather(location: str, compact: bool = True) -> str:
    """Fetch weather from wttr.in. Never raises; returns error string on failure."""
    try:
        loc_str = (location if isinstance(location, str) else str(location or "")).strip()
    except Exception:
        loc_str = ""
    if not loc_str:
        return "Error: location is required (e.g. London, New York, Beijing)."
    loc_encoded = urllib.parse.quote(loc_str)
    if compact:
        url = f"https://wttr.in/{loc_encoded}?format=%l:+%c+%t+%h+%w"
    else:
        url = f"https://wttr.in/{loc_encoded}?T"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    max_attempts = 3
    retry_delay_sec = 2
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                return resp.read().decode("utf-8", errors="replace").strip()
        except urllib.error.HTTPError as e:
            return f"Error: wttr.in returned {e.code} for {loc_str}. Try another location or check spelling."
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if attempt < max_attempts - 1:
                time.sleep(retry_delay_sec)
                continue
            reason = getattr(e, "reason", e)
            return f"Error: could not reach wttr.in: {reason}"
        except Exception as e:
            if ssl and isinstance(e, ssl.SSLError):
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay_sec)
                    continue
            return f"Error: could not reach wttr.in: {e}"
    return f"Error: could not reach wttr.in after {max_attempts} tries. Check network or try again later."


def _clean_tail(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[?？!！.,，。;；\s]+$", "", s).strip()
    return s


def _sanitize_extracted_location(loc: str) -> str:
    """Clear extractions that are time-only or vague weather phrases (use device/profile location instead)."""
    s = (loc or "").strip()
    if not s:
        return ""
    sl = s.lower()
    if re.match(
        r"^(today|tomorrow|tonight|now|this week|next week|明天|今天|今晚|下周)\s*$",
        sl,
    ):
        return ""
    if re.match(
        r"^(weather|forecast|temperature)\s+(today|tomorrow|tonight|now|this week|next week)\s*$",
        sl,
    ):
        return ""
    if re.match(
        r"^(天气|气温|预报)\s*(明天|今天|今晚|下周)\s*$",
        s.strip(),
    ):
        return ""
    return s


def _wants_extended_forecast(text: str) -> bool:
    """True when the user asks for a day or multi-day outlook (full wttr output)."""
    t = (text or "").lower()
    return bool(
        re.search(
            r"\b(tomorrow|tonight|next week|next few days|weekend|forecast)\b",
            t,
        )
        or re.search(r"(明天|今晚|下周|预报|周末)", text or "")
    )


def _extract_cn_location_before_weather(t: str) -> str:
    """
    Find 上海天气-style phrases inside longer Chinese text (overlapping),
    e.g. 请问上海天气怎么样 -> 上海.
    """
    if not t or not re.search(r"[\u4e00-\u9fff]", t):
        return ""
    candidates: List[str] = []
    # Overlapping: try every start position where N chars + 天气
    for m in re.finditer(r"(?=([\u4e00-\u9fff]{2,8})天气)", t):
        g = (m.group(1) or "").strip()
        if len(g) < 2:
            continue
        if any(x in g for x in ("请问", "怎么", "什么", "哪里", "是否", "能否")):
            continue
        if "问" in g:
            continue
        candidates.append(g)
    if not candidates:
        return ""
    # Prefer longest segment: 乌鲁木齐天气 -> 乌鲁木齐, not 木齐
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def extract_location_from_query(text: str) -> str:
    """
    Extract a place name from natural language (English + Chinese).
    Returns "" if nothing plausible found. Never raises.
    """
    try:
        if text is None or not isinstance(text, str) or not text.strip():
            return ""
    except Exception:
        return ""

    raw = text.strip()
    # Single-line, normalized spaces (keep content)
    t = re.sub(r"\s+", " ", raw)

    # --- Regex patterns (order: more specific first) ---
    patterns = [
        # ... Beijing's weather? / New York's weather (place starts with capital; skips "about")
        re.compile(
            r"\b([A-Z][\w\-'.]*(?:\s+[A-Z][\w\-'.]*)?)'s\s+weather(?:\s|$|[?？!！])",
        ),
        # English: What's the weather in Paris? / How's the weather in NYC?
        re.compile(
            r"(?:what(?:'s| is)|how(?:'s| is))\s+(?:the\s+)?(?:weather|forecast|temperature)\s+"
            r"(?:in|for|at|like in)\s+(.+?)(?:\s*[?？!！]|$)",
            re.I,
        ),
        # weather / forecast / temperature ... in|for|at PLACE
        re.compile(
            r"(?:weather|forecast|temperature|temp\.?)\s+(?:like\s+)?(?:in|for|at|near)\s+(.+?)(?:\s*[?？!！]|$)",
            re.I,
        ),
        # "... weather ... in City" (extra words before "in")
        re.compile(
            r"(?:weather|forecast|temperature).{0,40}?\b(?:in|for|at)\s+([A-Za-z][A-Za-z0-9\s\-'.]+?)(?:\s*[?？!！]|$)",
            re.I | re.DOTALL,
        ),
        # Chinese: 天气在 / 气温在 …
        re.compile(
            r"(?:天气|气温|预报).*?(?:在|于)\s*([\u4e00-\u9fff\w][\u4e00-\u9fff\w\s·\-]{1,24}?)(?:\s*[?？!！]|$)"
        ),
        # 天气：上海 / 天气 在 上海 (must not match 天气怎么样 → 怎么样)
        re.compile(r"天气\s*[:：]\s*([\u4e00-\u9fff]{2,12})"),
        re.compile(r"天气\s+(?:在|于)\s+([\u4e00-\u9fff]{2,12})"),
    ]

    for pat in patterns:
        m = pat.search(t)
        if m:
            loc = _clean_tail(m.group(1))
            # Drop trailing English fluff
            loc = re.sub(
                r"\s+(today|now|tomorrow|this week|please|thanks)\s*$",
                "",
                loc,
                flags=re.I,
            ).strip()
            if loc and 1 < len(loc) < 120:
                out = _sanitize_extracted_location(loc)
                if out:
                    return out

    cn_loc = _extract_cn_location_before_weather(t)
    if cn_loc:
        out = _sanitize_extracted_location(cn_loc)
        if out:
            return out

    # --- Legacy prefix strip (whole-line starts), case-insensitive ---
    prefixes = [
        "how about the weather in ",
        "how about the weather for ",
        "what's the weather in ",
        "what is the weather in ",
        "whats the weather in ",
        "how's the weather in ",
        "how is the weather in ",
        "hows the weather in ",
        "weather in ",
        "weather for ",
        "forecast for ",
        "forecast in ",
        "temperature in ",
        "temperature for ",
    ]
    tl = t.lower()
    for p in prefixes:
        if tl.startswith(p):
            rest = t[len(p) :].strip()
            out = _clean_tail(rest) or ""
            return _sanitize_extracted_location(out) or ""

    # "London weather" / "NYC weather" (no "in")
    m_city_weather = re.match(
        r"^([A-Za-z][A-Za-z0-9\s\-'.]+?)\s+weather\s*$",
        t.strip(),
        re.I,
    )
    if m_city_weather:
        cand = _clean_tail(m_city_weather.group(1))
        if cand and not re.search(r"\b(weather|forecast|temperature)\b", cand.lower()):
            bad_first = frozenset(
                {
                    "cold",
                    "hot",
                    "warm",
                    "cool",
                    "humid",
                    "bad",
                    "nice",
                    "good",
                    "great",
                    "rainy",
                    "sunny",
                    "windy",
                    "snowy",
                    "foggy",
                    "dry",
                    "wet",
                    "the",
                    "is",
                    "how",
                    "what",
                }
            )
            first = cand.split()[0].lower() if cand.split() else ""
            if first not in bad_first and 1 < len(cand) < 120:
                return cand

    # --- Short message = likely place name only (e.g. "Beijing", "New York") ---
    if _looks_like_plain_place(t):
        out = _sanitize_extracted_location(_clean_tail(t))
        return out or ""

    return ""


def _looks_like_plain_place(t: str) -> bool:
    """True if t looks like a city/region name, not a full question."""
    t = (t or "").strip()
    if not t or len(t) > 80:
        return False
    tl = t.lower()
    # "weather tomorrow", "forecast today" — not a place (use HOMECLAW_USER_LOCATION).
    if re.match(r"^(weather|forecast|temperature)\s+\S+\s*$", tl):
        return False
    ws = t.split()
    if len(ws) == 2 and ws[1].lower() == "weather":
        _adj_weather = frozenset(
            {
                "cold",
                "hot",
                "warm",
                "cool",
                "humid",
                "bad",
                "nice",
                "good",
                "great",
                "rainy",
                "sunny",
                "windy",
                "snowy",
                "foggy",
                "dry",
                "wet",
            }
        )
        if ws[0].lower() in _adj_weather:
            return False
    # Obvious questions
    if "?" in t or "？" in t:
        return False
    qwords = (
        "what ",
        "how ",
        "why ",
        "when ",
        "where ",
        "which ",
        "is the ",
        "are the ",
        "will it ",
        "can you ",
        "tell me ",
        "请问",
        "怎么",
        "什么",
        "哪里",
    )
    if any(tl.startswith(w) or f" {w.strip()}" in tl for w in qwords):
        return False
    if re.search(r"\b(weather|forecast|temperature|rain|snow|wind|humid|cold|hot)\b", tl):
        # Probably a sentence, not "London" alone
        if len(t.split()) > 4:
            return False
        # Short phrases like "weather tomorrow" are not place names
        if re.search(
            r"\b(tomorrow|today|tonight|now|this week|next week)\b",
            tl,
        ):
            return False
    # Mostly Latin or mostly CJK short phrase
    if re.fullmatch(r"[\w\s\-'.]+", t) or re.fullmatch(r"[\u4e00-\u9fff·\s]{2,24}", t.strip()):
        return len(t) >= 2
    return False


def get_location_from_core() -> str:
    """Use Core's user location from Companion/profile (HOMECLAW_USER_LAT_LNG or HOMECLAW_USER_LOCATION)."""
    import os

    try:
        lat_s = os.environ.get("HOMECLAW_USER_LAT_LNG")
        if isinstance(lat_s, str) and lat_s.strip():
            try:
                from base.geocode import parse_lat_lng

                p = parse_lat_lng(lat_s.strip())
                if p:
                    return f"{p[0]},{p[1]}"
            except Exception:
                pass
        val = os.environ.get("HOMECLAW_USER_LOCATION")
        return (val if isinstance(val, str) else "").strip()
    except Exception:
        return ""


def get_server_time_line_from_env() -> str:
    """One-line label from Core-injected env (empty if unset). Never raises."""
    import os

    try:
        dt = os.environ.get("HOMECLAW_SERVER_DATETIME")
        tz = os.environ.get("HOMECLAW_SERVER_TIMEZONE")
        iso = os.environ.get("HOMECLAW_SERVER_DATETIME_ISO")
        parts: List[str] = []
        if isinstance(dt, str) and dt.strip():
            parts.append(dt.strip())
        elif isinstance(iso, str) and iso.strip():
            parts.append(iso.strip()[:40])
        if not parts:
            return ""
        line = f"HomeClaw server time: {parts[0]}"
        if isinstance(tz, str) and tz.strip():
            line += f" ({tz.strip()})"
        return line
    except Exception:
        return ""


def main() -> None:
    """Entry point. Never raises; exits with 0 on success, 1 on usage/error."""
    try:
        parser = argparse.ArgumentParser(description="Get weather for a location via wttr.in")
        parser.add_argument(
            "location",
            nargs="?",
            default="",
            help="City, airport code, or natural language (e.g. 'weather in Beijing')",
        )
        parser.add_argument("--location", dest="location_opt", default="", help="Same as positional location")
        parser.add_argument("--full", action="store_true", help="Full forecast instead of one-line")
        args = parser.parse_args()
        location = str(args.location_opt or args.location or "").strip()
        if not location and len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-"):
            location = str(sys.argv[1]).strip()

        raw_query = (args.location_opt or args.location or "").strip()
        if not raw_query and len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-"):
            raw_query = str(sys.argv[1]).strip()

        if location:
            extracted = extract_location_from_query(location)
            if extracted:
                location = extracted

        if not location:
            core_loc = get_location_from_core()
            if core_loc:
                location = core_loc

        if not location:
            msg = (
                "Error: could not determine location. Name a city or place in your message "
                "(e.g. weather in Paris, London), or set location in your HomeClaw user profile / "
                "share location from Companion so Core can inject it when you ask without a place. "
                "CLI: get_weather.py Beijing"
            )
            print(msg, file=sys.stderr)
            print(msg)
            sys.stdout.flush()
            sys.stderr.flush()
            sys.exit(1)

        full_forecast = bool(getattr(args, "full", False)) or _wants_extended_forecast(raw_query)
        result = fetch_weather(location, compact=not full_forecast)
        if result:
            time_line = get_server_time_line_from_env()
            if time_line and not str(result).lstrip().lower().startswith("error:"):
                print(time_line)
            print(result)
            sys.stdout.flush()
    except SystemExit:
        raise
    except Exception as e:
        err_msg = f"Error: {e}"
        print(err_msg, file=sys.stderr)
        print(err_msg)
        sys.stdout.flush()
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
