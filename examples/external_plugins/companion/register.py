"""
Register the Companion external plugin with Core.
Run after Core is up and after starting the companion server.
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
COMPANION_NAME = os.environ.get("COMPANION_NAME", "Veda").strip() or "Veda"
PLUGIN_BASE = os.environ.get("COMPANION_BASE_URL", "http://127.0.0.1:3103")

payload = {
    "plugin_id": "companion",
    "name": "Companion",
    "description": f"Chat with {COMPANION_NAME}, a companion persona. Use when the user is in the companion thread (session_id=companion or conversation_type=companion). Data is stored separately from the main assistant.",
    "description_long": f"Companion feature: one conversation thread per user with {COMPANION_NAME}. All messages and history are stored only in the companion store, not in the main user database. Core routes to this plugin when the client sends conversation_type=companion or session_id=companion (or channel_name=companion).",
    "health_check_url": f"{PLUGIN_BASE.rstrip('/')}/health",
    "type": "http",
    "config": {
        "base_url": PLUGIN_BASE.rstrip("/"),
        "path": "run",
        "timeout_sec": 120,
    },
    "capabilities": [
        {
            "id": "chat",
            "name": "Companion chat",
            "description": f"One turn of conversation with {COMPANION_NAME}. User message in user_input; returns companion reply.",
            "parameters": [],
            "method": "POST",
            "path": "/run",
        },
    ],
}


def main():
    url = f"{CORE_URL.rstrip('/')}/api/plugins/register"
    headers = {}
    if os.environ.get("CORE_API_KEY"):
        key = os.environ.get("CORE_API_KEY", "").strip()
        headers["X-API-Key"] = key
        headers["Authorization"] = f"Bearer {key}"
    try:
        r = httpx.post(url, json=payload, headers=headers or None, timeout=10)
        data = r.json()
        if r.status_code == 200 and data.get("registered"):
            print("Registered companion plugin:", data.get("plugin_id"))
        else:
            print("Registration failed:", r.status_code, data)
            sys.exit(1)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
