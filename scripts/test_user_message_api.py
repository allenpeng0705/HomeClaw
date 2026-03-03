#!/usr/bin/env python3
"""
Test script for the single HomeClaw social network APIs: user-message and user-inbox.

Usage:
  python scripts/test_user_message_api.py [--core-url URL] [--api-key KEY] [--from USER] [--to USER] [--text TEXT]
  # Or set env: HOMECLAW_CORE_URL, HOMECLAW_API_KEY (or auth_api_key from config/core.yml when not set)

Examples:
  python scripts/test_user_message_api.py --from AllenPeng --to PengXiaoFeng --text "Hello from test"
  python scripts/test_user_message_api.py --inbox PengXiaoFeng

Requires: Core running with users that have each other as user-type friends in config/user.yml.
"""

import argparse
import os
import sys

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx", file=sys.stderr)
    sys.exit(1)


def get_core_url_and_key(core_url: str | None, api_key: str | None) -> tuple[str, str]:
    url = (core_url or os.environ.get("HOMECLAW_CORE_URL") or "").strip() or "http://127.0.0.1:9000"
    key = (api_key or os.environ.get("HOMECLAW_API_KEY") or "").strip()
    if not key:
        try:
            import yaml
            config_path = os.path.join(os.path.dirname(__file__), "..", "config", "core.yml")
            if os.path.isfile(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                key = (cfg.get("auth_api_key") or "").strip()
        except Exception:
            pass
    return url.rstrip("/"), key


def main() -> int:
    p = argparse.ArgumentParser(description="Test POST /api/user-message and GET /api/user-inbox")
    p.add_argument("--core-url", default=None, help="Core base URL (default: env HOMECLAW_CORE_URL or http://127.0.0.1:9000)")
    p.add_argument("--api-key", default=None, help="API key (default: env HOMECLAW_API_KEY or config/core.yml auth_api_key)")
    p.add_argument("--from", dest="from_user", default="AllenPeng", help="Sender user_id (default: AllenPeng)")
    p.add_argument("--to", dest="to_user", default="PengXiaoFeng", help="Recipient user_id (default: PengXiaoFeng)")
    p.add_argument("--text", default="Hello from test script", help="Message text")
    p.add_argument("--inbox", metavar="USER_ID", default=None, help="Only fetch inbox for this user_id (no send)")
    args = p.parse_args()

    base_url, api_key = get_core_url_and_key(args.core_url, args.api_key)
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"

    if args.inbox:
        # GET /api/user-inbox
        url = f"{base_url}/api/user-inbox"
        params = {"user_id": args.inbox, "limit": 20}
        print(f"GET {url}?user_id={args.inbox}&limit=20")
        try:
            r = httpx.get(url, params=params, headers=headers, timeout=30)
            print(f"Status: {r.status_code}")
            data = r.json()
            messages = data.get("messages") or []
            print(f"Messages: {len(messages)}")
            for m in messages:
                print(f"  - from {m.get('from_user_name', m.get('from_user_id', '?'))}: {m.get('text', '')[:80]}")
            return 0 if r.status_code == 200 else 1
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # POST /api/user-message
    url = f"{base_url}/api/user-message"
    body = {
        "from_user_id": args.from_user,
        "to_user_id": args.to_user,
        "text": args.text,
    }
    print(f"POST {url}")
    print(f"  from_user_id={args.from_user}, to_user_id={args.to_user}, text={args.text[:50]}...")
    try:
        r = httpx.post(url, json=body, headers=headers, timeout=30)
        print(f"Status: {r.status_code}")
        data = r.json()
        if r.status_code == 200:
            print(f"OK message_id={data.get('message_id', '?')}")
        else:
            print(f"Error: {data.get('error', r.text)}")
        return 0 if r.status_code == 200 else 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
