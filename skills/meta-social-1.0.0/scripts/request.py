#!/usr/bin/env python3
"""
Meta Social (Facebook Page + Instagram) request script for run_skill.

Supports:
  facebook post <page_id> <message>     — POST /{page-id}/feed
  instagram post <page_id> <image_url> [caption] — create media container then media_publish

Token: META_ACCESS_TOKEN env, or this skill's config.yml (meta_access_token). Env overrides config.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _get_token() -> str:
    """Token from (1) META_ACCESS_TOKEN env, (2) skill config.yml (meta_access_token). Env overrides."""
    token = (os.environ.get("META_ACCESS_TOKEN") or "").strip()
    if token:
        return token
    config_yml = _skill_root() / "config.yml"
    if config_yml.is_file():
        try:
            import yaml
            with open(config_yml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            token = (data.get("meta_access_token") or "").strip()
            if token:
                return token
        except Exception:
            pass
    return ""


BASE = "https://graph.facebook.com/v21.0"


def _graph_get(path: str, token: str, params: dict | None = None) -> dict:
    """GET Graph API; path relative; params + access_token in query."""
    url = f"{BASE}/{path.lstrip('/')}"
    params = dict(params or {})
    params["access_token"] = token
    url += "?" + urlencode(params)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _graph_post_json(path: str, token: str, body: dict) -> dict:
    """POST Graph API with JSON body; access_token in query."""
    url = f"{BASE}/{path.lstrip('/')}?{urlencode({'access_token': token})}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _graph_post(path: str, token: str, body: dict) -> dict:
    """POST with form-encoded body (message=...) for feed; Graph API often expects form."""
    url = f"{BASE}/{path.lstrip('/')}"
    data = urlencode({**body, "access_token": token}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    token = _get_token()
    if not token:
        print(
            "Error: Meta access token not set. Set META_ACCESS_TOKEN in env or meta_access_token in "
            "skills/meta-social-1.0.0/config.yml. Get token at https://developers.facebook.com",
            file=sys.stderr,
        )
        return 1

    if len(sys.argv) < 4:
        print(
            "Usage: request.py facebook post <page_id> <message>  |  request.py instagram post <page_id> <image_url> [caption]",
            file=sys.stderr,
        )
        return 1

    platform = (sys.argv[1] or "").strip().lower()
    action = (sys.argv[2] or "").strip().lower()

    if platform == "facebook" and action == "post":
        page_id = sys.argv[3].strip()
        message = sys.argv[4].strip() if len(sys.argv) > 4 else ""
        if not message:
            print("Error: message is required for facebook post.", file=sys.stderr)
            return 1
        try:
            out = _graph_post(f"{page_id}/feed", token, {"message": message})
            print(json.dumps(out, indent=2))
            return 0
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {e.reason}\n{err_body}", file=sys.stderr)
            return 1

    if platform == "instagram" and action == "post":
        page_id = sys.argv[3].strip()
        image_url = sys.argv[4].strip() if len(sys.argv) > 4 else ""
        caption = sys.argv[5].strip() if len(sys.argv) > 5 else ""
        if not image_url:
            print("Error: image_url is required for instagram post.", file=sys.stderr)
            return 1
        try:
            # 1) Get IG user id from Page
            me = _graph_get(f"{page_id}", token, params={"fields": "instagram_business_account"})
            ig_account = (me.get("instagram_business_account") or {}).get("id")
            if not ig_account:
                print(
                    "Error: Page has no linked Instagram Business account. Link IG in Page settings.",
                    file=sys.stderr,
                )
                return 1
            # 2) Create media container (JSON body)
            body = {"image_url": image_url}
            if caption:
                body["caption"] = caption
            container = _graph_post_json(f"{ig_account}/media", token, body)
            creation_id = container.get("id")
            if not creation_id:
                print("Error: Could not create media container.", file=sys.stderr)
                print(json.dumps(container, indent=2), file=sys.stderr)
                return 1
            # 3) Publish (POST with query params)
            publish_url = f"{BASE}/{ig_account}/media_publish?{urlencode({'access_token': token, 'creation_id': creation_id})}"
            req = urllib.request.Request(publish_url, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            print(json.dumps(out, indent=2))
            return 0
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            print(f"HTTP {e.code}: {e.reason}\n{err_body}", file=sys.stderr)
            return 1

    print(
        "Usage: request.py facebook post <page_id> <message>  |  request.py instagram post <page_id> <image_url> [caption]",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
