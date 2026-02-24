"""
Register the Friends external plugin with Core.
Run after Core is up and after starting the friends server.
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
FRIENDS_NAME = (os.environ.get("FRIENDS_PERSONA_NAME") or os.environ.get("FRIENDS_NAME") or "Veda").strip() or "Veda"
PLUGIN_BASE = os.environ.get("FRIENDS_BASE_URL", "http://127.0.0.1:3103")

payload = {
    "plugin_id": "friends",
    "name": "Friends",
    "description": f"Chat with {FRIENDS_NAME}, a friend/persona. Use when the user is in the companion thread (session_id=companion or conversation_type=companion). Data is stored separately from the main assistant.",
    "description_long": f"Friends feature: one conversation thread per user with {FRIENDS_NAME}. All messages and history are stored only in the friends store, not in the main user database. Core routes to this plugin when the client sends conversation_type=companion or session_id=companion (or channel_name=companion).",
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
            "name": "Friends chat",
            "description": f"One turn of conversation with {FRIENDS_NAME}. User message in user_input; returns persona reply.",
            "parameters": [],
            "method": "POST",
            "path": "/run",
        },
    ],
}


def main():
    base = CORE_URL.rstrip("/")
    url = f"{base}/api/plugins/register"
    print("Using CORE_URL=%s" % base)
    headers = {}
    if os.environ.get("CORE_API_KEY"):
        key = os.environ.get("CORE_API_KEY", "").strip()
        headers["X-API-Key"] = key
        headers["Authorization"] = f"Bearer {key}"
    try:
        try:
            r0 = httpx.get("%s/ready" % base, headers=headers or None, timeout=5)
            if r0.status_code != 200:
                print("Warning: GET %s/ready returned %s (Core may not be ready)" % (base, r0.status_code))
        except httpx.ConnectError:
            print("Error: Cannot connect to Core at %s. Is Core running? Start with: python -m main start" % base)
            sys.exit(1)
        r = httpx.post(url, json=payload, headers=headers or None, timeout=10)
        text = r.text or ""
        try:
            data = r.json() if text.strip() else {}
        except ValueError:
            data = {}
            print("Core returned non-JSON. status=%s body=%s" % (r.status_code, text[:500]))
        if not data and text.strip():
            print("Core returned non-JSON. status=%s body=%s" % (r.status_code, text[:500]))
            sys.exit(1)
        if r.status_code == 200 and data.get("registered"):
            print("Registered friends plugin:", data.get("plugin_id"))
        else:
            body = data if data else (text[:500] if text.strip() else "(empty)")
            print("Registration failed: %s %s" % (r.status_code, body))
            if r.status_code == 502:
                print("  502 Bad Gateway: Core may be down or unreachable from the server you're hitting. If CORE_URL is a proxy (e.g. Cloudflare), ensure Core is running and the proxy can reach it. Try CORE_URL=http://127.0.0.1:9000 when Core runs locally.")
            sys.exit(1)
    except httpx.ConnectError as e:
        print("Error: Cannot reach Core at %s. Is Core running?" % url)
        print("  %s" % e)
        sys.exit(1)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
