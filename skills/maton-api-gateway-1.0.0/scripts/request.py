#!/usr/bin/env python3
"""
Maton API Gateway request script for run_skill.

This script is service-agnostic: it forwards (app, path, method, body) to
https://gateway.maton.ai/{app}/{path} with the same API key for every service.
The skill's references/ folder (and Supported Services table in SKILL.md) tell
the model the correct app name and path for each service (Slack, HubSpot,
Outlook, Notion, etc.); request.py does not need to know them.

Usage: request.py <app> <path> [method] [body_json] [connection_id]
  app   - Service name from Supported Services (e.g. slack, hubspot, outlook, notion, google-mail)
  path  - Native API path for that service (e.g. api/chat.postMessage, v1.0/me/messages, crm/v3/objects/contacts)
  method - GET (default), POST, PUT, PATCH, DELETE
  body_json - Optional JSON string for request body (for POST/PUT/PATCH)
  connection_id - Optional; set Maton-Connection header when multiple connections exist

API key: MATON_API_KEY env, or this skill's config.yml (maton_api_key). Env overrides config.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _skill_root() -> Path:
    """Skill folder containing config.yml and scripts/."""
    return Path(__file__).resolve().parent.parent


def _get_api_key() -> str:
    """API key from (1) MATON_API_KEY env, (2) skill config.yml (maton_api_key). Env overrides."""
    key = (os.environ.get("MATON_API_KEY") or "").strip()
    if key:
        return key
    config_yml = _skill_root() / "config.yml"
    if config_yml.is_file():
        try:
            import yaml
            with open(config_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            key = (data.get("maton_api_key") or "").strip()
            if key:
                return key
        except Exception:
            pass
    return ""


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: request.py <app> <path> [method] [body_json] [connection_id]", file=sys.stderr)
        return 1
    app = sys.argv[1].strip()
    path = sys.argv[2].strip()
    method = (sys.argv[3].strip().upper() if len(sys.argv) > 3 else "GET") or "GET"
    body_json = sys.argv[4].strip() if len(sys.argv) > 4 else None
    connection_id = sys.argv[5].strip() if len(sys.argv) > 5 else None

    key = _get_api_key()
    if not key:
        print(
            "Error: Maton API key not set. Set MATON_API_KEY in env or maton_api_key in "
            "skills/maton-api-gateway-1.0.0/config.yml. Get key at https://www.maton.ai/settings",
            file=sys.stderr,
        )
        return 1

    base = "https://gateway.maton.ai"
    url = f"{base.rstrip('/')}/{app.strip('/')}/{path.lstrip('/')}"

    data = None
    if body_json and method in ("POST", "PUT", "PATCH"):
        try:
            data = body_json.encode("utf-8")
        except Exception:
            data = body_json.encode("utf-8", errors="replace")

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    if data:
        req.add_header("Content-Type", "application/json")
    if connection_id:
        req.add_header("Maton-Connection", connection_id)
    if app.lower() == "linkedin":
        req.add_header("LinkedIn-Version", "202506")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                out = json.loads(raw)
                print(json.dumps(out, indent=2))
            except json.JSONDecodeError:
                print(raw)
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {e.reason}\n{body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
