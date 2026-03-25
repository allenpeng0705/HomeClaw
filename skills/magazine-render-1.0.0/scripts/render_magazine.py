#!/usr/bin/env python3
"""
Magazine renderer skill: Markdown/JSON -> VMPrint (draft2final) PDF saved under HOMECLAW_OUTPUT_DIR.

This script prints a single JSON line on success:

  {"success": true, "output_rel_path": "output/<file>.pdf", "message": "..."}

Core's run_skill wrapper appends the file view link automatically when configured.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _now_local_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _repo_root() -> Path:
    # skills/<skill>/scripts/<this_file>
    return Path(__file__).resolve().parents[3]


def _default_vmprint_dir(root: Path) -> Optional[Path]:
    for name in ("vmprint", "vm_print"):
        p = (root / "tools" / name).resolve()
        if p.is_dir() and (p / "draft2final").is_dir():
            return p
    return None


def _find_vmprint_cli(vmprint_dir: Path) -> Optional[Path]:
    cli = (vmprint_dir / "draft2final" / "dist" / "cli.js").resolve()
    return cli if cli.is_file() else None


def _sanitize_filename(name: str, default: str = "report.pdf") -> str:
    s = (name or "").strip()
    if not s:
        return default
    s = s.replace("\\", "/").split("/")[-1]
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("._-")
    if not s.lower().endswith(".pdf"):
        s = s + ".pdf"
    return s or default


def _sanitize_image_filename(name: str, default: str = "preview.png") -> str:
    s = (name or "").strip()
    if not s:
        return default
    s = s.replace("\\", "/").split("/")[-1]
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("._-")
    if not s.lower().endswith(".png"):
        s = s + ".png"
    return s or default


def _output_dirs() -> Tuple[Path, str]:
    out_env = (os.environ.get("HOMECLAW_OUTPUT_DIR") or "").strip()
    if out_env:
        return (Path(out_env).resolve(), "output/")
    root = _repo_root()
    return ((root / "output").resolve(), "output/")


def _ensure_text_arg(s: Optional[str], max_chars: int, name: str) -> str:
    s = (s or "").strip()
    if not s:
        raise ValueError(f"{name} is required.")
    if len(s) > max_chars:
        raise ValueError(f"{name} is too large ({len(s)} chars). Max is {max_chars}.")
    return s


def _json_loads_strict(s: str) -> Dict[str, Any]:
    obj = json.loads(s)
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object.")
    return obj


def _md_escape_inline(s: str) -> str:
    s = (s or "").strip().replace("\n", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _md_link(title: str, url: str) -> str:
    t = _md_escape_inline(title) or "link"
    u = (url or "").strip()
    if not u:
        return t
    u = u.replace(")", "%29").replace("(", "%28")
    return f"[{t}]({u})"


def _apply_theme_to_markdown(md: str, theme: str, title: str, as_of: Optional[str] = None) -> str:
    """
    Wrap or normalize Markdown into a consistent magazine-like layout.
    This is intentionally simple: VMPrint does the heavy lifting, we just keep structure stable.
    """
    theme = (theme or "").strip().lower() or "dispatch"
    body = (md or "").strip()
    as_of = (as_of or "").strip() or _now_local_str()

    if theme in ("dispatch", "daily_dispatch", "newspaper"):
        mast = (title or "THE DAILY DISPATCH").strip()
        mast = mast.upper()
        parts = [
            f"# {mast}",
            "",
            f"*As of {as_of}*",
            "",
            "---",
            "",
            body,
            "",
        ]
        return "\n".join([p for p in parts if p is not None]).strip() + "\n"

    if theme in ("minimal", "report"):
        mast = (title or "Report").strip()
        parts = [f"# {mast}", "", f"*As of {as_of}*", "", body, ""]
        return "\n".join(parts).strip() + "\n"

    raise ValueError("theme must be one of: dispatch, minimal")


def _maybe_generate_preview_png(pdf_path: Path, out_dir: Path, out_png_name: str) -> Optional[Path]:
    """
    Best-effort: generate a small PNG preview (first page).
    - macOS: qlmanage thumbnail
    - Linux/Windows (when installed): pdftoppm
    Returns absolute path to png on success.
    """
    if not pdf_path.is_file():
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    out_png = (out_dir / _sanitize_image_filename(out_png_name)).resolve()

    # 1) macOS QuickLook thumbnails
    try:
        r = subprocess.run(
            ["qlmanage", "-t", "-s", "1200", "-o", str(out_dir), str(pdf_path)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        # qlmanage writes <pdfname>.png into out_dir
        if r.returncode == 0:
            candidate = (out_dir / (pdf_path.name + ".png")).resolve()
            if candidate.is_file() and candidate.stat().st_size > 0:
                try:
                    if out_png != candidate:
                        if out_png.exists():
                            out_png.unlink(missing_ok=True)
                        candidate.replace(out_png)
                except Exception:
                    return candidate
                return out_png
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # 2) poppler utils
    try:
        base = out_png.with_suffix("")  # pdftoppm adds .png
        r = subprocess.run(
            ["pdftoppm", "-png", "-singlefile", "-f", "1", "-l", "1", str(pdf_path), str(base)],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if r.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 0:
            return out_png
    except FileNotFoundError:
        pass
    except Exception:
        pass

    return None


def _template_daily_brief(data: Dict[str, Any], title: str) -> str:
    items = data.get("items") or data.get("results") or []
    if not isinstance(items, list):
        items = []
    as_of = data.get("as_of") or data.get("generated_at") or ""
    if not as_of:
        as_of = _now_local_str()
    lines = [f"# {title}", "", f"*As of {as_of}*", ""]
    lines.append("## Today at a glance")
    lines.append("")
    lines.append("| # | Headline | Source |")
    lines.append("|---:|---|---|")
    for i, it in enumerate(items[:15], start=1):
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        link = str(it.get("link") or it.get("url") or "").strip()
        src = str(it.get("feed") or it.get("source") or it.get("site") or "").strip()
        lines.append(f"| {i} | {_md_link(h or 'Item', link)} | {_md_escape_inline(src)} |")
    lines.append("")
    if len(items) > 15:
        lines.append("## More headlines")
        lines.append("")
        for it in items[15:40]:
            if not isinstance(it, dict):
                continue
            h = str(it.get("title") or it.get("headline") or "").strip()
            link = str(it.get("link") or it.get("url") or "").strip()
            src = str(it.get("feed") or it.get("source") or "").strip()
            lines.append(f"- {_md_link(h or 'Item', link)} — {_md_escape_inline(src)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _template_weather(data: Dict[str, Any], title: str) -> str:
    loc = str(data.get("location") or data.get("city") or "").strip()
    as_of = str(data.get("as_of") or data.get("generated_at") or "").strip()
    if not as_of:
        as_of = _now_local_str()
    now = data.get("now") or {}
    forecast = data.get("forecast") or data.get("days") or []
    if not isinstance(now, dict):
        now = {}
    if not isinstance(forecast, list):
        forecast = []
    lines = [f"# {title}", ""]
    if loc:
        lines.append(f"**Location:** {loc}")
    lines.append(f"**As of:** {as_of}")
    lines.append("")
    lines.append("## Now")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for k in ("condition", "temp", "feels_like", "humidity", "wind", "precip", "uv"):
        v = now.get(k)
        if v is None or v == "":
            continue
        lines.append(f"| {k.replace('_',' ').title()} | {_md_escape_inline(str(v))} |")
    lines.append("")
    if forecast:
        lines.append("## Forecast")
        lines.append("")
        lines.append("| Day | Summary | High | Low |")
        lines.append("|---|---|---:|---:|")
        for d in forecast[:7]:
            if not isinstance(d, dict):
                continue
            day = str(d.get("day") or d.get("date") or "").strip()
            summ = str(d.get("summary") or d.get("condition") or "").strip()
            hi = str(d.get("high") or d.get("max") or "").strip()
            lo = str(d.get("low") or d.get("min") or "").strip()
            lines.append(
                f"| {_md_escape_inline(day)} | {_md_escape_inline(summ)} | {_md_escape_inline(hi)} | {_md_escape_inline(lo)} |"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _template_stock(data: Dict[str, Any], title: str) -> str:
    as_of = str(data.get("as_of") or data.get("generated_at") or "").strip()
    if not as_of:
        as_of = _now_local_str()
    watch = data.get("watchlist") or data.get("items") or []
    if not isinstance(watch, list):
        watch = []
    lines = [f"# {title}", "", f"*As of {as_of}*", ""]
    lines.append("## Watchlist")
    lines.append("")
    lines.append("| Symbol | Name | Price | Change | Note |")
    lines.append("|---|---|---:|---:|---|")
    for it in watch[:60]:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or it.get("ticker") or "").strip()
        name = str(it.get("name") or "").strip()
        price = str(it.get("price") or it.get("last") or "").strip()
        chg = str(it.get("change") or it.get("pct") or it.get("change_pct") or "").strip()
        note = str(it.get("note") or it.get("alert") or "").strip()
        lines.append(
            f"| {_md_escape_inline(sym)} | {_md_escape_inline(name)} | {_md_escape_inline(price)} | {_md_escape_inline(chg)} | {_md_escape_inline(note)} |"
        )
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_json_to_markdown(template: str, data: Dict[str, Any], title: Optional[str]) -> str:
    t = (template or "").strip().lower()
    if not title:
        title = {"daily_brief": "Daily Brief", "weather": "Weather", "stock": "Stocks"}.get(t, "Report")
    if t == "daily_brief":
        return _template_daily_brief(data, title)
    if t == "weather":
        return _template_weather(data, title)
    if t == "stock":
        return _template_stock(data, title)
    raise ValueError("template must be one of: daily_brief, weather, stock")


def _render_with_vmprint(md_content: str, out_pdf: Path, vmprint_profile: str, vmprint_style: Optional[str]) -> Tuple[bool, str]:
    root = _repo_root()
    vmprint_dir = _default_vmprint_dir(root)
    if vmprint_dir is None:
        return (
            False,
            "VMPrint not found (expected tools/vmprint or tools/vm_print with draft2final/). "
            "Run ./install.sh / install.ps1 / install.bat to install VMPrint.",
        )
    cli_js = _find_vmprint_cli(vmprint_dir)
    if cli_js is None:
        return (
            False,
            f"VMPrint draft2final CLI not built at {vmprint_dir}/draft2final/dist/cli.js. "
            f"Run: cd {vmprint_dir} && npm install && npm run build",
        )
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=False, timeout=10)
    except FileNotFoundError:
        return (False, "Node.js not found on PATH for the Core process. Install Node.js 18+ and ensure `node` works.")

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
        f.write(md_content or "")
        md_path = f.name
    try:
        base_cmd = ["node", str(cli_js), md_path, "--as", (vmprint_profile or "literature")]
        if vmprint_style:
            base_cmd.extend(["--style", vmprint_style])
        cmd_variants = [base_cmd + ["--out", str(out_pdf)], base_cmd + ["--output", str(out_pdf)]]
        last = None
        for cmd in cmd_variants:
            last = subprocess.run(cmd, cwd=str(vmprint_dir), capture_output=True, timeout=180, check=False)
            if last.returncode == 0 and out_pdf.is_file() and out_pdf.stat().st_size > 0:
                return (True, "ok")
        err = (last.stderr or last.stdout or b"").decode("utf-8", errors="replace").strip() if last else "unknown"
        return (False, f"VMPrint render failed: {err[:800] or 'unknown error'}")
    finally:
        try:
            Path(md_path).unlink(missing_ok=True)
        except Exception:
            pass


def _ok(output_rel_path: str, message: str) -> None:
    print(json.dumps({"success": True, "output_rel_path": output_rel_path, "message": message}, ensure_ascii=False))


def _fail(msg: str, rc: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(rc)


def main() -> None:
    p = argparse.ArgumentParser(prog="render_magazine.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_md = sub.add_parser("render-md", help="Render Markdown (provided via --md or --input) to a magazine-style PDF.")
    p_md.add_argument("--title", default="Report", help="Document title.")
    p_md.add_argument("--md", default="", help="Markdown text (inline).")
    p_md.add_argument("--input", default="", help="Path to a Markdown file to read.")
    p_md.add_argument("--theme", default="dispatch", choices=["dispatch", "minimal"], help="Named theme (wraps Markdown).")
    p_md.add_argument("--profile", default="literature", choices=["academic", "manuscript", "screenplay", "literature"])
    p_md.add_argument("--style", default="", help="Optional VMPrint style.")
    p_md.add_argument(
        "--preview",
        default="auto",
        choices=["auto", "none"],
        help="Generate a PNG preview thumbnail (best-effort).",
    )
    p_md.add_argument("--preview_name", default="", help="PNG filename (default derived from --out).")
    p_md.add_argument("--out", required=True, help="Output PDF filename (saved under output/).")

    p_js = sub.add_parser("render-json", help="Render structured JSON via a template to a magazine-style PDF.")
    p_js.add_argument("--template", required=True, choices=["daily_brief", "weather", "stock"], help="Template name.")
    p_js.add_argument("--title", default="", help="Override document title.")
    p_js.add_argument("--json", default="", help="JSON text (inline).")
    p_js.add_argument("--input", default="", help="Path to a JSON file to read.")
    p_js.add_argument("--theme", default="dispatch", choices=["dispatch", "minimal"], help="Named theme (wraps Markdown).")
    p_js.add_argument("--profile", default="literature", choices=["academic", "manuscript", "screenplay", "literature"])
    p_js.add_argument("--style", default="", help="Optional VMPrint style.")
    p_js.add_argument(
        "--preview",
        default="auto",
        choices=["auto", "none"],
        help="Generate a PNG preview thumbnail (best-effort).",
    )
    p_js.add_argument("--preview_name", default="", help="PNG filename (default derived from --out).")
    p_js.add_argument("--out", required=True, help="Output PDF filename (saved under output/).")

    args = p.parse_args()

    out_dir, rel_prefix = _output_dirs()
    out_name = _sanitize_filename(str(args.out))
    out_abs = (out_dir / out_name).resolve()
    out_rel = f"{rel_prefix}{out_name}"

    try:
        if args.cmd == "render-md":
            md_text = (args.md or "").strip()
            if not md_text and args.input:
                md_text = Path(str(args.input)).read_text(encoding="utf-8", errors="replace")
            md_text = _ensure_text_arg(md_text, max_chars=350_000, name="Markdown")
            md_text = _apply_theme_to_markdown(md_text, theme=args.theme, title=str(args.title or "Report"))
            ok, err = _render_with_vmprint(md_text, out_abs, args.profile, (args.style or "").strip() or None)
            if not ok:
                _fail(err)
            if args.preview == "auto":
                prev_name = (args.preview_name or "").strip() or (Path(out_name).stem + ".png")
                prev = _maybe_generate_preview_png(out_abs, out_dir, prev_name)
                if prev:
                    print(f"HOMECLAW_IMAGE_PATH={prev}")
            _ok(out_rel, f"Magazine PDF saved: {out_rel}")
            return

        if args.cmd == "render-json":
            json_text = (args.json or "").strip()
            if not json_text and args.input:
                json_text = Path(str(args.input)).read_text(encoding="utf-8", errors="replace")
            json_text = _ensure_text_arg(json_text, max_chars=350_000, name="JSON")
            data = _json_loads_strict(json_text)
            md_text = _render_json_to_markdown(args.template, data, (args.title or "").strip() or None)
            md_text = _apply_theme_to_markdown(md_text, theme=args.theme, title=str(args.title or "").strip() or "Report")
            ok, err = _render_with_vmprint(md_text, out_abs, args.profile, (args.style or "").strip() or None)
            if not ok:
                _fail(err)
            if args.preview == "auto":
                prev_name = (args.preview_name or "").strip() or (Path(out_name).stem + ".png")
                prev = _maybe_generate_preview_png(out_abs, out_dir, prev_name)
                if prev:
                    print(f"HOMECLAW_IMAGE_PATH={prev}")
            _ok(out_rel, f"Magazine PDF saved: {out_rel}")
            return

        _fail("Unknown command")
    except ValueError as e:
        _fail(str(e))
    except FileNotFoundError as e:
        _fail(f"File not found: {e}")
    except json.JSONDecodeError as e:
        _fail(f"Invalid JSON: {e.msg} (line {e.lineno}, col {e.colno})")


if __name__ == "__main__":
    main()

