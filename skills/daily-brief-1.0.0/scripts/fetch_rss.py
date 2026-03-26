#!/usr/bin/env python3
"""
Daily Brief — fetch headlines from configured RSS feeds (no API key).

Usage:
  python fetch_rss.py list
  python fetch_rss.py fetch [--max N] [--lang en|cn|all] [--filter KEYWORD]
  python fetch_rss.py fetch-vmprint [--max N] [--lang en|cn|all] [--filter KEYWORD]

Examples:
  python fetch_rss.py fetch --max 20 --lang cn
  python fetch_rss.py fetch --max 30 --lang all --filter AI
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import feedparser
except ImportError:
    print(
        "Error: feedparser is not installed.\n"
        "  pip install -r skills/daily-brief-1.0.0/requirements.txt\n"
        "  (or: pip install feedparser)",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# Fetch limits (avoid hangs and huge downloads)
_DEFAULT_TIMEOUT_SEC = 25
_MAX_FEED_BYTES = 5_000_000  # 5 MiB per feed
_MAX_OUTPUT_ITEMS = 100  # hard cap for --max
_USER_AGENT = "HomeClaw-daily-brief/1.0 (+https://github.com/allenpeng0705/HomeClaw)"


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_feeds() -> List[Dict[str, Any]]:
    path = _skill_root() / "config" / "feeds.yaml"
    if not path.is_file():
        return []
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"Error: cannot read {path}: {e}", file=sys.stderr)
        return []
    if yaml is None:
        return []
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        print(f"Error: invalid YAML in feeds.yaml: {e}", file=sys.stderr)
        return []
    feeds = data.get("feeds") or []
    if not isinstance(feeds, list):
        return []
    out: List[Dict[str, Any]] = []
    for f in feeds:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "").strip() or "feed"
        url = str(f.get("url") or "").strip()
        lang = str(f.get("lang") or "en").strip().lower()
        if not url:
            continue
        if len(url) > 2048:
            continue
        if lang not in ("en", "cn"):
            lang = "en"
        out.append({"name": name, "url": url, "lang": lang})
    return out


def _is_allowed_feed_url(url: str) -> bool:
    """Only http(s); block obvious SSRF / local targets from feeds.yaml mistakes."""
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return False
    if host in ("127.0.0.1", "::1", "0.0.0.0"):
        return False
    if host.startswith("127."):
        return False
    if host == "metadata.google.internal":  # common SSRF probe
        return False
    return True


def _read_body_limited(resp: Any, max_bytes: int) -> bytes:
    chunks: List[bytes] = []
    total = 0
    while total < max_bytes:
        chunk = resp.read(min(65536, max_bytes - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _fetch_feed_bytes(url: str, timeout_sec: int = _DEFAULT_TIMEOUT_SEC) -> Tuple[Optional[bytes], Optional[str]]:
    """Download feed body with timeout and size cap. Returns (body, error_message)."""
    if not _is_allowed_feed_url(url):
        return None, "URL not allowed (use http/https only; local URLs blocked)"
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=timeout_sec) as resp:
            data = _read_body_limited(resp, _MAX_FEED_BYTES)
    except HTTPError as e:
        reason = getattr(e, "reason", None) or str(e)
        return None, f"HTTP {e.code}: {reason}"
    except URLError as e:
        return None, f"network error: {e.reason!r}"
    except OSError as e:
        return None, f"IO error: {e}"
    except Exception as e:
        return None, f"fetch error: {e}"
    if len(data) >= _MAX_FEED_BYTES:
        return data, f"truncated at {_MAX_FEED_BYTES} bytes"
    return data, None


def _entry_date(entry: Any) -> Optional[datetime]:
    """
    Best-effort parse published/updated date from feedparser entry.
    """
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            t = entry.published_parsed
            return datetime(
                t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, tzinfo=timezone.utc
            )
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            t = entry.updated_parsed
            return datetime(
                t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec, tzinfo=timezone.utc
            )
    except Exception:
        pass
    return None


def _strip_html(s: str) -> str:
    if not s:
        return ""
    t = re.sub(r"<[^>]+>", " ", s)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _one_line(s: str, max_len: int = 500) -> str:
    """Avoid breaking Markdown / logs when titles contain newlines or control chars."""
    if not s:
        return ""
    t = s.replace("\r", " ").replace("\n", " ")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    t = t.strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _fetch_one_feed(meta: Dict[str, Any], max_per_feed: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (items, warning_messages). Warnings include fetch/truncation/bozo soft errors."""
    url = meta["url"]
    name = meta["name"]
    lang = meta["lang"]
    warnings: List[str] = []

    body, fetch_err = _fetch_feed_bytes(url)
    if body is None:
        return [], [f"{name}: {fetch_err or 'empty response'}"]
    if fetch_err:
        warnings.append(f"{name}: {fetch_err}")

    try:
        parsed = feedparser.parse(body)
    except Exception as e:
        return [], [f"{name}: parse error: {e}"]

    bozo = getattr(parsed, "bozo_exception", None)
    entries = list(getattr(parsed, "entries", []) or [])
    if bozo and not entries:
        return [], [f"{name}: {bozo}"]
    if bozo and entries:
        warnings.append(f"{name}: feed had XML warnings ({bozo}); still using {len(entries)} entries")

    items: List[Dict[str, Any]] = []
    entries = entries[:max_per_feed]
    for e in entries:
        try:
            title_raw = str(getattr(e, "title", "") or "")
            title = _one_line(_strip_html(title_raw), 400) or "(no title)"
            link = ""
            if getattr(e, "link", None):
                link = str(e.link).strip()
            elif getattr(e, "links", None):
                for L in e.links:
                    if isinstance(L, dict) and L.get("rel") == "alternate" and L.get("href"):
                        link = str(L["href"]).strip()
                        break
            if not link:
                continue
            if not _is_allowed_feed_url(link):
                continue
            summary = _one_line(_strip_html(str(getattr(e, "summary", "") or getattr(e, "description", "") or "")), 500)
            dt = _entry_date(e)
            items.append(
                {
                    "feed": name,
                    "feed_lang": lang,
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": dt.isoformat() if dt else "",
                }
            )
        except Exception:
            continue

    if not items and entries:
        warnings.append(f"{name}: no usable entries (missing links after filter)")
    return items, warnings


