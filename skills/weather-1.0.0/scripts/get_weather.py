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
from datetime import datetime, timedelta
from typing import List
import time
import urllib.error
import urllib.parse
import urllib.request

# Force UTF-8 stdio for Windows subprocess capture (avoids mojibake in Core logs/results).
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import ssl
except ImportError:
    ssl = None

# HTTP timeout (seconds); keep moderate so a dead wttr.in does not block the chat for a full minute.
_TIMEOUT_SEC = 12
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
        # Keep one-line output but include condition text for better downstream advice.
        url = f"https://wttr.in/{loc_encoded}?format=%l:+%C,+%t,+Hum:%h,+Wind:%w"
    else:
        url = f"https://wttr.in/{loc_encoded}?T"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    max_attempts = 2
    retry_delay_sec = 1
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
    # Remove trailing temporal words accidentally captured with city names:
    # "北京明天" -> "北京", "shanghai tomorrow" -> "shanghai"
    s = re.sub(r"(明天|今天|今晚|下周|这周|现在)$", "", s).strip()
    s = re.sub(
        r"\b(today|tomorrow|tonight|now|this week|next week)\b$",
        "",
        s,
        flags=re.I,
    ).strip()
    return s


def _wants_extended_forecast(text: str) -> bool:
    """True only when user explicitly asks for full/detailed forecast output."""
    t = (text or "").lower()
    return bool(
        re.search(
            r"\b(full|detailed|multi-?day|7[- ]?day|weekly|next week)\b",
            t,
        )
        or re.search(r"(详细|完整|多日|一周|下周|7天)", text or "")
    )


def _strip_ansi(s: str) -> str:
    """Remove ANSI escape sequences for mobile readability."""
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", s or "")


