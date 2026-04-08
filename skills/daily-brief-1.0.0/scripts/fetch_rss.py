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
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


def _fetch_feed_bytes(
    url: str, timeout_sec: int = _DEFAULT_TIMEOUT_SEC
) -> Tuple[Optional[bytes], Optional[str], Optional[Dict[str, str]]]:
    """
    Download feed body with timeout and size cap.
    Returns (body, error_message, response_headers_for_feedparser).

    Headers are passed to feedparser so charset from Content-Type can match HTTP (reduces mojibake
    when XML encoding and HTTP disagree).
    """
    if not _is_allowed_feed_url(url):
        return None, "URL not allowed (use http/https only; local URLs blocked)", None
    try:
        req = Request(url, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=timeout_sec) as resp:
            data = _read_body_limited(resp, _MAX_FEED_BYTES)
            hdrs = {str(k).lower(): str(v) for k, v in resp.headers.items()}
    except HTTPError as e:
        reason = getattr(e, "reason", None) or str(e)
        return None, f"HTTP {e.code}: {reason}", None
    except URLError as e:
        return None, f"network error: {e.reason!r}", None
    except OSError as e:
        return None, f"IO error: {e}", None
    except Exception as e:
        return None, f"fetch error: {e}", None
    if len(data) >= _MAX_FEED_BYTES:
        return data, f"truncated at {_MAX_FEED_BYTES} bytes", hdrs
    return data, None, hdrs


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


def _detail_value_plain(detail: Any) -> str:
    if detail is None:
        return ""
    v = getattr(detail, "value", None)
    if v is None and isinstance(detail, dict):
        v = detail.get("value")
    return _strip_html(str(v or ""))


def _entry_summary_excerpt(entry: Any, max_len: int = 500) -> str:
    """
    Plain-text excerpt for magazine Snippet column: use RSS description / Atom summary first,
    then the first content block (e.g. RSS content:encoded) when the feed omits a short summary.
    """
    raw = str(getattr(entry, "summary", "") or getattr(entry, "description", "") or "")
    plain = _strip_html(raw)
    if not plain.strip():
        plain = _detail_value_plain(getattr(entry, "summary_detail", None))
    if not plain.strip():
        plain = _detail_value_plain(getattr(entry, "subtitle_detail", None))
    if plain.strip():
        return _one_line(plain, max_len)
    for block in getattr(entry, "content", None) or []:
        if isinstance(block, dict):
            val = block.get("value")
            if val:
                t = _strip_html(str(val))
                if t.strip():
                    return _one_line(t, max_len)
    return ""


def _fetch_one_feed(meta: Dict[str, Any], max_per_feed: int) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Return (items, warning_messages). Warnings include fetch/truncation/bozo soft errors."""
    url = meta["url"]
    name = meta["name"]
    lang = meta["lang"]
    warnings: List[str] = []

    body, fetch_err, resp_headers = _fetch_feed_bytes(url)
    if body is None:
        return [], [f"{name}: {fetch_err or 'empty response'}"]
    if fetch_err:
        warnings.append(f"{name}: {fetch_err}")

    try:
        parsed = feedparser.parse(body, response_headers=resp_headers or None)
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
            summary = _entry_summary_excerpt(e, 500)
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
    try:
        days_ago = int(getattr(args, "days_ago", 0) or 0)
    except (TypeError, ValueError):
        days_ago = 0
    days_ago = max(0, min(7, days_ago))

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
    if days_ago > 0:
        target_day = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date()
        day_filtered: List[Dict[str, Any]] = []
        for it in selected:
            pub = str(it.get("published") or "").strip()
            if not pub:
                continue
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if dt.date() == target_day:
                    day_filtered.append(it)
            except Exception:
                continue
        selected = day_filtered

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


def _digest_markdown_body(
    deduped: List[Dict[str, Any]],
    errors: List[str],
    lang_filter: str,
    n_active: int,
    kw: str,
    *,
    vmprint_fallback: bool = False,
    vmprint_render_error: str = "",
) -> str:
    """
    Human-readable RSS digest (same as cmd_fetch headline section).
    Used by fetch-vmprint on success so chat shows headlines, not only the file-link JSON.
    Intentionally omits a ```json fenced block so Core does not auto-chain a second magazine-render.
    """
    lines: List[str] = []
    lines.append("# Daily Brief (RSS)")
    lines.append("")
    if vmprint_fallback:
        lines.append(_vmprint_fallback_stdout_prologue(vmprint_render_error))
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
        return "\n".join(lines)
    lines.append("## Headlines")
    lines.append("")
    for it in deduped:
        feed_name = _one_line(str(it.get("feed") or ""), 120)
        fl = _one_line(str(it.get("feed_lang") or ""), 8)
        title = _one_line(str(it.get("title") or ""), 400)
        link = str(it.get("link") or "").strip()
        lines.append(f"- **{feed_name}** [{fl}]")
        if link.startswith(("http://", "https://")) and title:
            lines.append(f"  - **[{title}]({link})**")
        else:
            lines.append(f"  - **{title}**")
            if link:
                lines.append(f"  - {link}")
        if it.get("summary"):
            lines.append(f"  - _{_one_line(_strip_html(str(it['summary'])), 240)}_")
        if it.get("published"):
            lines.append(f"  - _{it['published']}_")
        lines.append("")
    return "\n".join(lines)


def _vmprint_fallback_stdout_prologue(render_error_excerpt: str) -> str:
    """Shown at top of Markdown when fetch-vmprint could not produce HTML/PDF (so chat/UI see why)."""
    ex = _one_line(render_error_excerpt.replace("`", "'"), 420).strip() if render_error_excerpt else ""
    parts = [
        "> **Magazine (VMPrint) preview did not run.** Headlines below are plain Markdown (same RSS digest).",
        "> — Core needs **Node** on PATH; from HomeClaw repo root: `test -f tools/vmprint/cli/dist/index.js` "
        "and `node tools/vmprint/cli/dist/index.js --help`.",
        "> — If that fails: `cd tools/vmprint && npm install && npm run build`, then retry the `node ... --help` check.",
    ]
    if ex:
        parts.append(f"> — Render stderr (excerpt): {ex}")
    return "\n".join(parts)


