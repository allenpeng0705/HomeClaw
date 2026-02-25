#!/usr/bin/env python3
"""
Download all reference .md files from maton-ai/api-gateway-skill/references into
this skill's references/ folder. Run from repo root or from this script's directory.

Usage: python sync_references.py
"""
import json
import sys
import urllib.request
from pathlib import Path

REPO = "maton-ai/api-gateway-skill"
REF = "main"
API_LIST = f"https://api.github.com/repos/{REPO}/contents/references"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{REF}/references"


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    skill_root = script_dir.parent
    ref_dir = skill_root / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(API_LIST)
        req.add_header("Accept", "application/vnd.github.v3+json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            items = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Failed to list references: {e}", file=sys.stderr)
        return 1

    count = 0
    for item in items:
        if item.get("type") != "file" or not item.get("name", "").endswith(".md"):
            continue
        name = item["name"]
        url = f"{RAW_BASE}/{name}"
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            out_path = ref_dir / name
            out_path.write_text(body, encoding="utf-8")
            count += 1
            print(f"  {name}")
        except Exception as e:
            print(f"  {name}: {e}", file=sys.stderr)

    print(f"Synced {count} reference files to {ref_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