def _extract_temp_c(text: str) -> int | None:
    m = re.search(r"([+-]?\d+)\s*°?C", text or "", re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_humidity_pct(text: str) -> int | None:
    m = re.search(r"([0-9]{1,3})\s*%", text or "")
    if not m:
        return None
    try:
        v = int(m.group(1))
        return v if 0 <= v <= 100 else None
    except Exception:
        return None


def _build_life_tips(one_line_weather: str) -> list[str]:
    """Build concise practical tips (dress / umbrella / wash-car)."""
    t = one_line_weather or ""
    tl = t.lower()
    tips: list[str] = []
    temp_c = _extract_temp_c(t)
    hum = _extract_humidity_pct(t)
    rainy = any(k in tl for k in ("rain", "drizzle", "shower", "thunder", "storm", "snow", "sleet"))
    windy = ("wind:" in tl and any(k in tl for k in ("km/h", "mph"))) and any(k in tl for k in ("15 km/h", "20 km/h", "25 km/h", "30 km/h"))

    # Dress tip
    if temp_c is not None:
        if temp_c <= 5:
            tips.append("穿衣建议：偏冷，建议厚外套/羽绒服，注意保暖。")
        elif temp_c <= 14:
            tips.append("穿衣建议：微凉，建议外套或薄毛衣。")
        elif temp_c <= 24:
            tips.append("穿衣建议：体感舒适，长袖或薄外套即可。")
        elif temp_c <= 30:
            tips.append("穿衣建议：偏暖，短袖为主，注意补水。")
        else:
            tips.append("穿衣建议：较热，轻薄透气衣物，注意防晒和补水。")

    # Umbrella/rain tip
    if rainy:
        tips.append("出行建议：有降水信号，建议带伞。")
    elif hum is not None and hum >= 85:
        tips.append("出行建议：湿度较高，体感可能闷；可备伞以防阵雨。")
    else:
        tips.append("出行建议：降水风险看起来不高。")

    # Car wash tip
    if rainy:
        tips.append("洗车建议：不太适合，近期可能很快又变脏。")
    elif hum is not None and hum >= 90:
        tips.append("洗车建议：一般，湿度高且可能有水汽/雾。")
    else:
        tips.append("洗车建议：相对适合。")

    if windy:
        tips.append("额外提示：风力偏大，体感会更凉，出行注意防风。")
    return tips


def _cn_place_candidate_is_reminder_junk(g: str) -> bool:
    """True when a capture is scheduling/action text, not a wttr.in place (mixed 提醒 + 预报)."""
    if not g or len(g) < 2:
        return True
    junk_sub = (
        "发送",
        "给我",
        "帮我",
        "提醒",
        "点钟",
        "分钟",
        "每天",
        "早上",
        "晚上",
        "中午",
        "以后",
        "之后",
    )
    return any(s in g for s in junk_sub)


def _extract_cn_location_before_weather(t: str) -> str:
    """
    Find 上海天气-style phrases inside longer Chinese text (overlapping),
    e.g. 请问上海天气怎么样 -> 上海.
    """
    if not t or not re.search(r"[\u4e00-\u9fff]", t):
        return ""
    # Shortest Han suffix (2–8 chars) before 的+天气+预报 (e.g. …发送北京的天气预报 -> 北京).
    _tag = "的天气预报"
    _ti = t.rfind(_tag)
    if _ti >= 0:
        for _n in range(2, 9):
            if _ti < _n:
                break
            g0 = t[_ti - _n : _ti]
            if len(g0) != _n:
                continue
            if not re.match(r"^[\u4e00-\u9fff]+$", g0):
                continue
            if not _cn_place_candidate_is_reminder_junk(g0):
                return g0
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
        if _cn_place_candidate_is_reminder_junk(g):
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
    # Short CJK lines like "明天天气怎么样" match [\u4e00-\u9fff]{2,24} but are questions, not place names.
    if re.search(r"[\u4e00-\u9fff]", t) and re.search(
        r"(怎么样|如何|怎样|好不好|可不可以|是不是|有没有)",
        t,
    ):
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


def _parse_server_datetime_from_env() -> datetime | None:
    """Best-effort parse Core-injected server datetime for weekday inference."""
    import os

    for key in ("HOMECLAW_SERVER_DATETIME_ISO", "HOMECLAW_SERVER_DATETIME"):
        raw = os.environ.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        s = raw.strip()
        try:
            if key.endswith("_ISO"):
                return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
            # e.g. 2026-03-25 18:27
            return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
        except Exception:
            continue
    try:
        return datetime.now()
    except Exception:
        return None


def _target_day_line(raw_query: str) -> str:
    """Return markdown bullet for today/tomorrow/day-after with weekday, when query asks it."""
    q = (raw_query or "").strip().lower()
    q_raw = raw_query or ""
    delta = 0
    if "后天" in q_raw:
        delta = 2
    elif "明天" in q_raw or "tomorrow" in q:
        delta = 1
    elif "今天" in q_raw or "today" in q:
        delta = 0
    else:
        return ""
    base = _parse_server_datetime_from_env()
    if base is None:
        return ""
    target = base + timedelta(days=delta)
    wk = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][target.weekday()]
    label = "后天" if delta == 2 else ("明天" if delta == 1 else "今天")
    return f"- 目标日期：{label}（{wk}）"


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
        parser.add_argument(
            "--verbatim-place",
            dest="verbatim_place",
            default="",
            metavar="PLACE",
            help="Use PLACE for wttr.in exactly (skip NL extraction). Set by Core DAG after LLM extracts city.",
        )
        parser.add_argument("--full", action="store_true", help="Full forecast instead of one-line")
        args = parser.parse_args()
        verbatim = str(getattr(args, "verbatim_place", None) or "").strip()

        location = str(args.location_opt or args.location or "").strip()
        if not location and len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-"):
            location = str(sys.argv[1]).strip()

        raw_query = (args.location_opt or args.location or "").strip()
        if not raw_query and len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-"):
            raw_query = str(sys.argv[1]).strip()
        # Original user text (Core sets when running skill) — used for tomorrow/today hints when args are only --verbatim-place.
        try:
            import os as _os

            _um = (_os.environ.get("HOMECLAW_USER_MESSAGE") or "").strip()
            if _um:
                raw_query = _um[:2000]
        except Exception:
            pass

        if verbatim:
            location = verbatim
        elif location:
            extracted = extract_location_from_query(location)
            if extracted:
                location = extracted
            elif not _looks_like_plain_place(location):
                # Full question with no extractable city (e.g. 明天天气怎么样); do not send the whole
                # sentence to wttr.in (500). Fall through to profile / HOMECLAW_USER_LAT_LNG.
                location = ""

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
        result = _strip_ansi(result)
        if result:
            time_line = get_server_time_line_from_env()
            is_error = str(result).lstrip().lower().startswith("error:")
            if not is_error:
                print("## Weather")
                if time_line:
                    print(f"- {time_line}")
                day_line = _target_day_line(raw_query)
                if day_line:
                    print(day_line)
                print(f"- {result}")
            else:
                print(result)
            # Add concise practical tips for compact mode.
            if not full_forecast and not is_error:
                tips = _build_life_tips(result)
                if tips:
                    print("\n### Practical Tips")
                    for tip in tips:
                        print(f"- {tip}")
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
