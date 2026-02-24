#!/usr/bin/env python3
"""
X (Twitter) API v2 request script for run_skill.

Supports:
  post <text>     — POST /2/tweets (create tweet)
  get [max_results] — GET /2/users/me/tweets (user timeline, default 10, max 100)

Token: X_ACCESS_TOKEN env, or this skill's config.yml (x_access_token). Env overrides config.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_token() -> str:
    """Token from (1) X_ACCESS_TOKEN env, (2) skill config.yml (x_access_token). Env overrides."""
    token = (os.environ.get("X_ACCESS_TOKEN") or "").strip()
    if token:
        return token
    config_yml = _skill_root() / "config.yml"
    if config_yml.is_file():
        try:
            import yaml
            with open(config_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            token = (data.get("x_access_token") or "").strip()
            if token:
                return token
        except Exception:
            pass
    return ""


def _request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> int:
    base = "https://api.twitter.com/2"
    url = f"{base.rstrip('/')}/{path.lstrip('/')}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                out = json.loads(raw)
                print(json.dumps(out, indent=2))
            except json.JSONDecodeError:
                print(raw)
        return 0
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {e.reason}\n{err_body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> int:
    global token
    token = _get_token()
    if not token:
        print(
            "Error: X access token not set. Set X_ACCESS_TOKEN in env or x_access_token in "
            "config/skills/x-api-1.0.0/config.yml. Get token at https://developer.x.com",
            file=sys.stderr,
        )
        return 1

    if len(sys.argv) < 2:
        print("Usage: request.py post <text>  |  request.py get [max_results]", file=sys.stderr)
        return 1

    action = (sys.argv[1] or "").strip().lower()
    if action == "post":
        if len(sys.argv) < 3:
            print("Usage: request.py post <text>", file=sys.stderr)
            return 1
        text = sys.argv[2].strip()
        if len(text) > 280:
            print("Error: Tweet text must be 280 characters or less.", file=sys.stderr)
            return 1
        return _request("POST", "tweets", body={"text": text})
    if action == "get":
        max_results = 10
        if len(sys.argv) > 2:
            try:
                max_results = min(100, max(1, int(sys.argv[2])))
            except ValueError:
                pass
        # Get current user id first (GET /2/users/me), then their tweets
        try:
            req = urllib.request.Request(
                "https://api.twitter.com/2/users/me",
                method="GET",
            )
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                me = json.loads(resp.read().decode("utf-8"))
            user_id = (me.get("data") or {}).get("id")
            if not user_id:
                print("Error: Could not get user id from /users/me", file=sys.stderr)
                return 1
            return _request("GET", f"users/{user_id}/tweets", params={"max_results": max_results})
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {e.reason}\n{err_body}", file=sys.stderr)
            return 1

    print("Usage: request.py post <text>  |  request.py get [max_results]", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
