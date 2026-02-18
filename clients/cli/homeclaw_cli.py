#!/usr/bin/env python3
"""
HomeClaw CLI: send a message to Core and print the reply.

Usage:
  python homeclaw_cli.py chat "Hello"
  HOMECLAW_CORE_URL=http://192.168.1.10:9000 python homeclaw_cli.py chat "Hello"
  HOMECLAW_API_KEY=your-key python homeclaw_cli.py chat "Hello"

Requires: httpx (pip install httpx)
"""

import argparse
import json
import os
import sys

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

DEFAULT_URL = "http://127.0.0.1:9000"


def main():
    parser = argparse.ArgumentParser(
        description="HomeClaw CLI - send messages to Core and get replies"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Send a message and print the reply")
    chat_parser.add_argument(
        "message",
        type=str,
        nargs="+",
        help="Message text (words joined with spaces)",
    )
    chat_parser.add_argument(
        "--url",
        type=str,
        default=os.environ.get("HOMECLAW_CORE_URL", DEFAULT_URL),
        help=f"Core base URL (default: HOMECLAW_CORE_URL or {DEFAULT_URL})",
    )
    chat_parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("HOMECLAW_API_KEY", ""),
        help="API key if Core has auth_enabled (default: HOMECLAW_API_KEY)",
    )
    chat_parser.add_argument(
        "--user-id",
        type=str,
        default="cli",
        help="user_id sent to Core (default: cli)",
    )

    args = parser.parse_args()

    if args.command == "chat":
        url = args.url.rstrip("/")
        text = " ".join(args.message).strip()
        if not text:
            print("Error: message is empty", file=sys.stderr)
            sys.exit(1)
        payload = {
            "user_id": args.user_id,
            "text": text,
            "channel_name": "cli",
            "action": "respond",
        }
        headers = {"Content-Type": "application/json"}
        if getattr(args, "api_key", None):
            headers["X-API-Key"] = args.api_key
            headers["Authorization"] = f"Bearer {args.api_key}"
        try:
            r = httpx.post(
                f"{url}/inbound",
                json=payload,
                headers=headers,
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
        return

    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
