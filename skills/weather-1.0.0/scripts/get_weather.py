#!/usr/bin/env python3
"""
Fetch current weather from wttr.in (no API key). Used by run_skill.
Usage: python get_weather.py [--location] <location>
  e.g. python get_weather.py London
       python get_weather.py --location "New York"
"""
import argparse
import sys
import urllib.request
import urllib.parse
import urllib.error


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
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.64.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as e:
        return f"Error: wttr.in returned {e.code} for {loc_str}. Try another location or check spelling."
    except urllib.error.URLError as e:
        return f"Error: could not reach wttr.in: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


def extract_location_from_query(text: str) -> str:
    """Extract a place name from a natural language query. Returns empty string if none found or input invalid. Never raises."""
    try:
        if text is None or not isinstance(text, str) or not text.strip():
            return ""
    except Exception:
        return ""
    t = text.strip()
    # Common prefixes to strip (case-insensitive); order matters (longer first)
    prefixes = [
        "how about the weather in ",
        "how's the weather in ",
        "what's the weather in ",
        "what is the weather in ",
        "weather in ",
        "weather for ",
        "forecast for ",
        "temperature in ",
        "how about the weather ",
        "what's the weather ",
        "天气",
        "北京天气",
        "上海天气",
    ]
    for p in prefixes:
        if t.lower().startswith(p.lower()):
            t = t[len(p):].strip()
            break
    # Remove trailing question words
    for suffix in ("?", "？", " .", "?"):
        t = t.rstrip(suffix).strip()
    return (t if t else text.strip()) if isinstance(text, str) else ""


def get_location_from_core() -> str:
    """Use Core's user location from profile when set via HOMECLAW_USER_LOCATION (injected by run_skill). Never raises."""
    import os
    try:
        val = os.environ.get("HOMECLAW_USER_LOCATION")
        return (val if isinstance(val, str) else "").strip()
    except Exception:
        return ""


def _looks_like_question(text: str) -> bool:
    """True if text looks like a general question rather than a place name. Never raises."""
    try:
        if text is None or not isinstance(text, str) or not text.strip():
            return True
    except Exception:
        return True
    t = text.strip()
    if t.endswith("?") or t.endswith("？"):
        return True
    q = t.lower()
    if "怎么" in q or "怎么样" in q or "how" in q or "what" in q or "weather" in q or "天气" in q:
        # Likely a question; only treat as place if it's short and no question markers
        if len(t) > 25 or "?" in t or "？" in t:
            return True
    return False


def main() -> None:
    """Entry point. Never raises; exits with 0 on success, 1 on usage/error."""
    try:
        parser = argparse.ArgumentParser(description="Get weather for a location via wttr.in")
        parser.add_argument("location", nargs="?", default="", help="City or place, or natural language (e.g. 'weather in Beijing')")
        parser.add_argument("--location", dest="location_opt", default="", help="Same as positional location")
        parser.add_argument("--full", action="store_true", help="Full forecast instead of one-line")
        args = parser.parse_args()
        location = str(args.location_opt or args.location or "").strip()
        if not location and len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-"):
            location = str(sys.argv[1]).strip()
        if location:
            extracted = extract_location_from_query(location)
            if extracted:
                location = extracted
        # If still no location or the "location" looks like a question, use Core's profile location
        if not location or _looks_like_question(location):
            core_loc = get_location_from_core()
            if core_loc:
                location = core_loc
        if not location:
            print("Usage: python get_weather.py <location>   e.g.  python get_weather.py London", file=sys.stderr)
            print("If the user did not give a location, set it in profile (profile_update with location or city) so Core can pass it here.", file=sys.stderr)
            sys.exit(1)
        result = fetch_weather(location, compact=not getattr(args, "full", False))
        if result:
            print(result)
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