def cmd_fetch(args: argparse.Namespace, *, vmprint_fallback: bool = False, vmprint_render_error: str = "") -> int:
    digest = _build_digest(args)
    if digest is None:
        return 1
    deduped, errors, lang_filter, n_active, kw = digest

    head = _digest_markdown_body(
        deduped,
        errors,
        lang_filter,
        n_active,
        kw,
        vmprint_fallback=vmprint_fallback,
        vmprint_render_error=vmprint_render_error,
    )
    if not deduped:
        print(head)
        return 0

    lines = [head, "---", "", "JSON (machine-readable):", "```json"]
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


def _magazine_render_failure_kind(text: str) -> str:
    """
    Classify magazine-render stderr for fallback + user-facing note.
    Returns: 'install' (missing tree / not built / no node), 'runtime' (CLI ran but crashed),
    'vmprint_other' (mentions vmprint but not install-specific), or '' (do not auto-fallback).

    Order: runtime before install — upstream errors often say "run npm install" in remediation text,
    which must not force the "not installed" user note.
    """
    m = (text or "").strip()
    if not m:
        return ""
    ml = m.lower()
    runtime_markers = (
        "vmprint layout emit failed",
        "layout emit failed",
        "err_invalid_arg_type",
        "vmprint render failed",
        "vmprint ast render failed",
        "vmprint canvas preview failed",
        "fileurltopath",
        "typeerror",
        "referenceerror",
        "syntaxerror",
    )
    # Tight: do not use bare "npm install" / "no such file" — they appear inside normal stack traces and hints.
    install_markers = (
        "vmprint not found",
        "expected tools/vmprint",
        "vmprint directory missing",
        "cli not built at",
        "draft2final cli not built",
        "node.js is not available",
        "node is not available",
        "node not found",
        "magazine-render script not found",
        "cannot find module '@vmprint",
        "cannot find module '@draft2final",
    )
    if any(x in ml for x in runtime_markers):
        return "runtime"
    if any(x in ml for x in install_markers):
        return "install"
    if "vmprint" in ml or "draft2final" in ml:
        return "vmprint_other"
    return ""


def _should_fallback_fetch_vmprint_to_markdown(msg: str) -> bool:
    """True when we still deliver RSS as Markdown instead of failing the whole command."""
    return bool(_magazine_render_failure_kind(msg))


def _layout_from_user_message(msg: str) -> str:
    """Best-effort mapping from user phrasing to fetch-vmprint document layout."""
    q = (msg or "").strip()
    if not q:
        return ""
    q_lo = q.lower()
    if any(
        k in q
        for k in (
            "报纸排版",
            "报纸版式",
            "头版",
            "新闻报纸",
        )
    ) or any(
        k in q_lo
        for k in (
            "newspaper layout",
            "front page layout",
            "broadsheet layout",
            "broadsheet",
        )
    ):
        return "newspaper"
    if any(
        k in q
        for k in (
            "杂志排版",
            "杂志版式",
            "杂志布局",
            "杂志格式",
            "杂志样式",
            "杂志风",
        )
    ) or any(
        k in q_lo
        for k in (
            "magazine layout",
            "folio layout",
            "real magazine",
            "editorial layout",
            "magazine format",
        )
    ):
        return "magazine"
    return ""


