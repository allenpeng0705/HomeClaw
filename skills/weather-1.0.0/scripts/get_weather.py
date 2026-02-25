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
    if not location or not location.strip():
        return "Error: location is required (e.g. London, New York, Beijing)."
    loc_encoded = urllib.parse.quote(location.strip())
    if compact:
        url = f"https://wttr.in/{loc_encoded}?format=%l:+%c+%t+%h+%w"
    else:
        url = f"https://wttr.in/{loc_encoded}?T"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.64.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as e:
        return f"Error: wttr.in returned {e.code} for {location}. Try another location or check spelling."
    except urllib.error.URLError as e:
        return f"Error: could not reach wttr.in: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


def extract_location_from_query(text: str) -> str:
    """Extract a place name from a natural language query like 'how about the weather in Beijing' or 'weather London'."""
    if not text or not text.strip():
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
    return t if t else text.strip()


def main():
    parser = argparse.ArgumentParser(description="Get weather for a location via wttr.in")
    parser.add_argument("location", nargs="?", default="", help="City or place, or natural language (e.g. 'weather in Beijing')")
    parser.add_argument("--location", dest="location_opt", default="", help="Same as positional location")
    parser.add_argument("--full", action="store_true", help="Full forecast instead of one-line")
    args = parser.parse_args()
    location = (args.location_opt or args.location or "").strip()
    if not location and len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        location = sys.argv[1]
    if location:
        extracted = extract_location_from_query(location)
        if extracted:
            location = extracted
    if not location:
        print("Usage: python get_weather.py <location>   e.g.  python get_weather.py London", file=sys.stderr)
        sys.exit(1)
    result = fetch_weather(location, compact=not args.full)
    print(result)


if __name__ == "__main__":
    main()
