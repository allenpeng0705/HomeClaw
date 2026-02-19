#!/usr/bin/env python3
"""
HomeClaw CLI: chat with Core, check status, list sessions, pair (QR for mobile).

Usage:
  homeclaw chat "Hello"
  homeclaw status
  homeclaw sessions [--json]
  homeclaw pair          # print QR with Core URL + API key for app to scan
  HOMECLAW_CORE_URL=http://... HOMECLAW_API_KEY=... homeclaw chat "Hello"

Requires: httpx (pip install httpx). For QR: pip install qrcode[pil]
"""

import argparse
import json
import os
import sys
from urllib.parse import urlencode, urlparse

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

DEFAULT_URL = "http://127.0.0.1:9000"
CONFIG_DIR = os.path.expanduser("~/.config/homeclaw")
CONFIG_FILE = os.path.join(CONFIG_DIR, "cli.json")
DOTFILE = ".homeclaw"


def _load_config() -> dict:
    """Load url and api_key from config file. Prefer .homeclaw in cwd, then ~/.config/homeclaw/cli.json."""
    out = {}
    for path in [os.path.join(os.getcwd(), DOTFILE), CONFIG_FILE]:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r") as f:
                data = json.load(f)
                if isinstance(data.get("url"), str):
                    out["url"] = data["url"].rstrip("/")
                if isinstance(data.get("api_key"), str):
                    out["api_key"] = data["api_key"]
            break
        except Exception:
            pass
    return out


def _headers(api_key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _get_url_api_key(args) -> tuple:
    config = _load_config()
    url = (
        getattr(args, "url", None)
        or os.environ.get("HOMECLAW_CORE_URL")
        or config.get("url")
        or DEFAULT_URL
    )
    url = str(url).rstrip("/")
    api_key = (
        getattr(args, "api_key", None)
        or os.environ.get("HOMECLAW_API_KEY")
        or config.get("api_key")
        or ""
    )
    api_key = str(api_key or "")
    return url, api_key


def cmd_chat(args):
    url, api_key = _get_url_api_key(args)
    text = " ".join(args.message).strip()
    if not text:
        print("Error: message is empty", file=sys.stderr)
        sys.exit(1)
    payload = {
        "user_id": getattr(args, "user_id", "cli"),
        "text": text,
        "channel_name": "cli",
        "action": "respond",
    }
    try:
        r = httpx.post(
            f"{url}/inbound",
            json=payload,
            headers=_headers(api_key),
            timeout=120.0,
        )
    except httpx.ConnectError as e:
        print(f"Error: Cannot reach Core at {url}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if r.status_code != 200:
        print(f"Error: Core returned {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
    try:
        data = r.json()
    except Exception:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    reply = data.get("text", "")
    if data.get("error"):
        print(f"Core error: {data.get('error')}", file=sys.stderr)
    print(reply or "(no reply)")


def cmd_status(args):
    url, api_key = _get_url_api_key(args)
    try:
        r = httpx.get(
            f"{url}/api/sessions",
            headers=_headers(api_key),
            timeout=10.0,
        )
    except httpx.ConnectError as e:
        print(f"Core unreachable at {url}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if r.status_code == 200:
        try:
            data = r.json()
            sessions = data.get("sessions") or []
            print(f"Core reachable at {url}")
            print(f"Sessions: {len(sessions)}")
        except Exception:
            print(f"Core reachable at {url}")
    elif r.status_code == 403:
        print(f"Core reachable at {url} (sessions API disabled)")
    else:
        print(f"Core returned {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)


def cmd_sessions(args):
    url, api_key = _get_url_api_key(args)
    try:
        r = httpx.get(
            f"{url}/api/sessions",
            headers=_headers(api_key),
            timeout=10.0,
        )
    except httpx.ConnectError as e:
        print(f"Error: Cannot reach Core at {url}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if r.status_code == 403:
        print("Sessions API disabled", file=sys.stderr)
        sys.exit(1)
    if r.status_code != 200:
        print(f"Error: Core returned {r.status_code}: {r.text}", file=sys.stderr)
        sys.exit(1)
    try:
        data = r.json()
    except Exception:
        print(r.text, file=sys.stderr)
        sys.exit(1)
    sessions = data.get("sessions") or []
    if getattr(args, "json", False):
        print(json.dumps({"sessions": sessions}, indent=2))
        return
    if not sessions:
        print("No sessions.")
        return
    for s in sessions:
        sid = s.get("session_id") or s.get("session_id_key") or "?"
        uid = s.get("user_id") or "?"
        name = s.get("user_name") or uid
        print(f"  {sid}  {name} ({uid})")


def cmd_pair(args):
    """Print a QR code (or URL) with Core URL and API key for the companion app to scan."""
    url, api_key = _get_url_api_key(args)
    params = {"url": url}
    if api_key:
        params["api_key"] = api_key
    payload = "homeclaw://connect?" + urlencode(params)
    print("Scan with HomeClaw Companion: Settings → Scan QR to connect.", file=sys.stderr)
    print("", file=sys.stderr)
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=1, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print("(Install qrcode for QR: pip install qrcode[pil])", file=sys.stderr)
        print("", file=sys.stderr)
    print("URL (for manual entry):", file=sys.stderr)
    print(payload, file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="HomeClaw CLI - chat, status, sessions, pair (lightweight Core client)"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help=f"Core base URL (default: HOMECLAW_CORE_URL, or ~/.config/homeclaw/cli.json / .homeclaw, or {DEFAULT_URL})",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key if Core has auth_enabled (default: HOMECLAW_API_KEY or config file)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Send a message and print the reply")
    chat_parser.add_argument("message", type=str, nargs="+", help="Message text (words joined with spaces)")
    chat_parser.add_argument("--user-id", type=str, default="cli", help="user_id sent to Core (default: cli)")

    subparsers.add_parser("status", help="Check Core reachability and session count")

    sessions_parser = subparsers.add_parser("sessions", help="List sessions (GET /api/sessions)")
    sessions_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    subparsers.add_parser("pair", help="Print QR with Core URL + API key for app to scan")

    args = parser.parse_args()
    if args.command == "chat":
        cmd_chat(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "sessions":
        cmd_sessions(args)
    elif args.command == "pair":
        cmd_pair(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
