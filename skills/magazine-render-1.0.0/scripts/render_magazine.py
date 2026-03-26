#!/usr/bin/env python3
"""
Magazine renderer skill: Markdown/JSON -> VMPrint (draft2final) PDF saved under HOMECLAW_OUTPUT_DIR.

This script prints a single JSON line on success:

  {"success": true, "output_rel_path": "output/<file>.pdf", "message": "..."}

Core's run_skill wrapper appends the file view link automatically when configured.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_VMPRINT_ASSET_VERSION = "v1"


def _vmprint_inline_limits() -> tuple[int, int]:
    """Return (max_ast_chars, max_pages) for inline hint policy."""
    max_ast = 120_000
    max_pages = 2
    try:
        v = os.environ.get("HOMECLAW_VMPRINT_INLINE_MAX_AST_CHARS")
        if v is not None and str(v).strip():
            max_ast = max(10_000, int(v))
    except Exception:
        pass
    try:
        v = os.environ.get("HOMECLAW_VMPRINT_INLINE_MAX_PAGES")
        if v is not None and str(v).strip():
            max_pages = max(1, int(v))
    except Exception:
        pass
    return (max_ast, max_pages)


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


def _sanitize_output_filename(name: str, output_format: str) -> str:
    output_format = (output_format or "pdf").strip().lower()
    if output_format == "layout_json":
        d = "report.layout.json"
        s = (name or "").strip().replace("\\", "/").split("/")[-1]
        s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("._-") or d
        if not s.lower().endswith(".json"):
            s += ".json"
        return s
    if output_format == "browser_preview_html":
        d = "report.preview.html"
        s = (name or "").strip().replace("\\", "/").split("/")[-1]
        s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("._-") or d
        if not s.lower().endswith(".html"):
            s += ".html"
        return s
    return _sanitize_filename(name, default="report.pdf")


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


def _ensure_vmprint_static_assets(out_dir: Path, root: Path) -> None:
    """Ensure VMPrint runtime + preview shell assets exist under output/."""
    try:
        assets_dir = (out_dir / "_vmprint_assets" / _VMPRINT_ASSET_VERSION).resolve()
        assets_dir.mkdir(parents=True, exist_ok=True)
        preview_assets_dir = (out_dir / "assets").resolve()
        preview_assets_dir.mkdir(parents=True, exist_ok=True)
        vmroot = (root / "tools" / "vmprint").resolve()
        copies = [
            (vmroot / "engine" / "dist" / "index.js", assets_dir / "vmprint-engine.js"),
            (vmroot / "contexts" / "canvas" / "dist" / "index.js", assets_dir / "vmprint-context-canvas.js"),
            (vmroot / "font-managers" / "standard" / "dist" / "index.js", assets_dir / "vmprint-web-fonts.js"),
        ]
        for src, dst in copies:
            if src.is_file() and (not dst.exists() or dst.stat().st_size == 0):
                shutil.copy2(src, dst)
        fontkit_stub = assets_dir / "vmprint-fontkit.js"
        if not fontkit_stub.exists() or fontkit_stub.stat().st_size == 0:
            fontkit_stub.write_text(
                "window.process = window.process || { env: {} }; window.VMPrintFontkit = window.VMPrintFontkit || {};",
                encoding="utf-8",
            )
        styles_css = (out_dir / "styles.css").resolve()
        if not styles_css.exists() or styles_css.stat().st_size == 0:
            styles_css.write_text(
                "body{font-family:system-ui;margin:0;background:#111;color:#eee}"
                ".top{padding:10px 12px;background:#1b1b1b;position:sticky;top:0}"
                ".toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}"
                ".pages{padding:12px;display:grid;gap:16px}"
                ".page{background:#fff;color:#111;box-shadow:0 2px 12px rgba(0,0,0,.35);overflow:auto}"
                ".meta{font-size:12px;color:#bbb}",
                encoding="utf-8",
            )
        pipeline_js = preview_assets_dir / "pipeline.js"
        if not pipeline_js.exists() or pipeline_js.stat().st_size == 0:
            pipeline_js.write_text(
                "(function(){"
                "function parseJson(id,f){try{return JSON.parse((document.getElementById(id)||{}).textContent||'');}catch(_){return f;}}"
                "function hasRuntime(){return !!(window.VMPrint||window.vmprint||window.CanvasContext);}"
                "function renderFallback(root,pages){if(!root)return;root.innerHTML='';for(const s of (pages||[])){const d=document.createElement('div');d.className='page';d.innerHTML=String(s||'');root.appendChild(d);}}"
                "window.HomeClawVmprintPipeline={parseJson:parseJson,hasRuntime:hasRuntime,renderFallback:renderFallback};"
                "})();",
                encoding="utf-8",
            )
        ui_js = preview_assets_dir / "ui.js"
        if not ui_js.exists() or ui_js.stat().st_size == 0:
            ui_js.write_text(
                "(function(){"
                "function boot(){const p=window.HomeClawVmprintPipeline;if(!p)return;"
                "const root=document.getElementById('root');const status=document.getElementById('status');"
                "const pages=p.parseJson('fallback-svg-pages-data',[]);"
                "if(!p.hasRuntime()){p.renderFallback(root,pages);if(status)status.textContent='Fallback active (server-rendered pages).';return;}"
                "p.renderFallback(root,pages);if(status)status.textContent='Runtime assets detected; fallback kept until browser pipeline is wired.';}"
                "if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',boot);}else{boot();}"
                "})();",
                encoding="utf-8",
            )
    except Exception:
        pass


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


def _validate_ast_1_1(doc: Dict[str, Any]) -> None:
    if not isinstance(doc, dict):
        raise ValueError("AST root must be an object.")
    if str(doc.get("documentVersion") or "") != "1.1":
        raise ValueError("AST documentVersion must be '1.1'.")
    if not isinstance(doc.get("layout"), dict):
        raise ValueError("AST must include layout object.")
    if not isinstance(doc.get("styles"), dict):
        raise ValueError("AST must include styles object.")
    if not isinstance(doc.get("elements"), list):
        raise ValueError("AST must include elements array.")
    allowed_top = {
        "documentVersion",
        "layout",
        "styles",
        "elements",
        "header",
        "footer",
        "assets",
        "meta",
    }
    unknown = [k for k in doc.keys() if k not in allowed_top]
    if unknown:
        raise ValueError(f"AST has unsupported top-level keys: {', '.join(sorted(unknown))}")

    def _iter_children(el: Dict[str, Any]) -> list:
        out = []
        ch = el.get("children")
        if isinstance(ch, list):
            out.extend([c for c in ch if isinstance(c, dict)])
        for key in ("zones", "slots"):
            arr = el.get(key)
            if isinstance(arr, list):
                for n in arr:
                    if isinstance(n, dict):
                        elems = n.get("elements")
                        if isinstance(elems, list):
                            out.extend([c for c in elems if isinstance(c, dict)])
        return out

    def _walk(elements: list, where: str) -> None:
        for i, el in enumerate(elements):
            if not isinstance(el, dict):
                raise ValueError(f"{where}[{i}] must be an object element.")
            t = str(el.get("type") or "").strip()
            if not t:
                raise ValueError(f"{where}[{i}] missing element type.")

            if t == "table":
                table_cfg = el.get("table")
                if not isinstance(table_cfg, dict):
                    raise ValueError(f"{where}[{i}] table element must include table config object.")
                children = el.get("children")
                if not isinstance(children, list):
                    raise ValueError(f"{where}[{i}] table element must include children rows.")
                header_rows = int(table_cfg.get("headerRows") or 0)
                repeat_header = bool(table_cfg.get("repeatHeader"))
                if repeat_header:
                    if header_rows <= 0:
                        raise ValueError(f"{where}[{i}] repeatHeader=true requires headerRows >= 1.")
                    if len(children) < header_rows:
                        raise ValueError(f"{where}[{i}] headerRows exceeds available table rows.")
                    for r in range(header_rows):
                        row = children[r]
                        if not isinstance(row, dict):
                            raise ValueError(f"{where}[{i}] header row {r} must be an object.")
                        role = str((row.get("properties") or {}).get("semanticRole") or "").strip().lower()
                        if role != "header":
                            raise ValueError(
                                f"{where}[{i}] repeatHeader requires semanticRole='header' on row {r}."
                            )

            if t == "strip":
                if not isinstance(el.get("stripLayout"), dict):
                    raise ValueError(f"{where}[{i}] strip element requires stripLayout object.")
                if not isinstance(el.get("slots"), list):
                    raise ValueError(f"{where}[{i}] strip element requires slots list.")

            if t == "zone-map":
                if not isinstance(el.get("zoneLayout"), dict):
                    raise ValueError(f"{where}[{i}] zone-map element requires zoneLayout object.")
                zones = el.get("zones")
                if not isinstance(zones, list):
                    raise ValueError(f"{where}[{i}] zone-map element requires zones list.")

            _walk(_iter_children(el), f"{where}[{i}]")

    _walk(doc.get("elements") or [], "elements")
    h = doc.get("header") or {}
    if isinstance(h, dict):
        for k, v in h.items():
            if isinstance(v, dict) and isinstance(v.get("elements"), list):
                _walk(v["elements"], f"header.{k}.elements")
    f = doc.get("footer") or {}
    if isinstance(f, dict):
        for k, v in f.items():
            if isinstance(v, dict) and isinstance(v.get("elements"), list):
                _walk(v["elements"], f"footer.{k}.elements")


def _daily_brief_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    items = data.get("items") or data.get("results") or []
    if not isinstance(items, list):
        items = []
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    headline_rows = []
    for i, it in enumerate(items[:18], start=1):
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        src = str(it.get("feed") or it.get("source") or it.get("site") or "").strip()
        link = str(it.get("link") or it.get("url") or "").strip()
        headline_rows.append(
            {
                "type": "table-row",
                "content": "",
                "children": [
                    {"type": "table-cell", "content": str(i)},
                    {"type": "table-cell", "content": h or "Item"},
                    {"type": "table-cell", "content": src or "-"},
                    {"type": "table-cell", "content": link or "-"},
                ],
            }
        )
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 720, "height": 405},
            "orientation": "landscape",
            "margins": {"top": 34, "right": 42, "bottom": 34, "left": 42},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.35,
            "pageBackground": "#f7f7f7" if theme == "minimal" else "#fdf6e3",
        },
        "styles": {
            "kicker": {"fontSize": 8, "letterSpacing": 1.2, "marginBottom": 4, "keepWithNext": True},
            "title": {"fontSize": 24, "fontWeight": "bold", "marginBottom": 8, "keepWithNext": True},
            "meta": {"fontSize": 9, "marginBottom": 10, "color": "#555"},
            "body": {"fontSize": 10, "marginBottom": 8, "textAlign": "justify"},
            "table-cell": {"fontSize": 8, "paddingTop": 3, "paddingBottom": 3, "paddingLeft": 4, "paddingRight": 4},
            "rh-odd": {"fontSize": 8, "textAlign": "center", "color": "#666"},
            "folio-left": {"fontSize": 8, "textAlign": "left", "color": "#666"},
            "folio-page": {"fontSize": 8, "textAlign": "center", "color": "#666"},
            "folio-right": {"fontSize": 8, "textAlign": "right", "color": "#666"},
        },
        "header": {
            "default": {
                "elements": [
                    {
                        "type": "strip",
                        "content": "",
                        "stripLayout": {"tracks": [{"mode": "flex", "fr": 1}, {"mode": "fixed", "value": 150}], "gap": 8},
                        "slots": [
                            {"id": "left", "elements": [{"type": "rh-odd", "content": mast}]},
                            {"id": "right", "elements": [{"type": "rh-odd", "content": as_of}]},
                        ],
                    }
                ]
            }
        },
        "footer": {
            "default": {
                "elements": [
                    {
                        "type": "strip",
                        "content": "",
                        "stripLayout": {"tracks": [{"mode": "flex", "fr": 1}, {"mode": "fixed", "value": 86}, {"mode": "flex", "fr": 1}], "gap": 8},
                        "slots": [
                            {"id": "left", "elements": [{"type": "folio-left", "content": "HomeClaw"}]},
                            {"id": "center", "elements": [{"type": "folio-page", "content": "Page {pageNumber} / {totalPages}"}]},
                            {"id": "right", "elements": [{"type": "folio-right", "content": "Daily Brief"}]},
                        ],
                    }
                ]
            }
        },
        "elements": [
            {"type": "kicker", "content": "DAILY BRIEF"},
            {"type": "title", "content": mast},
            {"type": "meta", "content": f"As of {as_of}"},
            {
                "type": "zone-map",
                "content": "",
                "zoneLayout": {"columns": [{"mode": "flex", "fr": 2}, {"mode": "flex", "fr": 1}], "gap": 16},
                "zones": [
                    {
                        "id": "main",
                        "elements": [
                            {
                                "type": "table",
                                "content": "",
                                "table": {
                                    "headerRows": 1,
                                    "repeatHeader": True,
                                    "columnGap": 4,
                                    "columns": [
                                        {"mode": "fixed", "value": 24},
                                        {"mode": "flex", "fr": 2},
                                        {"mode": "fixed", "value": 90},
                                        {"mode": "flex", "fr": 1},
                                    ],
                                },
                                "children": [
                                    {
                                        "type": "table-row",
                                        "content": "",
                                        "properties": {"semanticRole": "header"},
                                        "children": [
                                            {"type": "table-cell", "content": "#"},
                                            {"type": "table-cell", "content": "Headline"},
                                            {"type": "table-cell", "content": "Source"},
                                            {"type": "table-cell", "content": "Link"},
                                        ],
                                    },
                                    *headline_rows,
                                ],
                            }
                        ],
                    },
                    {
                        "id": "side",
                        "elements": [
                            {"type": "kicker", "content": "TOP HIGHLIGHTS"},
                            {"type": "body", "content": "• Focused, readable dispatch layout"},
                            {"type": "body", "content": "• Structured table with stable pagination"},
                            {"type": "body", "content": "• Same AST can render to PDF or browser preview"},
                        ],
                    },
                ],
            },
        ],
    }


def _weather_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    now = data.get("now") or {}
    if not isinstance(now, dict):
        now = {}
    days = data.get("forecast") or data.get("days") or []
    if not isinstance(days, list):
        days = []
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    loc = str(data.get("location") or data.get("city") or "Unknown")
    rows = []
    for d in days[:10]:
        if not isinstance(d, dict):
            continue
        rows.append(
            {
                "type": "table-row",
                "content": "",
                "children": [
                    {"type": "table-cell", "content": str(d.get("day") or d.get("date") or "-")},
                    {"type": "table-cell", "content": str(d.get("summary") or d.get("condition") or "-")},
                    {"type": "table-cell", "content": str(d.get("high") or d.get("max") or "-")},
                    {"type": "table-cell", "content": str(d.get("low") or d.get("min") or "-")},
                ],
            }
        )
    mast = title.upper() if theme == "dispatch" else title
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 720, "height": 405},
            "orientation": "landscape",
            "margins": {"top": 34, "right": 42, "bottom": 34, "left": 42},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.35,
            "pageBackground": "#f7f7f7" if theme == "minimal" else "#eef6ff",
        },
        "styles": {
            "kicker": {"fontSize": 8, "letterSpacing": 1.2, "marginBottom": 4, "keepWithNext": True},
            "title": {"fontSize": 24, "fontWeight": "bold", "marginBottom": 8, "keepWithNext": True},
            "meta": {"fontSize": 9, "marginBottom": 10, "color": "#555"},
            "body": {"fontSize": 10, "marginBottom": 8},
            "table-cell": {"fontSize": 8, "paddingTop": 3, "paddingBottom": 3, "paddingLeft": 4, "paddingRight": 4},
        },
        "elements": [
            {"type": "kicker", "content": "WEATHER"},
            {"type": "title", "content": mast},
            {"type": "meta", "content": f"{loc} · As of {as_of}"},
            {
                "type": "strip",
                "content": "",
                "stripLayout": {"tracks": [{"mode": "flex", "fr": 1}, {"mode": "flex", "fr": 1}], "gap": 14},
                "slots": [
                    {
                        "id": "left",
                        "elements": [
                            {"type": "body", "content": f"Condition: {now.get('condition') or '-'}"},
                            {"type": "body", "content": f"Temp: {now.get('temp') or '-'}"},
                            {"type": "body", "content": f"Feels Like: {now.get('feels_like') or '-'}"},
                            {"type": "body", "content": f"Humidity: {now.get('humidity') or '-'}"},
                            {"type": "body", "content": f"Wind: {now.get('wind') or '-'}"},
                        ],
                    },
                    {
                        "id": "right",
                        "elements": [
                            {
                                "type": "table",
                                "content": "",
                                "table": {"headerRows": 1, "repeatHeader": True, "columnGap": 4},
                                "children": [
                                    {
                                        "type": "table-row",
                                        "content": "",
                                        "properties": {"semanticRole": "header"},
                                        "children": [
                                            {"type": "table-cell", "content": "Day"},
                                            {"type": "table-cell", "content": "Summary"},
                                            {"type": "table-cell", "content": "High"},
                                            {"type": "table-cell", "content": "Low"},
                                        ],
                                    },
                                    *rows,
                                ],
                            }
                        ],
                    },
                ],
            },
        ],
    }


def _stock_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    items = data.get("watchlist") or data.get("items") or []
    if not isinstance(items, list):
        items = []
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    rows = []
    for it in items[:30]:
        if not isinstance(it, dict):
            continue
        rows.append(
            {
                "type": "table-row",
                "content": "",
                "children": [
                    {"type": "table-cell", "content": str(it.get("symbol") or it.get("ticker") or "-")},
                    {"type": "table-cell", "content": str(it.get("name") or "-")},
                    {"type": "table-cell", "content": str(it.get("price") or it.get("last") or "-")},
                    {"type": "table-cell", "content": str(it.get("change_pct") or it.get("pct") or it.get("change") or "-")},
                    {"type": "table-cell", "content": str(it.get("note") or it.get("alert") or "-")},
                ],
            }
        )
    mast = title.upper() if theme == "dispatch" else title
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 720, "height": 405},
            "orientation": "landscape",
            "margins": {"top": 34, "right": 42, "bottom": 34, "left": 42},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.35,
            "pageBackground": "#f7f7f7" if theme == "minimal" else "#f6f2e8",
        },
        "styles": {
            "kicker": {"fontSize": 8, "letterSpacing": 1.2, "marginBottom": 4, "keepWithNext": True},
            "title": {"fontSize": 24, "fontWeight": "bold", "marginBottom": 8, "keepWithNext": True},
            "meta": {"fontSize": 9, "marginBottom": 10, "color": "#555"},
            "table-cell": {"fontSize": 8, "paddingTop": 3, "paddingBottom": 3, "paddingLeft": 4, "paddingRight": 4},
        },
        "elements": [
            {"type": "kicker", "content": "MARKET BRIEF"},
            {"type": "title", "content": mast},
            {"type": "meta", "content": f"As of {as_of}"},
            {
                "type": "table",
                "content": "",
                "table": {"headerRows": 1, "repeatHeader": True, "columnGap": 4},
                "children": [
                    {
                        "type": "table-row",
                        "content": "",
                        "properties": {"semanticRole": "header"},
                        "children": [
                            {"type": "table-cell", "content": "Symbol"},
                            {"type": "table-cell", "content": "Name"},
                            {"type": "table-cell", "content": "Price"},
                            {"type": "table-cell", "content": "Change"},
                            {"type": "table-cell", "content": "Note"},
                        ],
                    },
                    *rows,
                ],
            },
        ],
    }


def _ast_from_template(template: str, data: Dict[str, Any], title: str, theme: str) -> Dict[str, Any]:
    t = (template or "").strip().lower()
    if t == "daily_brief":
        return _daily_brief_ast(data, title=title, theme=theme)
    if t == "weather":
        return _weather_ast(data, title=title, theme=theme)
    if t == "stock":
        return _stock_ast(data, title=title, theme=theme)
    raise ValueError("template must be one of: daily_brief, weather, stock")
def _build_browser_preview_html(layout_json_text: str) -> str:
    esc = html.escape(layout_json_text or "{}")
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>VMPrint Preview</title><style>body{font-family:system-ui;margin:0;background:#111;color:#eee}"
        ".top{padding:10px 12px;background:#1b1b1b;position:sticky;top:0}.pages{padding:12px;display:grid;gap:16px}"
        ".page{background:#fff;color:#111;position:relative;box-shadow:0 2px 12px rgba(0,0,0,.35);overflow:hidden}"
        ".box{position:absolute;border:1px dashed rgba(0,0,0,.12);font-size:10px;line-height:1.2;overflow:hidden;white-space:pre-wrap}"
        ".meta{font-size:12px;color:#bbb}</style></head><body>"
        "<div class='top'><strong>VMPrint Scene Preview</strong><div class='meta'>HomeClaw generated preview (layout boxes).</div></div>"
        "<div id='root' class='pages'></div>"
        f"<script id='layout-data' type='application/json'>{esc}</script>"
        "<script>const d=JSON.parse(document.getElementById('layout-data').textContent||'{}');"
        "const pages=d.pages||[];const root=document.getElementById('root');"
        "for(const p of pages){const w=p.width||595,h=p.height||842;const pg=document.createElement('div');pg.className='page';pg.style.width=w+'px';pg.style.height=h+'px';"
        "for(const b of (p.boxes||[])){const n=document.createElement('div');n.className='box';n.style.left=(b.x||0)+'px';n.style.top=(b.y||0)+'px';n.style.width=(b.w||0)+'px';n.style.height=(b.h||0)+'px';"
        "const t=(b.lines&&b.lines.length)?(b.lines.map(l=>(l.segments||[]).map(s=>s.text||'').join('')).join('\\n')):(b.type||'');n.textContent=t;pg.appendChild(n);}root.appendChild(pg);}"
        "</script></body></html>"
    )


def _build_canvas_preview_html(svg_pages: list) -> str:
    esc_json = html.escape(json.dumps(svg_pages, ensure_ascii=False))
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>VMPrint Canvas Preview</title><style>body{font-family:system-ui;margin:0;background:#111;color:#eee}"
        ".top{padding:10px 12px;background:#1b1b1b;position:sticky;top:0}.pages{padding:12px;display:grid;gap:16px}"
        ".page{background:#fff;color:#111;box-shadow:0 2px 12px rgba(0,0,0,.35);overflow:auto}"
        ".meta{font-size:12px;color:#bbb}</style></head><body>"
        "<div class='top'><strong>VMPrint CanvasContext Preview</strong><div class='meta'>Rendered from AST via @vmprint/context-canvas.</div></div>"
        "<div id='root' class='pages'></div>"
        f"<script id='svg-pages-data' type='application/json'>{esc_json}</script>"
        "<script>const pages=JSON.parse(document.getElementById('svg-pages-data').textContent||'[]');"
        "const root=document.getElementById('root');"
        "for(const s of pages){const d=document.createElement('div');d.className='page';d.innerHTML=String(s||'');root.appendChild(d);}</script>"
        "</body></html>"
    )


def _build_hybrid_runtime_preview_html(ast_json_text: str, fallback_svg_pages: list) -> str:
    ast_esc = html.escape(ast_json_text or "{}")
    svg_esc = html.escape(json.dumps(fallback_svg_pages or [], ensure_ascii=False))
    ast_chars = len(ast_json_text or "")
    page_count = len(fallback_svg_pages or [])
    max_ast, max_pages = _vmprint_inline_limits()
    ui_hint = "inline" if (ast_chars <= max_ast and page_count <= max_pages) else "link"
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='homeclaw-vmprint-ui-hint' content='{ui_hint}'>"
        f"<meta name='homeclaw-vmprint-ast-chars' content='{ast_chars}'>"
        f"<meta name='homeclaw-vmprint-pages' content='{page_count}'>"
        "<title>VMPrint Browser Preview</title><link rel='stylesheet' href='./styles.css'></head><body>"
        "<div class='top'><strong>VMPrint Hybrid Preview</strong>"
        "<div class='meta'>Primary: browser VMPrint runtime (AST->canvas). Fallback: server-rendered pages.</div>"
        "<div class='toolbar'><label>Scale <select id='scale'><option value='0.75'>75%</option><option selected value='1'>100%</option><option value='1.25'>125%</option><option value='1.5'>150%</option></select></label>"
        "<label>DPI <select id='dpi'><option selected value='auto'>Auto</option><option value='72'>72</option><option value='96'>96</option><option value='144'>144</option><option value='192'>192</option><option value='300'>300</option></select></label>"
        "<label>Text <select id='text-mode'><option value='text'>Text</option><option selected value='glyph-path'>Glyph Path</option></select></label>"
        "<span id='status' class='meta'>Initializing...</span></div></div>"
        "<div id='root' class='pages'></div>"
        f"<script id='ast-data' type='application/json'>{ast_esc}</script>"
        f"<script id='fallback-svg-pages-data' type='application/json'>{svg_esc}</script>"
        f"<script src='./_vmprint_assets/{_VMPRINT_ASSET_VERSION}/vmprint-fontkit.js'></script><script src='./_vmprint_assets/{_VMPRINT_ASSET_VERSION}/vmprint-engine.js'></script><script src='./_vmprint_assets/{_VMPRINT_ASSET_VERSION}/vmprint-web-fonts.js'></script><script src='./_vmprint_assets/{_VMPRINT_ASSET_VERSION}/vmprint-context-canvas.js'></script>"
        "<script src='./assets/pipeline.js'></script><script src='./assets/ui.js'></script>"
        "</body></html>"
    )


def _render_ast_with_vmprint(ast_doc: Dict[str, Any], out_abs: Path, output_format: str) -> Tuple[bool, str]:
    root = _repo_root()
    _ensure_vmprint_static_assets(out_abs.parent, root)
    vmprint_dir = _default_vmprint_dir(root)
    if vmprint_dir is None:
        return (False, "VMPrint not found (expected tools/vmprint).")
    vm_cli = (vmprint_dir / "cli" / "dist" / "index.js").resolve()
    if not vm_cli.is_file():
        return (False, f"VMPrint CLI not built at {vm_cli}. Run: cd {vmprint_dir} && npm install && npm run build")
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".ast.json", delete=False, mode="w", encoding="utf-8") as f:
        json.dump(ast_doc, f, ensure_ascii=False, indent=2)
        ast_path = f.name
    layout_path = ast_path + ".layout.json"
    pdf_path = ast_path + ".pdf"
    try:
        if output_format == "pdf":
            r = subprocess.run(
                ["node", str(vm_cli), "-i", ast_path, "-o", str(out_abs)],
                cwd=str(vmprint_dir),
                capture_output=True,
                timeout=180,
                check=False,
            )
            if r.returncode == 0 and out_abs.is_file() and out_abs.stat().st_size > 0:
                return (True, "ok")
            err = (r.stderr or r.stdout or b"").decode("utf-8", errors="replace").strip()
            return (False, f"VMPrint AST render failed: {err[:800] or 'unknown'}")
        r = subprocess.run(
            ["node", str(vm_cli), "-i", ast_path, "-o", pdf_path, "--emit-layout", layout_path],
            cwd=str(vmprint_dir),
            capture_output=True,
            timeout=180,
            check=False,
        )
        if r.returncode != 0 or not Path(layout_path).is_file():
            err = (r.stderr or r.stdout or b"").decode("utf-8", errors="replace").strip()
            return (False, f"VMPrint layout emit failed: {err[:800] or 'unknown'}")
        if output_format == "layout_json":
            out_abs.write_text(Path(layout_path).read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            return (True, "ok")
        if output_format == "browser_preview_html":
            canvas_script = (
                "const fs=require('fs');"
                "const {LayoutEngine,Renderer,toLayoutConfig,createEngineRuntime}=require('./engine/dist/index.js');"
                "const {StandardFontManager}=require('./font-managers/standard/dist/index.js');"
                "const {CanvasContext}=require('./contexts/canvas/dist/index.js');"
                "const p=process.argv[1]; const doc=JSON.parse(fs.readFileSync(p,'utf8'));"
                "(async()=>{"
                "const runtime=createEngineRuntime({fontManager:new StandardFontManager()});"
                "const cfg=toLayoutConfig(doc);"
                "const engine=new LayoutEngine(cfg,runtime);"
                "await engine.waitForFonts();"
                "const pages=engine.simulate(doc.elements);"
                "const ctx=new CanvasContext({size:cfg.pageSize,margins:cfg.margins,autoFirstPage:false,bufferPages:false,textRenderMode:'text'});"
                "const renderer=new Renderer(cfg,false,runtime);"
                "await renderer.render(pages,ctx); ctx.end();"
                "process.stdout.write(JSON.stringify({svgs:ctx.toSvgPages()}));"
                "})().catch(e=>{console.error(String(e&&e.stack||e)); process.exit(2);});"
            )
            c = subprocess.run(
                ["node", "-e", canvas_script, ast_path],
                cwd=str(vmprint_dir),
                capture_output=True,
                timeout=180,
                check=False,
            )
            if c.returncode != 0:
                err = (c.stderr or c.stdout or b"").decode("utf-8", errors="replace").strip()
                return (False, f"VMPrint canvas preview failed: {err[:800] or 'unknown'}")
            try:
                payload = json.loads((c.stdout or b"{}").decode("utf-8", errors="replace"))
                svgs = payload.get("svgs") if isinstance(payload, dict) else None
                if not isinstance(svgs, list) or not svgs:
                    return (False, "VMPrint canvas preview failed: no pages rendered.")
            except Exception as e:
                return (False, f"VMPrint canvas preview parse failed: {e!s}")
            html_out = _build_hybrid_runtime_preview_html(json.dumps(ast_doc, ensure_ascii=False), svgs)
            if len(html_out) > 2_000_000:
                return (False, f"Preview html too large ({len(html_out)} chars). Use output_format=layout_json or output_format=pdf.")
            out_abs.write_text(html_out, encoding="utf-8")
            return (True, "ok")
        return (False, "Unknown output_format")
    finally:
        try:
            Path(ast_path).unlink(missing_ok=True)
            Path(layout_path).unlink(missing_ok=True)
            Path(pdf_path).unlink(missing_ok=True)
        except Exception:
            pass


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


def _contains_cjk(text: str) -> bool:
    s = text or ""
    for ch in s:
        cp = ord(ch)
        if (
            0x4E00 <= cp <= 0x9FFF  # CJK Unified Ideographs
            or 0x3400 <= cp <= 0x4DBF  # CJK Extension A
            or 0x20000 <= cp <= 0x2A6DF  # CJK Extension B
            or 0x2A700 <= cp <= 0x2B73F  # CJK Extension C
            or 0x2B740 <= cp <= 0x2B81F  # CJK Extension D
            or 0x2B820 <= cp <= 0x2CEAF  # CJK Extension E/F
        ):
            return True
    return False


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
        themed = "\n".join([p for p in parts if p is not None]).strip() + "\n"
        if _contains_cjk(themed) and not themed.lstrip().startswith("---"):
            # Force a CJK-capable primary family to avoid tofu squares in Chinese/Japanese/Korean text.
            frontmatter = (
                "---\n"
                "layout:\n"
                "  fontFamily: Noto Sans SC\n"
                "---\n\n"
            )
            themed = frontmatter + themed
        return themed

    if theme in ("minimal", "report"):
        mast = (title or "Report").strip()
        parts = [f"# {mast}", "", f"*As of {as_of}*", "", body, ""]
        themed = "\n".join(parts).strip() + "\n"
        if _contains_cjk(themed) and not themed.lstrip().startswith("---"):
            frontmatter = (
                "---\n"
                "layout:\n"
                "  fontFamily: Noto Sans SC\n"
                "---\n\n"
            )
            themed = frontmatter + themed
        return themed

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

    p_ast = sub.add_parser("render-ast", help="Render VMPrint AST JSON 1.1 directly.")
    p_ast.add_argument("--ast", default="", help="AST JSON text (inline).")
    p_ast.add_argument("--input", default="", help="Path to AST JSON file.")
    p_ast.add_argument("--output_format", default="pdf", choices=["pdf", "layout_json", "browser_preview_html"])
    p_ast.add_argument("--out", required=True, help="Output filename under output/ (pdf/json/html depending on output_format).")

    p_dba = sub.add_parser("render-daily-brief-ast", help="Compile daily-brief JSON -> VMPrint AST -> artifact.")
    p_dba.add_argument("--title", default="Daily Brief", help="Document title.")
    p_dba.add_argument("--json", default="", help="Daily-brief JSON text (inline).")
    p_dba.add_argument("--input", default="", help="Path to daily-brief JSON file.")
    p_dba.add_argument("--theme", default="dispatch", choices=["dispatch", "minimal"])
    p_dba.add_argument("--output_format", default="pdf", choices=["pdf", "layout_json", "browser_preview_html"])
    p_dba.add_argument("--out", required=True, help="Output filename under output/ (pdf/json/html depending on output_format).")

    p_ta = sub.add_parser("render-template-ast", help="Compile template JSON -> VMPrint AST -> artifact.")
    p_ta.add_argument("--template", required=True, choices=["daily_brief", "weather", "stock"])
    p_ta.add_argument("--title", default="Report", help="Document title.")
    p_ta.add_argument("--json", default="", help="Template JSON text (inline).")
    p_ta.add_argument("--input", default="", help="Path to template JSON file.")
    p_ta.add_argument("--theme", default="dispatch", choices=["dispatch", "minimal"])
    p_ta.add_argument("--output_format", default="browser_preview_html", choices=["pdf", "layout_json", "browser_preview_html"])
    p_ta.add_argument("--out", required=True, help="Output filename under output/ (pdf/json/html depending on output_format).")

    args = p.parse_args()

    out_dir, rel_prefix = _output_dirs()
    if args.cmd in ("render-ast", "render-daily-brief-ast", "render-template-ast"):
        out_name = _sanitize_output_filename(str(args.out), str(getattr(args, "output_format", "pdf")))
    else:
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

        if args.cmd == "render-ast":
            ast_text = (args.ast or "").strip()
            if not ast_text and args.input:
                ast_text = Path(str(args.input)).read_text(encoding="utf-8", errors="replace")
            ast_text = _ensure_text_arg(ast_text, max_chars=900_000, name="AST JSON")
            ast_doc = _json_loads_strict(ast_text)
            _validate_ast_1_1(ast_doc)
            ok, err = _render_ast_with_vmprint(ast_doc, out_abs, str(args.output_format))
            if not ok:
                _fail(err)
            _ok(out_rel, f"VMPrint AST artifact saved: {out_rel}")
            return

        if args.cmd == "render-daily-brief-ast":
            json_text = (args.json or "").strip()
            if not json_text and args.input:
                json_text = Path(str(args.input)).read_text(encoding="utf-8", errors="replace")
            json_text = _ensure_text_arg(json_text, max_chars=350_000, name="JSON")
            data = _json_loads_strict(json_text)
            ast_doc = _daily_brief_ast(data, title=str(args.title or "Daily Brief"), theme=str(args.theme or "dispatch"))
            _validate_ast_1_1(ast_doc)
            ok, err = _render_ast_with_vmprint(ast_doc, out_abs, str(args.output_format))
            if not ok:
                _fail(err)
            _ok(out_rel, f"VMPrint daily-brief AST artifact saved: {out_rel}")
            return

        if args.cmd == "render-template-ast":
            json_text = (args.json or "").strip()
            if not json_text and args.input:
                json_text = Path(str(args.input)).read_text(encoding="utf-8", errors="replace")
            json_text = _ensure_text_arg(json_text, max_chars=350_000, name="JSON")
            data = _json_loads_strict(json_text)
            ast_doc = _ast_from_template(
                str(args.template or ""),
                data,
                title=str(args.title or "Report"),
                theme=str(args.theme or "dispatch"),
            )
            _validate_ast_1_1(ast_doc)
            ok, err = _render_ast_with_vmprint(ast_doc, out_abs, str(args.output_format))
            if not ok:
                _fail(err)
            _ok(out_rel, f"VMPrint template AST artifact saved: {out_rel}")
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