def _log_fetch_vmprint_fallback(reason: str, detail: str) -> None:
    """One-line reason + excerpt so Core logs show the real magazine-render/VMPrint failure."""
    print(f"daily-brief: fetch-vmprint fell back to Markdown ({reason}).", file=sys.stderr)
    d = (detail or "").strip().replace("\r", " ")
    if not d:
        return
    d = _one_line(d, 2000)
    print(f"daily-brief: magazine-render/VMPrint detail (excerpt): {d}", file=sys.stderr)


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

    items_out = [
        {
            "title": str(it.get("title") or "").strip(),
            "feed": str(it.get("feed") or "").strip(),
            "source": str(it.get("feed") or "").strip(),
            "link": str(it.get("link") or "").strip(),
            "summary": str(it.get("summary") or "").strip(),
        }
        for it in deduped
    ]
    # Empty digest still produced a valid VMPrint artifact before; users saw a blank magazine. Surface why.
    if not items_out:
        err_hint = "; ".join(_one_line(str(e), 200) for e in errors[:8]) if errors else ""
        if not err_hint.strip():
            err_hint = (
                "All feeds returned no headlines (timeout, HTTP error, block, or parse failure). "
                "Check Core host network/DNS, try --lang all, or update config/feeds.yaml URLs."
            )
        long_title = f"(No articles retrieved) {err_hint}"
        if len(long_title) > 900:
            long_title = long_title[:897] + "..."
        items_out = [
            {
                "title": long_title,
                "feed": "daily-brief",
                "source": "daily-brief",
                "link": "",
                "summary": "",
            },
        ]
    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "items": items_out,
        "meta": {
            "lang": lang_filter,
            "feeds_used": n_active,
            "filter": kw or "",
            "warnings": errors[:20],
            "empty_digest": not bool(deduped),
        },
    }
    out_name = f"daily_brief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.preview.html"
    try:
        print(
            f"daily-brief: fetch-vmprint using document_layout={getattr(args, 'document_layout', 'digest_table')}",
            file=sys.stderr,
        )
    except Exception:
        pass
    cmd = [
        sys.executable,
        str(renderer),
        "render-daily-brief-ast",
        "--title",
        "Daily Brief",
        "--theme",
        str(args.theme or "dispatch"),
        "--document-layout",
        str(getattr(args, "document_layout", "digest_table") or "digest_table"),
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
        el = str(e)
        k = _magazine_render_failure_kind(el)
        if k:
            _log_fetch_vmprint_fallback("could not launch magazine render", el)
            return cmd_fetch(args, vmprint_fallback=True, vmprint_render_error=el)
        print(f"Error: vmprint render launch failed: {e}", file=sys.stderr)
        return 1
    if r.returncode != 0:
        msg = (r.stderr or r.stdout or "").strip() or "unknown error"
        if _should_fallback_fetch_vmprint_to_markdown(msg):
            _log_fetch_vmprint_fallback("VMPrint render failed", msg)
            return cmd_fetch(args, vmprint_fallback=True, vmprint_render_error=msg)
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
    # VMPrint path used to print only {"success","output_rel_path"} — RSS looked "missing" in chat vs Markdown fallback.
    print(_digest_markdown_body(deduped, errors, lang_filter, n_active, kw))
    print("")
    print("**Magazine preview:** use the file link in the JSON line below (open in browser).")
    print("")
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
    pf.add_argument("--days-ago", type=int, default=0, help="0=today/latest (default), 1=yesterday, max 7")

    pvp = sub.add_parser("fetch-vmprint", help="Fetch digest then render VMPrint preview artifact")
    pvp.add_argument(
        "--max",
        type=int,
        default=20,
        help=f"Max items after merge (default 20, cap {_MAX_OUTPUT_ITEMS})",
    )
    pvp.add_argument("--lang", type=str, default="all", help="en | cn | all")
    pvp.add_argument("--filter", type=str, default="", help="Keyword filter (title/summary substring)")
    pvp.add_argument("--days-ago", type=int, default=0, help="0=today/latest (default), 1=yesterday, max 7")
    pvp.add_argument("--theme", type=str, default="dispatch", help="dispatch | minimal")
    pvp.add_argument(
        "--output_format",
        type=str,
        default="browser_preview_html",
        choices=["browser_preview_html", "pdf", "layout_json"],
        help="VMPrint output format (default browser_preview_html).",
    )
    pvp.add_argument(
        "--document-layout",
        type=str,
        default="digest_table",
        choices=["digest_table", "magazine", "newspaper"],
        help="digest_table: index table (default). magazine: lead+rail. newspaper: masthead + sections + index.",
    )

    args = p.parse_args()
    # Safety net: when upstream run_skill normalization misses document layout in argv,
    # still honor explicit user phrasing (e.g. "杂志格式") from env injected by Core.
    try:
        if args.cmd == "fetch-vmprint":
            uq = (
                (os.environ.get("HOMECLAW_USER_MESSAGE") or "").strip()
                or (os.environ.get("HOMECLAW_INPUT_MESSAGE") or "").strip()
            )
            want = _layout_from_user_message(uq)
            if want:
                args.document_layout = want
    except Exception:
        pass
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "fetch-vmprint":
        return cmd_fetch_vmprint(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
