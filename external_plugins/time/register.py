"""
Register the Time external plugin with Core (multiple capabilities, multiple params, one with post_process=true).
Run after Core is up and after starting the time server.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:9000")
PLUGIN_BASE = "http://127.0.0.1:3102"

payload = {
    "plugin_id": "time",
    "name": "Time Plugin",
    "description": "Get current time or list timezones. Use when the user asks what time it is, or the time in a city/country.",
    "description_long": "Returns current date and time; optional timezone and format (12h/24h). Can list common timezones. Use for: what time is it, current time, time in Tokyo, list timezones.",
    "health_check_url": f"{PLUGIN_BASE}/health",
    "type": "http",
    "config": {
        "base_url": PLUGIN_BASE,
        "path": "run",
        "timeout_sec": 10,
    },
    "capabilities": [
        {
            "id": "get_time",
            "name": "Get current time",
            "description": "Returns current time; optional timezone and format. Core will format in a friendly sentence (post_process).",
            "parameters": [
                {"name": "timezone", "type": "string", "required": False, "description": "IANA timezone, e.g. America/New_York, Europe/London, Asia/Tokyo."},
                {"name": "format", "type": "string", "required": False, "description": "Time format: 24h (default) or 12h."},
            ],
            "output_description": '{"text": "date and time string in requested timezone and format"}',
            "post_process": True,
            "post_process_prompt": "The user asked for the time. Turn this raw time string into one short, friendly sentence (e.g. 'It is 3:45 PM in New York.'). Do not add extra commentary.",
            "method": "POST",
            "path": "/run",
        },
        {
            "id": "list_timezones",
            "name": "List common timezones",
            "description": "Returns a list of common IANA timezone names the user can pass to get_time.",
            "parameters": [],
            "output_description": '{"text": "comma-separated list of timezone names"}',
            "post_process": False,
            "method": "POST",
            "path": "/run",
        },
    ],
}


def main():
    url = f"{CORE_URL.rstrip('/')}/api/plugins/register"
    headers = {}
    api_key = os.environ.get("CORE_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = httpx.post(url, json=payload, headers=headers or None, timeout=10)
        data = r.json()
        if r.status_code == 200 and data.get("registered"):
            print("Registered time plugin:", data.get("plugin_id"))
        else:
            print("Registration failed:", r.status_code, data)
            sys.exit(1)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
