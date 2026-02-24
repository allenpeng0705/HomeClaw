#!/usr/bin/env python3
"""
Hootsuite Publishing API request script for run_skill.

Supports:
  list                    — GET /v1/socialProfiles (list profile IDs and types)
  post <profile_id> <text> [scheduledSendTime] — POST /v1/messages (schedule; time optional, default now+5min UTC)

Profile ID can be comma-separated for multiple: post id1,id2 "message".

Token: HOOTSUITE_ACCESS_TOKEN env, or this skill's config.yml (hootsuite_access_token). Env overrides config.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_token() -> str:
    """Token from (1) HOOTSUITE_ACCESS_TOKEN env, (2) skill config.yml (hootsuite_access_token). Env overrides."""
    token = (os.environ.get("HOOTSUITE_ACCESS_TOKEN") or "").strip()
    if token:
        return token
    config_yml = _skill_root() / "config.yml"
    if config_yml.is_file():
        try:
            import yaml
            with open(config_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            token = (data.get("hootsuite_access_token") or "").strip()
            if token:
                return token
        except Exception:
            pass
    return ""


BASE = "https://platform.hootsuite.com/v1"


def _request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = f"{BASE.rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json;charset=utf-8")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    token = _get_token()
    if not token:
        print(
            "Error: Hootsuite access token not set. Set HOOTSUITE_ACCESS_TOKEN in env or hootsuite_access_token in "
            "config/skills/hootsuite-1.0.0/config.yml. Get token at https://developer.hootsuite.com",
            file=sys.stderr,
        )
        return 1

    if len(sys.argv) < 2:
        print("Usage: request.py list  |  request.py post <profile_id> <text> [scheduledSendTime]", file=sys.stderr)
        return 1

    action = (sys.argv[1] or "").strip().lower()

    if action == "list":
        try:
            out = _request("GET", "socialProfiles", token)
            print(json.dumps(out, indent=2))
            return 0
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {e.reason}\n{err_body}", file=sys.stderr)
            return 1

    if action == "post":
        if len(sys.argv) < 4:
            print("Usage: request.py post <profile_id> <text> [scheduledSendTime]", file=sys.stderr)
            return 1
        profile_arg = sys.argv[2].strip()
        text = sys.argv[3].strip()
        scheduled_send_time = sys.argv[4].strip() if len(sys.argv) > 4 else None

        profile_ids = [p.strip() for p in profile_arg.split(",") if p.strip()]
        if not profile_ids:
            print("Error: At least one profile_id required.", file=sys.stderr)
            return 1

        if not scheduled_send_time:
            # Default: 5 minutes from now (API requires ≥5 min in future)
            t = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
            scheduled_send_time = t

        body = {
            "text": text,
            "socialProfileIds": [int(pid) if pid.isdigit() else pid for pid in profile_ids],
            "scheduledSendTime": scheduled_send_time,
            "emailNotification": False,
        }
        try:
            out = _request("POST", "messages", token, body=body)
            print(json.dumps(out, indent=2))
            return 0
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {e.reason}\n{err_body}", file=sys.stderr)
            return 1

    print("Usage: request.py list  |  request.py post <profile_id> <text> [scheduledSendTime]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
