"""
Register the Quote external plugin with Core (multiple capabilities, one with post_process=true).
Run after Core is up and after starting the quote server.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:9000")
PLUGIN_BASE = "http://127.0.0.1:3101"

payload = {
    "plugin_id": "quote",
    "name": "Quote Plugin",
    "description": "Get a random inspirational quote, or by topic. Use when the user asks for a quote, motivation, or inspiration.",
    "description_long": "Returns random quotes; optional topic (motivation, success, dreams, etc.) and style (short/long). Use for: give me a quote, inspire me, quote about success.",
    "health_check_url": f"{PLUGIN_BASE}/health",
    "type": "http",
    "config": {
        "base_url": PLUGIN_BASE,
        "path": "run",
        "timeout_sec": 10,
    },
    "capabilities": [
        {
            "id": "get_quote",
            "name": "Get random quote",
            "description": "Returns a random inspirational quote. Core will add a brief reflection (post_process).",
            "parameters": [
                {"name": "style", "type": "string", "required": False, "description": "Output style: short (quote only) or long (with label)."},
            ],
            "output_description": '{"text": "quote and author string"}',
            "post_process": True,
            "post_process_prompt": "The user received this quote. Add one short sentence (under 15 words) that reflects why this quote matters or how it can inspire them. Do not repeat the quote.",
            "method": "POST",
            "path": "/run",
        },
        {
            "id": "get_quote_by_topic",
            "name": "Get quote by topic",
            "description": "Returns a random quote filtered by topic (e.g. motivation, success, dreams).",
            "parameters": [
                {"name": "topic", "type": "string", "required": True, "description": "Topic: motivation, success, innovation, dreams, perseverance."},
                {"name": "style", "type": "string", "required": False, "description": "Output style: short or long."},
            ],
            "output_description": '{"text": "quote and author string"}',
            "post_process": False,
            "method": "POST",
            "path": "/run",
        },
    ],
}


def main():
    url = f"{CORE_URL.rstrip('/')}/api/plugins/register"
    try:
        r = httpx.post(url, json=payload, timeout=10)
        data = r.json()
        if r.status_code == 200 and data.get("registered"):
            print("Registered quote plugin:", data.get("plugin_id"))
        else:
            print("Registration failed:", r.status_code, data)
            sys.exit(1)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