def cmd_list() -> int:
    if yaml is None:
        print("Error: PyYAML is required (HomeClaw includes PyYAML in requirements.txt).", file=sys.stderr)
        return 1
    feeds = _load_feeds()
    if not feeds:
        print("No feeds configured (feeds.yaml missing, empty, or invalid).", file=sys.stderr)
        return 1
    lines = ["Configured RSS feeds:\n"]
    for f in feeds:
        lines.append(f"- [{f['lang']}] {f['name']}: {f['url']}")
    print("\n".join(lines))
    return 0


def _build_digest(args: argparse.Namespace) -> Optional[Tuple[List[Dict[str, Any]], List[str], str, int, str]]:
    feeds = _load_feeds()
    if not feeds:
        print("Error: no feeds in config/feeds.yaml (missing, empty, or invalid YAML).", file=sys.stderr)
        return None

    lang_filter = (args.lang or "all").strip().lower()
    if lang_filter not in ("en", "cn", "all"):
        lang_filter = "all"

    try:
        max_total = int(args.max if args.max is not None else 30)
    except (TypeError, ValueError):
        max_total = 30
    max_total = max(1, min(max_total, _MAX_OUTPUT_ITEMS))

    active_feeds = [f for f in feeds if lang_filter == "all" or f["lang"] == lang_filter]
    if not active_feeds:
        print(
            f"Error: no feeds match --lang {lang_filter!r}. Check config/feeds.yaml or use --lang all.",
            file=sys.stderr,
        )
        return None

    n_active = len(active_feeds)
    per_feed = max(5, min(40, max_total // max(1, n_active) + 5))

    selected: List[Dict[str, Any]] = []
    errors: List[str] = []
    for meta in active_feeds:
        items, warns = _fetch_one_feed(meta, per_feed)
        errors.extend(warns)
        selected.extend(items)

    kw = (args.filter or "").strip().lower()
    if kw:
        filtered: List[Dict[str, Any]] = []
        for it in selected:
            blob = f"{it.get('title','')} {it.get('summary','')}".lower()
            if kw in blob:
                filtered.append(it)
        selected = filtered

    # Sort by date (newest first) within the pool, then de-dupe by link
    seen = set()
    pool: List[Dict[str, Any]] = []
    for it in sorted(
        selected,
        key=lambda x: (x.get("published") or "", x.get("title") or ""),
        reverse=True,
    ):
        link = it.get("link") or ""
        if not link or link in seen:
            continue
        seen.add(link)
        pool.append(it)

    # Interleave by feed name so one high-volume source does not dominate
    by_feed: Dict[str, List[Dict[str, Any]]] = {}
    for it in pool:
        key = str(it.get("feed") or "unknown")
        by_feed.setdefault(key, []).append(it)

    deduped: List[Dict[str, Any]] = []
    feeds_order = list(by_feed.keys())
    idx_map = {k: 0 for k in feeds_order}
    while len(deduped) < max_total and any(idx_map[k] < len(by_feed[k]) for k in feeds_order):
        for k in feeds_order:
            if len(deduped) >= max_total:
                break
            arr = by_feed[k]
            i = idx_map[k]
            if i < len(arr):
                deduped.append(arr[i])
                idx_map[k] = i + 1

    return (deduped, errors, lang_filter, n_active, kw)


def cmd_fetch(args: argparse.Namespace) -> int:
    digest = _build_digest(args)
    if digest is None:
        return 1
    deduped, errors, lang_filter, n_active, kw = digest

    # Markdown output for chat / LLM post-processing
    lines: List[str] = []
    lines.append("# Daily Brief (RSS)")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Language filter: {lang_filter}")
    lines.append(f"- Feeds used: {n_active}")
    if kw:
        lines.append(f"- Title/summary filter: {kw}")
    lines.append(f"- Items: {len(deduped)}")
    lines.append("")
    if errors:
        lines.append("## Feed warnings")
        for e in errors[:20]:
            lines.append(f"- {_one_line(e, 300)}")
        lines.append("")
    if not deduped:
        lines.append(
            "_No items after filters or all feeds failed. Try --lang all, remove --filter, "
            "check network, or edit config/feeds.yaml._"
        )
        print("\n".join(lines))
        return 0

    lines.append("## Headlines")
    lines.append("")
    for it in deduped:
        feed_name = _one_line(str(it.get("feed") or ""), 120)
        fl = _one_line(str(it.get("feed_lang") or ""), 8)
        title = _one_line(str(it.get("title") or ""), 400)
        link = str(it.get("link") or "").strip()
        lines.append(f"- **{feed_name}** [{fl}]")
        lines.append(f"  - **{title}**")
        lines.append(f"  - {link}")
        if it.get("summary"):
            lines.append(f"  - _{_one_line(_strip_html(str(it['summary'])), 240)}_")
        if it.get("published"):
            lines.append(f"  - _{it['published']}_")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("JSON (machine-readable):")
    lines.append("```json")
    try:
        json_blob = json.dumps(
            {"items": deduped, "errors": errors[:50]},
            ensure_ascii=False,
            indent=2,
        )
    except (TypeError, ValueError) as e:
        json_blob = json.dumps({"error": f"json encode failed: {e}", "items": [], "errors": errors[:20]})
    lines.append(json_blob)
    lines.append("```")
    print("\n".join(lines))
    return 0


def cmd_fetch_vmprint(args: argparse.Namespace) -> int:
    digest = _build_digest(args)
    if digest is None:
        return 1
    deduped, errors, lang_filter, n_active, kw = digest

    root = Path(__file__).resolve().parents[3]
    renderer = root / "skills" / "magazine-render-1.0.0" / "scripts" / "render_magazine.py"
    if not renderer.is_file():
        print("Error: magazine-render script not found.", file=sys.stderr)
        return 1

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "items": [
            {
                "title": str(it.get("title") or "").strip(),
                "source": str(it.get("feed") or "").strip(),
                "link": str(it.get("link") or "").strip(),
            }
            for it in deduped
        ],
        "meta": {"lang": lang_filter, "feeds_used": n_active, "filter": kw or "", "warnings": errors[:20]},
    }
    out_name = f"daily_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.preview.html"
    cmd = [
        sys.executable,
        str(renderer),
        "render-daily-brief-ast",
        "--title",
        "Daily Brief",
        "--theme",
        str(args.theme or "dispatch"),
        "--json",
        json.dumps(payload, ensure_ascii=False),
        "--output_format",
        str(args.output_format or "browser_preview_html"),
        "--out",
        out_name,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as e:
        print(f"Error: vmprint render launch failed: {e}", file=sys.stderr)
        return 1
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip() or "unknown error"
        print(f"Error: vmprint render failed: {msg}", file=sys.stderr)
        return 1

    out = (r.stdout or "").strip()
    if not out:
        print("Error: vmprint render returned empty output.", file=sys.stderr)
        return 1

    # Keep run_skill link append stable: emit JSON with output_rel_path when available.
    parsed: Optional[Dict[str, Any]] = None
    for ln in reversed([ln for ln in out.splitlines() if ln.strip()]):
        try:
            obj = json.loads(ln)
            if isinstance(obj, dict) and obj.get("success") and obj.get("output_rel_path"):
                parsed = obj
                break
        except Exception:
            continue
    if parsed is None:
        print(out)
        return 0
    print(json.dumps(parsed, ensure_ascii=False))
    return 0


def main() -> int:
    if yaml is None:
        print("Error: PyYAML is required (HomeClaw includes PyYAML in requirements.txt).", file=sys.stderr)
        return 1

    p = argparse.ArgumentParser(description="Daily Brief RSS fetcher")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List configured RSS feeds")

    pf = sub.add_parser("fetch", help="Fetch and merge headlines")
    pf.add_argument(
        "--max",
        type=int,
        default=30,
        help=f"Max items after merge (default 30, cap {_MAX_OUTPUT_ITEMS})",
    )
    pf.add_argument("--lang", type=str, default="all", help="en | cn | all")
    pf.add_argument("--filter", type=str, default="", help="Keyword filter (title/summary substring)")

    pvp = sub.add_parser("fetch-vmprint", help="Fetch digest then render VMPrint preview artifact")
    pvp.add_argument(
        "--max",
        type=int,
        default=20,
        help=f"Max items after merge (default 20, cap {_MAX_OUTPUT_ITEMS})",
    )
    pvp.add_argument("--lang", type=str, default="all", help="en | cn | all")
    pvp.add_argument("--filter", type=str, default="", help="Keyword filter (title/summary substring)")
    pvp.add_argument("--theme", type=str, default="dispatch", help="dispatch | minimal")
    pvp.add_argument(
        "--output_format",
        type=str,
        default="browser_preview_html",
        choices=["browser_preview_html", "pdf", "layout_json"],
        help="VMPrint output format (default browser_preview_html).",
    )

    args = p.parse_args()
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "fetch-vmprint":
        return cmd_fetch_vmprint(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
