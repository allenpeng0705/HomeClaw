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
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from tools.vmprint_preview_loader import vmprint_hybrid_preview_loaders

_VMPRINT_ASSET_VERSION = "v1"

# VMPrint scripting YAML (methods only); paired with JSON body in one .json file. See tools/vmprint/documents/SKILL.md §17.
_WEB_SEARCH_COLOPHON_SCRIPT_YAML = """methods:
  onReady(): |
    const pages = doc.getPageCount()
    sendMessage("colophon", { subject: "ready-pages", payload: { pages } })
  colophon_onMessage(from, msg): |
    if (from.name !== "doc") return
    if (msg.subject !== "ready-pages") return
    const p = Number((msg.payload && msg.payload.pages) || 0)
    setContent(self, "Settled across " + p + " page(s).")
"""


def _write_ast_input_file(path: Path, ast_doc: Dict[str, Any], script_yaml: Optional[str]) -> None:
    if script_yaml and str(script_yaml).strip():
        path.write_text(
            "---\n" + str(script_yaml).strip() + "\n---\n" + json.dumps(ast_doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        path.write_text(json.dumps(ast_doc, ensure_ascii=False, indent=2), encoding="utf-8")


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
        if not p.is_dir():
            continue
        if (p / "draft2final").is_dir():
            return p
        if (p / "package.json").is_file() and (p / "cli").is_dir():
            return p
    return None


def _vmprint_cli_marker_path(vmroot: Path) -> Path:
    return (vmroot / "cli" / "dist" / "index.js").resolve()


def _vmprint_root_from_built_cli_js(cli_js: Path) -> Optional[Path]:
    """If cli_js is .../cli/dist/index.js, return the vmprint monorepo root."""
    try:
        r = cli_js.expanduser().resolve()
        if not r.is_file():
            return None
        if r.name != "index.js":
            return None
        if r.parent.name != "dist" or r.parent.parent.name != "cli":
            return None
        return r.parent.parent.parent
    except Exception:
        return None


def _vmprint_root_for_ast(root: Path) -> Optional[Path]:
    """Monorepo root with built @vmprint/cli (AST / layout / browser preview). Draft2Final is not required."""
    for env_key in ("HOMECLAW_VMPRINT_CLI", "VMPRINT_CLI"):
        raw = (os.environ.get(env_key) or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser().resolve()
        vmroot = _vmprint_root_from_built_cli_js(p)
        if vmroot is not None and _vmprint_cli_marker_path(vmroot).is_file():
            return vmroot
    for env_key in ("HOMECLAW_VMPRINT_ROOT", "VMPRINT_ROOT"):
        raw = (os.environ.get(env_key) or "").strip()
        if not raw:
            continue
        p = Path(raw).expanduser().resolve()
        if p.is_dir() and _vmprint_cli_marker_path(p).is_file():
            return p
    for name in ("vmprint", "vm_print"):
        p = (root / "tools" / name).resolve()
        if p.is_dir() and _vmprint_cli_marker_path(p).is_file():
            return p
    return None


def _vmprint_ast_cli_missing_message(root: Path) -> str:
    """Actionable multi-line message when cli/dist/index.js is missing."""
    default_dir = (root / "tools" / "vmprint").resolve()
    lines = [
        "VMPrint CLI missing: expected cli/dist/index.js (run a full workspace build).",
        f"  Default path: {default_dir}",
        "  Optional: set HOMECLAW_VMPRINT_ROOT or VMPRINT_ROOT to a vmprint clone that already has cli/dist/index.js,",
        "  or HOMECLAW_VMPRINT_CLI / VMPRINT_CLI to the absolute path of cli/dist/index.js.",
        "  From HomeClaw repo root (first-time):",
        "    git clone --depth 1 https://github.com/cosmiciron/vmprint.git tools/vmprint",
        "    cd tools/vmprint && npm install && npm run build",
        "  If clone exists but error persists: cd tools/vmprint && rm -rf node_modules */node_modules */dist && npm install && npm run build",
        "  For browser_preview_html (SVG canvas): cd tools/vmprint && npm install @vmprint/context-canvas",
        "  Docs: skills/magazine-render-1.0.0/ast_templates/README.md",
    ]
    return "\n".join(lines)


def _vmprint_root_for_assets(root: Path, prefer: Optional[Path] = None) -> Path:
    if prefer is not None and prefer.is_dir():
        return prefer.resolve()
    p = _vmprint_root_for_ast(root)
    if p is not None:
        return p
    q = _default_vmprint_dir(root)
    if q is not None:
        return q
    return (root / "tools" / "vmprint").resolve()


def _vmprint_npm_package_dist_entry(
    vmroot: Path, scope: str, name: str, dist_names: Tuple[str, ...]
) -> Optional[Path]:
    """Resolve a built npm package entry (hoisted under vmroot or nested under cli/engine)."""
    for root in (vmroot, vmroot / "cli", vmroot / "engine"):
        pkg = root / "node_modules" / scope / name
        if not pkg.is_dir():
            continue
        for rel in dist_names:
            p = (pkg / rel).resolve()
            if p.is_file():
                return p
        pkg_json = pkg / "package.json"
        if pkg_json.is_file():
            try:
                main = json.loads(pkg_json.read_text(encoding="utf-8")).get("main")
                if isinstance(main, str) and main.strip():
                    p = (pkg / main.strip()).resolve()
                    if p.is_file():
                        return p
            except Exception:
                pass
    return None


def _vmprint_preview_standard_fonts_cjs(vmroot: Path) -> Optional[Path]:
    p = _vmprint_npm_package_dist_entry(vmroot, "@vmprint", "standard-fonts", ("dist/index.cjs", "dist/index.js"))
    if p is not None:
        return p
    legacy = (vmroot / "font-managers" / "standard" / "dist" / "index.js").resolve()
    return legacy if legacy.is_file() else None


def _vmprint_preview_context_canvas_js(vmroot: Path) -> Optional[Path]:
    p = _vmprint_npm_package_dist_entry(vmroot, "@vmprint", "context-canvas", ("dist/index.js", "dist/index.cjs"))
    if p is not None:
        return p
    legacy = (vmroot / "contexts" / "canvas" / "dist" / "index.js").resolve()
    return legacy if legacy.is_file() else None


def _vmprint_preview_node_deps_missing_message(vmroot: Path) -> str:
    std = _vmprint_preview_standard_fonts_cjs(vmroot)
    ctx = _vmprint_preview_context_canvas_js(vmroot)
    missing: List[str] = []
    if std is None:
        missing.append("@vmprint/standard-fonts")
    if ctx is None:
        missing.append("@vmprint/context-canvas")
    if not missing:
        return ""
    pkgs = " ".join(missing)
    return (
        f"Missing preview packages ({', '.join(missing)}). "
        f"From your VMPrint root run: npm install {pkgs}"
    )


def _find_vmprint_cli(vmprint_dir: Path) -> Optional[Path]:
    legacy = (vmprint_dir / "draft2final" / "dist" / "cli.js").resolve()
    if legacy.is_file():
        return legacy
    npm_cli = (vmprint_dir / "node_modules" / "draft2final" / "dist" / "cli.js").resolve()
    return npm_cli if npm_cli.is_file() else None


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


def _ensure_vmprint_static_assets(out_dir: Path, root: Path, vmroot: Optional[Path] = None) -> None:
    """Ensure VMPrint runtime + preview shell assets exist under output/."""
    try:
        assets_dir = (out_dir / "_vmprint_assets" / _VMPRINT_ASSET_VERSION).resolve()
        assets_dir.mkdir(parents=True, exist_ok=True)
        preview_assets_dir = (out_dir / "assets").resolve()
        preview_assets_dir.mkdir(parents=True, exist_ok=True)
        vmroot = _vmprint_root_for_assets(root, prefer=vmroot)
        copies: List[Tuple[Path, Path]] = []
        eng_js = (vmroot / "engine" / "dist" / "index.js").resolve()
        if eng_js.is_file():
            copies.append((eng_js, assets_dir / "vmprint-engine.js"))
        cc_js = _vmprint_preview_context_canvas_js(vmroot)
        if cc_js is not None and cc_js.is_file():
            copies.append((cc_js, assets_dir / "vmprint-context-canvas.js"))
        else:
            legacy_cc = (vmroot / "contexts" / "canvas" / "dist" / "index.js").resolve()
            if legacy_cc.is_file():
                copies.append((legacy_cc, assets_dir / "vmprint-context-canvas.js"))
        std_js = _vmprint_preview_standard_fonts_cjs(vmroot)
        if std_js is not None and std_js.is_file():
            copies.append((std_js, assets_dir / "vmprint-web-fonts.js"))
        else:
            legacy_std = (vmroot / "font-managers" / "standard" / "dist" / "index.js").resolve()
            if legacy_std.is_file():
                copies.append((legacy_std, assets_dir / "vmprint-web-fonts.js"))
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
        styles_css.write_text(
            "body{font-family:system-ui;margin:0;background:#111;color:#eee;overflow-x:auto}"
            ".pages{padding:12px;display:grid;gap:16px;justify-items:start}"
            ".page{min-width:612px;background:#fff;color:#111;box-shadow:0 2px 12px rgba(0,0,0,.35);overflow:auto}"
            ".page>svg{max-width:none;height:auto;display:block}",
            encoding="utf-8",
        )
        pipeline_js = preview_assets_dir / "pipeline.js"
        pipeline_js.write_text(
            "(function(){"
            "function parseJson(id,f){try{return JSON.parse((document.getElementById(id)||{}).textContent||'');}catch(_){return f;}}"
            "function hasRuntime(){return !!(window.VMPrint||window.vmprint||window.CanvasContext);}"
            "function renderSvgPages(root,pages){if(!root)return;root.innerHTML='';for(const s of (pages||[])){const d=document.createElement('div');d.className='page';d.innerHTML=String(s||'');root.appendChild(d);}}"
            "function renderLayoutBoxes(root,d){if(!root)return;root.innerHTML='';const pages=(d&&d.pages)||[];"
            "for(const pg of pages){const w=pg.width||595,h=pg.height||842;const el=document.createElement('div');el.className='page';el.style.width=w+'px';el.style.height=h+'px';el.style.position='relative';el.style.background='#fff';el.style.color='#111';el.style.boxShadow='0 2px 12px rgba(0,0,0,.35)';el.style.overflow='hidden';"
            "for(const b of (pg.boxes||[])){const n=document.createElement('div');n.className='box';n.style.position='absolute';n.style.left=(b.x||0)+'px';n.style.top=(b.y||0)+'px';n.style.width=(b.w||0)+'px';n.style.height=(b.h||0)+'px';n.style.border='1px dashed rgba(0,0,0,.12)';n.style.fontSize='10px';n.style.lineHeight='1.2';n.style.overflow='hidden';n.style.whiteSpace='pre-wrap';"
            "const t=(b.lines&&b.lines.length)?(b.lines.map(l=>(l.segments||[]).map(s=>s.text||'').join('')).join('\\n')):(b.type||'');n.textContent=t;el.appendChild(n);}root.appendChild(el);}}"
            "window.HomeClawVmprintPipeline={parseJson:parseJson,hasRuntime:hasRuntime,renderSvgPages:renderSvgPages,renderLayoutBoxes:renderLayoutBoxes};"
            "})();",
            encoding="utf-8",
        )
        ui_js = preview_assets_dir / "ui.js"
        ui_js.write_text(
            "(function(){"
            "function boot(){const p=window.HomeClawVmprintPipeline;if(!p)return;"
            "const root=document.getElementById('root');if(!root)return;"
            "const svgs=p.parseJson('svg-pages-data',[]);let layout=null;"
            "try{const le=document.getElementById('layout-data');if(le)layout=JSON.parse(le.textContent||'{}');}catch(_){layout=null;}"
            "if(svgs&&svgs.length){p.renderSvgPages(root,svgs);}"
            "else if(layout&&layout.pages&&layout.pages.length){p.renderLayoutBoxes(root,layout);}"
            "}"
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


def _stock_change_cell(raw: Any) -> str:
    """Ticker-style change column: arrow prefix when sign is obvious."""
    s = str(raw or "").strip()
    if not s or s == "-":
        return s if s else "-"
    if s.startswith("-"):
        return f"▼ {s}"
    if s.startswith("+"):
        return f"▲ {s}"
    try:
        v = float(s.rstrip("%").replace(",", ""))
        if v < 0:
            return f"▼ {s}"
        if v > 0:
            return f"▲ {s}"
    except ValueError:
        pass
    return s


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


def _daily_brief_items_normalized(data: Dict[str, Any]) -> list[Dict[str, str]]:
    """Shared item shape for table and magazine daily-brief layouts."""
    raw = data.get("items") or data.get("results") or []
    if not isinstance(raw, list):
        return []
    out: list[Dict[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        src = str(it.get("feed") or it.get("source") or it.get("site") or "").strip()
        snip = str(
            it.get("summary") or it.get("description") or it.get("content") or it.get("snippet") or ""
        ).strip()
        if len(snip) > 2000:
            snip = snip[:1997] + "..."
        link = str(it.get("link") or it.get("url") or "").strip()
        if h or link:
            out.append({"title": h or "(no title)", "feed": src, "summary": snip, "link": link})
    return out


def _split_summary_bodies(summary: str, max_first: int = 520, max_second: int = 560) -> list[str]:
    """Split long RSS summary into 1–2 story paragraphs (deterministic)."""
    t = (summary or "").strip()
    if not t:
        return []
    if len(t) <= max_first:
        return [t]
    cut = t.rfind("\n\n", 0, max_first)
    if cut >= 80:
        a, b = t[:cut].strip(), t[cut:].strip()
        if len(b) > max_second:
            b = b[: max_second - 1] + "…"
        return [a, b] if b else [a]
    cut = t.rfind(". ", 100, max_first)
    if cut < 0:
        cut = t.rfind("。", 100, max_first)
    if cut > 0:
        a, b = t[: cut + 1].strip(), t[cut + 1 :].strip()
        if len(b) > max_second:
            b = b[: max_second - 1] + "…"
        return [a, b] if b else [a]
    a = t[:max_first].rstrip() + "…"
    b = t[max_first : max_first + max_second].strip()
    out = [a]
    if b:
        out.append(b + ("…" if len(t) > max_first + max_second else ""))
    return out


def _host_label_from_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        parsed = urlparse(u if "://" in u else f"https://{u}")
        h = (parsed.netloc or "").lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _magazine_editorial_chrome(
    mast: str, as_of: str, theme: str, folio_right: str, page_bg: str
) -> Dict[str, Any]:
    return {
        "layout": {
            "pageSize": {"width": 595, "height": 842},
            "orientation": "portrait",
            "margins": {"top": 38, "right": 42, "bottom": 38, "left": 42},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.4,
            "pageBackground": page_bg,
            "hyphenation": "soft",
            "justifyEngine": "advanced",
            "justifyStrategy": "auto",
        },
        "styles": {
            "kicker": {"fontSize": 7, "letterSpacing": 1.6, "marginBottom": 5, "keepWithNext": True, "color": "#78350f"},
            "title": {"fontSize": 26, "fontWeight": "bold", "marginBottom": 8, "keepWithNext": True, "color": "#1c1917"},
            "meta": {"fontSize": 9, "marginBottom": 10, "color": "#57534e", "fontStyle": "italic"},
            "headline": {
                "fontSize": 19,
                "fontWeight": "bold",
                "lineHeight": 1.2,
                "marginBottom": 5,
                "keepWithNext": True,
                "hyphenation": "off",
                "color": "#292524",
            },
            "deck": {
                "fontSize": 9.5,
                "fontStyle": "italic",
                "lineHeight": 1.35,
                "color": "#44403c",
                "marginBottom": 6,
                "keepWithNext": True,
            },
            "byline": {"fontSize": 7.5, "color": "#78716c", "marginBottom": 8, "keepWithNext": True},
            "body": {
                "fontSize": 9.5,
                "lineHeight": 1.45,
                "marginBottom": 8,
                "textAlign": "justify",
                "allowLineSplit": True,
                "orphans": 2,
                "widows": 2,
            },
            "sidebar_head": {
                "fontSize": 8.5,
                "fontWeight": "bold",
                "letterSpacing": 0.8,
                "color": "#1c1917",
                "marginBottom": 4,
                "keepWithNext": True,
            },
            "sidebar_rule": {
                "fontSize": 0.1,
                "marginBottom": 6,
                "borderBottomWidth": 0.75,
                "borderBottomColor": "#d6d3d1",
            },
            "sidebar_body": {
                "fontSize": 8.2,
                "lineHeight": 1.35,
                "color": "#44403c",
                "marginBottom": 7,
                "textAlign": "left",
            },
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
                        "stripLayout": {
                            "tracks": [{"mode": "flex", "fr": 1}, {"mode": "fixed", "value": 86}, {"mode": "flex", "fr": 1}],
                            "gap": 8,
                        },
                        "slots": [
                            {"id": "left", "elements": [{"type": "folio-left", "content": "HomeClaw"}]},
                            {"id": "center", "elements": [{"type": "folio-page", "content": "Page {pageNumber} / {totalPages}"}]},
                            {"id": "right", "elements": [{"type": "folio-right", "content": folio_right}]},
                        ],
                    }
                ]
            }
        },
    }


def _assemble_editorial_magazine_ast(
    *,
    page_kicker: str,
    mast: str,
    meta_line: str,
    theme: str,
    as_of: str,
    folio_right: str,
    page_bg: str,
    lead_elements: List[Dict[str, Any]],
    rail_elements: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    chrome = _magazine_editorial_chrome(mast, as_of, theme, folio_right, page_bg)
    return {
        "documentVersion": "1.1",
        **chrome,
        "elements": [
            {"type": "kicker", "content": page_kicker},
            {"type": "title", "content": mast},
            {"type": "meta", "content": meta_line},
            {
                "type": "zone-map",
                "content": "",
                "zoneLayout": {"columns": [{"mode": "flex", "fr": 2}, {"mode": "flex", "fr": 1}], "gap": 16},
                "zones": [
                    {"id": "lead", "elements": lead_elements},
                    {"id": "rail", "elements": rail_elements},
                ],
            },
        ],
    }


def _editorial_items_to_lead_rail(
    items: List[Dict[str, str]],
    sidebar_head: str,
    *,
    empty_kicker: str,
    empty_headline: str,
    empty_body: str,
    top_story_fallback: str = "TOP STORY",
    no_snippet_line: str = "No excerpt — open the link for the full story.",
    max_sidebar: int = 16,
    lead_body_columns: int = 1,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    lead_elements: List[Dict[str, Any]]
    if not items:
        lead_elements = [
            {"type": "kicker", "content": empty_kicker},
            {"type": "headline", "content": empty_headline},
            {"type": "body", "content": empty_body},
        ]
    else:
        first = items[0]
        kicker_line = (top_story_fallback or "TOP STORY").strip().upper()
        if len(kicker_line) > 36:
            kicker_line = kicker_line[:33] + "…"
        raw_deck = first["summary"].strip() or no_snippet_line
        deck = raw_deck[:320] + ("…" if len(raw_deck) > 320 else "")
        link = (first.get("link") or "").strip()
        byline = (first.get("feed") or "Source").strip()
        story_children: List[Dict[str, Any]] = []
        for para in _split_summary_bodies(first["summary"]):
            story_children.append(
                {
                    "type": "body",
                    "content": para,
                    "properties": {"style": {"textAlign": "justify"}},
                }
            )
        if not story_children:
            story_children.append(
                {
                    "type": "body",
                    "content": "No summary text — see the link below." if link else no_snippet_line,
                    "properties": {"style": {"textAlign": "left"}},
                }
            )
        if link:
            story_children.append(
                {
                    "type": "body",
                    "content": link,
                    "properties": {
                        "style": {
                            "fontSize": 8.5,
                            "lineHeight": 1.35,
                            "textAlign": "left",
                            "marginTop": 2,
                            "color": "#57534e",
                        }
                    },
                }
            )
        cols = max(1, min(3, int(lead_body_columns)))
        lead_elements = [
            {"type": "kicker", "content": kicker_line},
            {"type": "headline", "content": first["title"]},
            {"type": "deck", "content": deck},
            {"type": "byline", "content": byline},
            {
                "type": "story",
                "content": "",
                "columns": cols,
                "gutter": 12,
                "balance": False,
                "children": story_children,
            },
        ]

    side_elements: List[Dict[str, Any]] = [
        {"type": "sidebar_head", "content": sidebar_head},
        {"type": "sidebar_rule", "content": ""},
    ]
    if len(items) <= 1:
        side_elements.append({"type": "sidebar_body", "content": "—"})
    else:
        for it in items[1 : 1 + max_sidebar]:
            sn = it["summary"]
            snippet = sn[:200] + ("…" if len(sn) > 200 else "")
            lk = (it.get("link") or "").strip()
            src = (it.get("feed") or "").strip()
            parts_r: list[str] = [it["title"]]
            if snippet:
                parts_r.append(snippet)
            if src:
                parts_r.append(f"— {src}")
            if lk:
                parts_r.append(lk)
            line = "\n\n".join(parts_r)
            side_elements.append({"type": "sidebar_body", "content": line})
    return lead_elements, side_elements


def _daily_brief_magazine_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    """
    Two-column editorial magazine: same masthead/zone lead as newspaper, but secondary items are
    separate story blocks (kicker → headline → byline → justified body) in 2 columns, like a
    printed front page—header/footer still come from layout + optional chrome merge.
    """
    return _daily_brief_newspaper_ast(
        data,
        title,
        theme,
        folio_footer_right="Magazine",
        include_headline_index_table=False,
        secondary_story_columns=2,
        secondary_story_balance=True,
        secondary_stories_as_blocks=True,
    )


def _pull_quote_from_lead_summary(summary: str) -> Optional[str]:
    """Short excerpt for a float pull-quote (specimen-style), or None."""
    t = (summary or "").strip().replace("\n\n", " ")
    if len(t) < 50:
        return None
    cut = -1
    for sep in ("。", "！", "？", ". ", "! ", "? "):
        idx = t.find(sep)
        if 40 <= idx < 260:
            cut = idx + len(sep)
            break
    frag = (t[:cut] if cut > 0 else t[:220]).strip()
    if len(frag) < 40:
        frag = t[:min(200, len(t))].strip()
    if len(frag) < 40:
        return None
    if len(frag) > 240:
        frag = frag[:237] + "…"
    return f"“{frag}”"


def _specimen_daily_brief_styles(page_bg: str, accent: str, ink: str) -> Dict[str, Any]:
    """VMPrint practitioner specimen (newsletter front page): Tinos/Cousine/Arimo."""
    return {
        "masthead": {
            "fontFamily": "Arimo",
            "fontSize": 38,
            "fontWeight": "bold",
            "letterSpacing": 6,
            "textAlign": "center",
            "color": ink,
            "marginBottom": 2,
        },
        "masthead-rule": {
            "fontSize": 0.1,
            "marginBottom": 4,
            "borderBottomWidth": 3,
            "borderBottomColor": ink,
        },
        "dateline": {
            "fontFamily": "Cousine",
            "fontSize": 6.5,
            "letterSpacing": 1,
            "textAlign": "center",
            "color": "#555",
            "marginBottom": 4,
        },
        "edition-rule": {
            "fontSize": 0.1,
            "marginBottom": 12,
            "borderBottomWidth": 0.75,
            "borderBottomColor": "#999",
        },
        "kicker": {
            "fontFamily": "Cousine",
            "fontSize": 6.2,
            "letterSpacing": 1.4,
            "color": accent,
            "marginBottom": 5,
            "keepWithNext": True,
            "hyphenation": "off",
        },
        "headline": {
            "fontFamily": "Tinos",
            "fontSize": 20,
            "fontWeight": "bold",
            "lineHeight": 1.18,
            "color": "#111",
            "marginBottom": 5,
            "keepWithNext": True,
            "hyphenation": "off",
        },
        "headline-lg": {
            "fontFamily": "Tinos",
            "fontSize": 26,
            "fontWeight": "bold",
            "lineHeight": 1.15,
            "color": "#111",
            "marginBottom": 6,
            "keepWithNext": True,
            "hyphenation": "off",
        },
        "deck": {
            "fontFamily": "Arimo",
            "fontSize": 9,
            "fontStyle": "italic",
            "lineHeight": 1.35,
            "color": "#333",
            "marginBottom": 8,
            "keepWithNext": True,
        },
        "byline": {
            "fontFamily": "Cousine",
            "fontSize": 6.5,
            "letterSpacing": 0.8,
            "color": "#555",
            "marginBottom": 8,
            "keepWithNext": True,
        },
        "body": {
            "fontSize": 9.5,
            "lineHeight": 1.42,
            "textAlign": "justify",
            "marginBottom": 7,
            "allowLineSplit": True,
            "orphans": 2,
            "widows": 2,
            "hyphenation": "auto",
        },
        "pull-quote": {
            "fontFamily": "Tinos",
            "fontSize": 12.5,
            "fontStyle": "italic",
            "fontWeight": "bold",
            "lineHeight": 1.3,
            "color": accent,
            "textAlign": "center",
            "paddingTop": 8,
            "paddingBottom": 8,
            "borderTopWidth": 1.5,
            "borderTopColor": accent,
            "borderBottomWidth": 1.5,
            "borderBottomColor": accent,
            "marginBottom": 0,
        },
        "col-rule": {
            "fontSize": 0.1,
            "borderBottomWidth": 0.5,
            "borderBottomColor": "#ccc",
            "marginBottom": 10,
        },
        "section-flag": {
            "fontFamily": "Cousine",
            "fontSize": 6.5,
            "fontWeight": "bold",
            "letterSpacing": 1.5,
            "color": page_bg,
            "backgroundColor": ink,
            "paddingTop": 3,
            "paddingBottom": 3,
            "paddingLeft": 5,
            "paddingRight": 5,
            "marginBottom": 8,
        },
        "sidebar-head": {
            "fontFamily": "Arimo",
            "fontSize": 8,
            "fontWeight": "bold",
            "letterSpacing": 0.5,
            "color": ink,
            "marginBottom": 3,
            "keepWithNext": True,
        },
        "sidebar-body": {
            "fontFamily": "Arimo",
            "fontSize": 8,
            "lineHeight": 1.35,
            "color": "#333",
            "marginBottom": 6,
            "textAlign": "left",
        },
        "table-header": {
            "fontFamily": "Cousine",
            "fontSize": 6.5,
            "fontWeight": "bold",
            "paddingTop": 4,
            "paddingBottom": 4,
            "paddingLeft": 5,
            "paddingRight": 5,
            "color": page_bg,
            "backgroundColor": ink,
        },
        "table-cell": {
            "fontFamily": "Cousine",
            "fontSize": 7.5,
            "paddingTop": 4,
            "paddingBottom": 4,
            "paddingLeft": 5,
            "paddingRight": 5,
            "color": "#222",
        },
        "table-cell-alt": {
            "fontFamily": "Cousine",
            "fontSize": 7.5,
            "paddingTop": 4,
            "paddingBottom": 4,
            "paddingLeft": 5,
            "paddingRight": 5,
            "color": "#222",
            "backgroundColor": "#f0ede4",
        },
        "caption": {
            "fontFamily": "Arimo",
            "fontSize": 7,
            "fontStyle": "italic",
            "color": "#666",
            "textAlign": "center",
            "marginBottom": 8,
        },
        "footer-text": {
            "fontFamily": "Cousine",
            "fontSize": 6.5,
            "color": "#666",
            "letterSpacing": 0.5,
        },
    }


def _specimen_daily_brief_header_footer_strip(mast: str, folio_footer_right: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Running head + folio matching upstream specimen (`footer-text` in header strip)."""
    head_mast = (mast or "DISPATCH").strip()[:80]
    header = {
        "default": {
            "elements": [
                {
                    "type": "strip",
                    "content": "",
                    "stripLayout": {"tracks": [{"mode": "flex", "fr": 1}, {"mode": "flex", "fr": 1}], "gap": 0},
                    "slots": [
                        {"id": "run_left", "elements": [{"type": "footer-text", "content": head_mast}]},
                        {
                            "id": "run_right",
                            "elements": [
                                {
                                    "type": "footer-text",
                                    "content": "PAGE {pageNumber} OF {totalPages}",
                                    "properties": {"style": {"textAlign": "right"}},
                                }
                            ],
                        },
                    ],
                    "properties": {
                        "style": {
                            "borderBottomWidth": 0.5,
                            "borderBottomColor": "#ccc",
                            "paddingBottom": 4,
                            "marginBottom": 10,
                        }
                    },
                }
            ]
        },
        "firstPage": None,
    }
    footer = {
        "default": {
            "elements": [
                {
                    "type": "strip",
                    "content": "",
                    "stripLayout": {
                        "tracks": [{"mode": "flex", "fr": 1}, {"mode": "fixed", "value": 86}, {"mode": "flex", "fr": 1}],
                        "gap": 8,
                    },
                    "slots": [
                        {"id": "fl", "elements": [{"type": "footer-text", "content": "HomeClaw"}]},
                        {"id": "fc", "elements": [{"type": "footer-text", "content": "PAGE {pageNumber} OF {totalPages}"}]},
                        {"id": "fr", "elements": [{"type": "footer-text", "content": folio_footer_right}]},
                    ],
                }
            ]
        }
    }
    return header, footer


def _format_newspaper_dateline(as_of: str) -> str:
    s = (as_of or "").strip() or _now_local_str()
    date_part = s.replace("T", " ").split()[0] if s else ""
    try:
        d = datetime.strptime(date_part[:10], "%Y-%m-%d")
        return d.strftime("%A, %B %d, %Y").upper()
    except ValueError:
        return s[:100].upper()


def _daily_brief_newspaper_ast(
    data: Dict[str, Any],
    title: str,
    theme: str = "dispatch",
    *,
    folio_footer_right: str = "Newspaper",
    include_headline_index_table: bool = True,
    secondary_story_columns: int = 3,
    secondary_story_balance: bool = False,
    secondary_stories_as_blocks: bool = False,
) -> Dict[str, Any]:
    """
    Front-page style from RSS: masthead + dateline, lead + sidebar (optional pull-quote),
    multi-column secondary heads, optional headline index table. Typography matches VMPrint
    practitioner specimen (Tinos/Cousine/Arimo, footer-text running head).

    When ``secondary_stories_as_blocks`` is True, each secondary RSS item is its own ``story``
    (same column count as ``secondary_story_columns``) so blocks stack vertically; pagination
    is handled by VMPrint as content fills pages.
    """
    items = _daily_brief_items_normalized(data)[:22]
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    page_bg = "#f7f7f7" if theme == "minimal" else "#faf8f3"
    date_line = _format_newspaper_dateline(as_of)
    dateline_content = f"HOMECLAW · {date_line}"

    accent = "#8b2020" if theme == "dispatch" else "#334155"
    ink = "#1a1a1a"
    styles = _specimen_daily_brief_styles(page_bg, accent, ink)
    hdr, ftr = _specimen_daily_brief_header_footer_strip(mast, folio_footer_right)

    lead_elements: List[Dict[str, Any]]
    if not items:
        lead_elements = [
            {"type": "kicker", "content": "DIGEST"},
            {"type": "headline-lg", "content": "No articles in this run"},
            {
                "type": "body",
                "content": "Feeds returned no usable items. Check config/feeds.yaml, network, and filters.",
            },
        ]
    else:
        first = items[0]
        sec_k = (first["feed"] or "TOP STORY").strip().upper()
        if len(sec_k) > 36:
            sec_k = sec_k[:33] + "…"
        raw_deck = first["summary"].strip() or "No excerpt — open the article link for the full story."
        deck = raw_deck[:320] + ("…" if len(raw_deck) > 320 else "")
        link = first["link"]
        byline = (first["feed"] or "Source").strip()
        if link:
            byline = f"{byline}\n{link}"
        pq = _pull_quote_from_lead_summary(first["summary"])
        story_children: List[Dict[str, Any]] = []
        for i, para in enumerate(_split_summary_bodies(first["summary"])):
            cell: Dict[str, Any] = {
                "type": "body",
                "content": para,
                "properties": {"style": {"textAlign": "justify"}},
            }
            if i == 0 and len(para) >= 120:
                cell["dropCap"] = {
                    "enabled": True,
                    "lines": 3,
                    "gap": 4,
                    "characterStyle": {"fontFamily": "Tinos", "fontWeight": 700, "color": accent},
                }
            story_children.append(cell)
            if i == 0 and pq:
                story_children.append(
                    {
                        "type": "pull-quote",
                        "content": pq,
                        "placement": {"mode": "float", "align": "right", "wrap": "around", "gap": 10},
                        "properties": {"style": {"width": 130, "height": 68}},
                    }
                )
        if not story_children:
            story_children.append(
                {
                    "type": "body",
                    "content": f"No summary text. Link: {link or '—'}",
                    "properties": {"style": {"textAlign": "left"}},
                }
            )
        lead_elements = [
            {"type": "kicker", "content": sec_k},
            {"type": "headline-lg", "content": first["title"]},
            {"type": "deck", "content": deck},
            {"type": "byline", "content": byline},
            {
                "type": "story",
                "content": "",
                "columns": 2,
                "gutter": 14,
                "balance": False,
                "children": story_children,
            },
        ]

    rail_title = "TODAY AT A GLANCE" if str(folio_footer_right).strip().lower() == "magazine" else "IN BRIEF"
    sidebar_els: List[Dict[str, Any]] = [
        {"type": "sidebar-head", "content": rail_title},
        {"type": "col-rule", "content": ""},
    ]
    if len(items) <= 1:
        sidebar_els.append({"type": "sidebar-body", "content": "—"})
    else:
        for it in items[1:12]:
            sn = it["summary"]
            snippet = sn[:120] + ("…" if len(sn) > 120 else "")
            lk = (it.get("link") or "").strip()
            line = f"• {it['title']}"
            if it["feed"]:
                line += f"\n{it['feed']}"
            if snippet:
                line += f"\n{snippet}"
            if lk:
                line += f"\n{lk}"
            sidebar_els.append({"type": "sidebar-body", "content": line})

    multi_children: List[Dict[str, Any]] = []
    secondary_story_blocks: List[Dict[str, Any]] = []
    if len(items) > 1:
        for it in items[1:8]:
            fk = (it["feed"] or "FEED").strip().upper()
            if len(fk) > 34:
                fk = fk[:31] + "…"
            by = (it["feed"] or "Source").strip()
            lk = (it.get("link") or "").strip()
            if lk:
                by = f"{by}\n{lk}"
            sn = it["summary"].strip() or "—"
            body_text = sn[:480] + ("…" if len(sn) > 480 else "")
            block_ch = [
                {"type": "kicker", "content": fk},
                {"type": "headline", "content": it["title"][:220]},
                {"type": "byline", "content": by[:500]},
                {
                    "type": "body",
                    "content": body_text,
                    "properties": {"style": {"textAlign": "justify"}},
                },
            ]
            if secondary_stories_as_blocks:
                secondary_story_blocks.append(
                    {
                        "type": "story",
                        "content": "",
                        "columns": max(1, min(4, int(secondary_story_columns))),
                        "gutter": 14,
                        "balance": bool(secondary_story_balance),
                        "children": block_ch,
                    }
                )
            else:
                multi_children.extend(block_ch)

    table_block: Optional[Dict[str, Any]] = None
    if include_headline_index_table:
        index_rows: List[Dict[str, Any]] = []
        for i, it in enumerate(items, start=1):
            sn = it["summary"]
            snip = sn[:200] + ("…" if len(sn) > 200 else "")
            lk = it["link"]
            link_show = lk if len(lk) <= 48 else lk[:45] + "…"
            alt = i % 2 == 0
            ct, st = ("table-cell-alt", "table-cell-alt") if alt else ("table-cell", "table-cell")
            index_rows.append(
                {
                    "type": "table-row",
                    "content": "",
                    "children": [
                        {"type": ct, "content": str(i)},
                        {"type": st, "content": it["title"][:180] or "—"},
                        {"type": ct, "content": it["feed"] or "—"},
                        {"type": st, "content": snip or "—"},
                        {"type": ct, "content": link_show or "—"},
                    ],
                }
            )

        table_block = {
            "type": "table",
            "content": "",
            "table": {
                "headerRows": 1,
                "repeatHeader": True,
                "columnGap": 3,
                "columns": [
                    {"mode": "fixed", "value": 22},
                    {"mode": "flex", "fr": 1.4},
                    {"mode": "fixed", "value": 56},
                    {"mode": "flex", "fr": 1.6},
                    {"mode": "flex", "fr": 1},
                ],
            },
            "children": [
                {
                    "type": "table-row",
                    "content": "",
                    "properties": {"semanticRole": "header"},
                    "children": [
                        {"type": "table-header", "content": "#"},
                        {"type": "table-header", "content": "Headline"},
                        {"type": "table-header", "content": "Feed"},
                        {"type": "table-header", "content": "Snippet"},
                        {"type": "table-header", "content": "Link"},
                    ],
                },
                *index_rows,
            ],
        }

    body_elements: List[Dict[str, Any]] = [
        {"type": "masthead", "content": mast},
        {"type": "masthead-rule", "content": ""},
        {"type": "dateline", "content": dateline_content},
        {"type": "edition-rule", "content": ""},
        {
            "type": "zone-map",
            "content": "",
            "properties": {"style": {"marginBottom": 10}},
            "zoneLayout": {
                "columns": [{"mode": "flex", "fr": 2}, {"mode": "flex", "fr": 1}],
                "gap": 22 if str(folio_footer_right).strip().lower() == "magazine" else 18,
            },
            "zones": [
                {"id": "lead", "elements": lead_elements},
                {"id": "sidebar", "elements": sidebar_els},
            ],
        },
    ]
    if secondary_stories_as_blocks and secondary_story_blocks:
        body_elements.append({"type": "col-rule", "content": ""})
        body_elements.append({"type": "section-flag", "content": "MORE HEADLINES"})
        for i, blk in enumerate(secondary_story_blocks):
            body_elements.append(blk)
            if i < len(secondary_story_blocks) - 1:
                body_elements.append(
                    {
                        "type": "col-rule",
                        "content": "",
                        "properties": {"style": {"marginTop": 6, "marginBottom": 10}},
                    }
                )
    elif multi_children:
        body_elements += [
            {"type": "col-rule", "content": ""},
            {"type": "section-flag", "content": "MORE HEADLINES"},
            {
                "type": "story",
                "content": "",
                "columns": max(1, min(4, int(secondary_story_columns))),
                "gutter": 14,
                "balance": bool(secondary_story_balance),
                "children": multi_children,
            },
        ]
    if include_headline_index_table and table_block is not None:
        body_elements += [
            {"type": "col-rule", "content": ""},
            {"type": "section-flag", "content": "HEADLINE INDEX"},
            table_block,
            {"type": "caption", "content": f"RSS digest · As of {as_of}"},
        ]
    else:
        body_elements.append({"type": "caption", "content": f"RSS digest · As of {as_of}"})

    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 612, "height": 792},
            "orientation": "portrait",
            "margins": {"top": 36, "right": 40, "bottom": 40, "left": 40},
            "fontFamily": "Tinos",
            "fontSize": 9.5,
            "lineHeight": 1.42,
            "pageBackground": page_bg,
            "hyphenation": "auto",
            "justifyEngine": "advanced",
            "justifyStrategy": "auto",
        },
        "styles": styles,
        "header": hdr,
        "footer": ftr,
        "elements": body_elements,
    }


def _web_search_results_normalized(data: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = data.get("results") or data.get("items") or []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        url = str(it.get("url") or it.get("link") or "").strip()
        snip = str(
            it.get("content") or it.get("snippet") or it.get("description") or it.get("summary") or ""
        ).strip()
        if len(snip) > 2000:
            snip = snip[:1997] + "..."
        host = _host_label_from_url(url)
        feed = host.upper() if host else "RESULT"
        if h or url:
            out.append({"title": h or "(no title)", "feed": feed, "summary": snip, "link": url})
    return out


def _web_search_magazine_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    items = _web_search_results_normalized(data)[:20]
    query = str(data.get("query") or data.get("q") or "").strip()
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    page_bg = "#f7f7f7" if theme == "minimal" else "#faf8f5"
    meta_line = f"Query: {query}" if query else f"As of {as_of}"
    lead, rail = _editorial_items_to_lead_rail(
        items,
        "MORE RESULTS",
        empty_kicker="SEARCH",
        empty_headline="No results for this query",
        empty_body="Try different keywords or check your search provider configuration.",
        top_story_fallback="TOP RESULT",
        no_snippet_line="No snippet returned — open the URL for the page.",
    )
    return _assemble_editorial_magazine_ast(
        page_kicker="WEB SEARCH",
        mast=mast,
        meta_line=meta_line,
        theme=theme,
        as_of=as_of,
        folio_right="Results",
        page_bg=page_bg,
        lead_elements=lead,
        rail_elements=rail,
    )


def _stock_items_editorial_normalized(data: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = data.get("watchlist") or data.get("items") or []
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or it.get("ticker") or "").strip() or "-"
        name = str(it.get("name") or "").strip()
        title = f"{sym} — {name}" if name else sym
        if not title.strip() or title.strip() == "-":
            title = sym
        price = str(it.get("price") or it.get("last") or "").strip()
        ch_raw = it.get("change_pct") or it.get("pct") or it.get("change") or "-"
        ch = str(_stock_change_cell(ch_raw))
        note = str(it.get("note") or it.get("alert") or "").strip()
        parts: List[str] = []
        if price and price != "-":
            parts.append(f"Last {price}")
        parts.append(f"Change {ch}")
        if note:
            parts.append(note)
        summary = " · ".join(parts) if parts else "—"
        out.append({"title": title, "feed": sym, "summary": summary, "link": ""})
    return out


def _stock_magazine_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    items = _stock_items_editorial_normalized(data)[:30]
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    page_bg = "#f7f7f7" if theme == "minimal" else "#eef2f6"
    lead, rail = _editorial_items_to_lead_rail(
        items,
        "MORE SYMBOLS",
        empty_kicker="WATCHLIST",
        empty_headline="No symbols in this snapshot",
        empty_body="Add tickers to your watchlist or retry after the data feed loads.",
        top_story_fallback="TOP SYMBOL",
        no_snippet_line="No price detail — check your market data source.",
    )
    return _assemble_editorial_magazine_ast(
        page_kicker="MARKETS",
        mast=mast,
        meta_line=f"Market snapshot · As of {as_of}",
        theme=theme,
        as_of=as_of,
        folio_right="Watchlist",
        page_bg=page_bg,
        lead_elements=lead,
        rail_elements=rail,
    )


def _weather_magazine_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    now = data.get("now") or {}
    if not isinstance(now, dict):
        now = {}
    days = data.get("forecast") or data.get("days") or []
    if not isinstance(days, list):
        days = []
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    loc = str(data.get("location") or data.get("city") or "Unknown").strip()
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    loc_show = mast
    if loc and loc.lower() != "unknown":
        loc_show = loc
    temp_s = str(now.get("temp") or "").strip()
    cond = str(now.get("condition") or "").strip()
    wx_bits = [x for x in (temp_s, cond) if x]
    wx_line = " · ".join(wx_bits)
    meta_line = f"{wx_line} · {as_of}" if wx_line else f"As of {as_of}"
    page_bg = "#f7f7f7" if theme == "minimal" else "#dbeafe"

    detail_lines = [
        f"Feels like: {now.get('feels_like') or '—'}",
        f"Humidity: {now.get('humidity') or '—'}",
        f"Wind: {now.get('wind') or '—'}",
    ]
    story_children: List[Dict[str, Any]] = []
    block = "\n\n".join(detail_lines)
    for para in _split_summary_bodies(block, max_first=200, max_second=200):
        story_children.append(
            {"type": "body", "content": para, "properties": {"style": {"textAlign": "justify"}}}
        )
    if not story_children:
        story_children.append(
            {
                "type": "body",
                "content": wx_line or "—",
                "properties": {"style": {"textAlign": "left"}},
            }
        )

    lead_elements: List[Dict[str, Any]] = [
        {"type": "kicker", "content": "RIGHT NOW"},
        {"type": "headline", "content": loc_show},
        {"type": "deck", "content": wx_line or "Conditions unavailable"},
        {"type": "byline", "content": f"Updated {as_of}"},
        {
            "type": "story",
            "content": "",
            "columns": 2,
            "gutter": 12,
            "balance": False,
            "children": story_children,
        },
    ]

    side_elements: List[Dict[str, Any]] = [
        {"type": "sidebar_head", "content": "OUTLOOK"},
        {"type": "sidebar_rule", "content": ""},
    ]
    if not days:
        side_elements.append({"type": "sidebar_body", "content": "—"})
    else:
        for d in days[:10]:
            if not isinstance(d, dict):
                continue
            day = str(d.get("day") or d.get("date") or "—")
            summ = str(d.get("summary") or d.get("condition") or "—")
            hi = str(d.get("high") or d.get("max") or "—")
            lo = str(d.get("low") or d.get("min") or "—")
            side_elements.append(
                {"type": "sidebar_body", "content": f"• {day}\n{summ}\nHigh {hi} · Low {lo}"}
            )

    return _assemble_editorial_magazine_ast(
        page_kicker="WEATHER",
        mast=mast,
        meta_line=meta_line,
        theme=theme,
        as_of=as_of,
        folio_right="Forecast",
        page_bg=page_bg,
        lead_elements=lead_elements,
        rail_elements=side_elements,
    )


def _daily_brief_ast(data: Dict[str, Any], title: str, theme: str = "dispatch") -> Dict[str, Any]:
    items = data.get("items") or data.get("results") or []
    if not isinstance(items, list):
        items = []
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    headline_rows = []
    for i, it in enumerate(items[:22], start=1):
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        src = str(it.get("feed") or it.get("source") or it.get("site") or "").strip()
        snip = str(
            it.get("summary") or it.get("description") or it.get("content") or it.get("snippet") or ""
        ).strip()
        if len(snip) > 260:
            snip = snip[:257] + "..."
        link = str(it.get("link") or it.get("url") or "").strip()
        headline_rows.append(
            {
                "type": "table-row",
                "content": "",
                "children": [
                    {"type": "table-cell", "content": str(i)},
                    {"type": "table-cell", "content": h or "Item"},
                    {"type": "table-cell", "content": src or "-"},
                    {"type": "table-cell", "content": snip or "-"},
                    {"type": "table-cell", "content": link or "-"},
                ],
            }
        )
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    # Portrait magazine page: tall folio, warm stock, stronger type hierarchy.
    page_bg = "#f7f7f7" if theme == "minimal" else "#f4ecdf"
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 595, "height": 842},
            "orientation": "portrait",
            "margins": {"top": 40, "right": 44, "bottom": 40, "left": 44},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.38,
            "pageBackground": page_bg,
        },
        "styles": {
            "kicker": {"fontSize": 7.5, "letterSpacing": 2.0, "marginBottom": 6, "keepWithNext": True, "color": "#6b5344"},
            "title": {"fontSize": 28, "fontWeight": "bold", "marginBottom": 10, "keepWithNext": True, "color": "#1c1917"},
            "meta": {"fontSize": 9.5, "marginBottom": 12, "color": "#57534e", "fontStyle": "italic"},
            "body": {"fontSize": 9.5, "marginBottom": 7, "textAlign": "left", "lineHeight": 1.4, "color": "#44403c"},
            "table-cell": {"fontSize": 8.5, "paddingTop": 4, "paddingBottom": 4, "paddingLeft": 4, "paddingRight": 4},
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
                            {"id": "right", "elements": [{"type": "folio-right", "content": "Magazine"}]},
                        ],
                    }
                ]
            }
        },
        "elements": [
            {"type": "kicker", "content": "FEATURE DIGEST"},
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
                                        {"mode": "fixed", "value": 22},
                                        {"mode": "flex", "fr": 1.25},
                                        {"mode": "fixed", "value": 56},
                                        {"mode": "flex", "fr": 2.25},
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
                                            {"type": "table-cell", "content": "Feed"},
                                            {"type": "table-cell", "content": "Snippet"},
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
                            {"type": "kicker", "content": "IN THIS ISSUE"},
                            {"type": "body", "content": "• Front-of-book scan: headlines, source, and pull quotes in one spread."},
                            {"type": "body", "content": "• Built for print-style pagination — PDF and canvas share the same layout."},
                            {"type": "body", "content": "• Open the preview link for the full folio; chat stays to bullet highlights."},
                        ],
                    },
                ],
            },
        ],
    }


def _web_search_ast(
    data: Dict[str, Any], title: str, theme: str = "dispatch", scripted_colophon: bool = False
) -> Dict[str, Any]:
    """Tavily / web_search shaped JSON: results[].title|url|content|snippet."""
    items = data.get("results") or data.get("items") or []
    if not isinstance(items, list):
        items = []
    query = str(data.get("query") or data.get("q") or "").strip()
    as_of = str(data.get("as_of") or data.get("generated_at") or _now_local_str())
    headline_rows = []
    for i, it in enumerate(items[:20], start=1):
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        url = str(it.get("url") or it.get("link") or "").strip()
        snip = str(
            it.get("content") or it.get("snippet") or it.get("description") or it.get("summary") or ""
        ).strip()
        if len(snip) > 220:
            snip = snip[:217] + "..."
        headline_rows.append(
            {
                "type": "table-row",
                "content": "",
                "children": [
                    {"type": "table-cell", "content": str(i)},
                    {"type": "table-cell", "content": h or "Result"},
                    {"type": "table-cell", "content": snip or "-"},
                    {"type": "table-cell", "content": url or "-"},
                ],
            }
        )
    if theme not in ("dispatch", "minimal"):
        theme = "dispatch"
    mast = title.upper() if theme == "dispatch" else title
    sub = f"Query: {query}" if query else f"As of {as_of}"
    head_elements: list = [
        {"type": "kicker", "content": "BRIEFING NOTES"},
        {"type": "title", "content": mast},
        {"type": "meta", "content": sub},
    ]
    if scripted_colophon:
        head_elements.append(
            {"type": "meta", "name": "colophon", "content": "Resolving page count after layout…"}
        )
    ws_bg = "#f7f7f7" if theme == "minimal" else "#faf8f5"
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 595, "height": 842},
            "orientation": "portrait",
            "margins": {"top": 48, "right": 52, "bottom": 48, "left": 52},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.42,
            "pageBackground": ws_bg,
        },
        "styles": {
            "kicker": {
                "fontSize": 8,
                "letterSpacing": 1.5,
                "marginBottom": 5,
                "keepWithNext": True,
                "color": "#64748b",
            },
            "title": {
                "fontSize": 20,
                "fontWeight": "bold",
                "marginBottom": 6,
                "keepWithNext": True,
                "color": "#1e293b",
            },
            "meta": {"fontSize": 9.5, "marginBottom": 14, "color": "#64748b"},
            "table-cell": {"fontSize": 8.5, "paddingTop": 4, "paddingBottom": 4, "paddingLeft": 5, "paddingRight": 5},
        },
        "elements": head_elements
        + [
            {
                "type": "table",
                "content": "",
                "table": {
                    "headerRows": 1,
                    "repeatHeader": True,
                    "columnGap": 4,
                    "columns": [
                        {"mode": "fixed", "value": 24},
                        {"mode": "flex", "fr": 1},
                        {"mode": "flex", "fr": 2},
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
                            {"type": "table-cell", "content": "Title"},
                            {"type": "table-cell", "content": "Snippet"},
                            {"type": "table-cell", "content": "URL"},
                        ],
                    },
                    *headline_rows,
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
    loc_show = mast
    if loc and loc.strip() and loc.strip().lower() != "unknown":
        loc_show = loc.strip()
    temp_s = str(now.get("temp") or "").strip()
    cond = str(now.get("condition") or "").strip()
    wx_bits = [x for x in (temp_s, cond) if x]
    wx_line = " · ".join(wx_bits)
    meta_line = f"{wx_line} · {as_of}" if wx_line else f"As of {as_of}"
    wx_bg = "#f7f7f7" if theme == "minimal" else "#dbeafe"
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 720, "height": 405},
            "orientation": "landscape",
            "margins": {"top": 30, "right": 38, "bottom": 30, "left": 38},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.38,
            "pageBackground": wx_bg,
        },
        "styles": {
            "kicker": {
                "fontSize": 8,
                "letterSpacing": 1.4,
                "marginBottom": 4,
                "keepWithNext": True,
                "color": "#075985",
            },
            "title": {
                "fontSize": 26,
                "fontWeight": "bold",
                "marginBottom": 6,
                "keepWithNext": True,
                "color": "#0c4a6e",
            },
            "meta": {"fontSize": 10, "marginBottom": 12, "color": "#164e63"},
            "body": {"fontSize": 10.5, "marginBottom": 7, "lineHeight": 1.35, "color": "#134e4a"},
            "table-cell": {"fontSize": 9, "paddingTop": 4, "paddingBottom": 4, "paddingLeft": 5, "paddingRight": 5},
        },
        "elements": [
            {"type": "kicker", "content": "LOCAL FORECAST"},
            {"type": "title", "content": loc_show},
            {"type": "meta", "content": meta_line},
            {
                "type": "strip",
                "content": "",
                "stripLayout": {"tracks": [{"mode": "flex", "fr": 0.9}, {"mode": "flex", "fr": 1.1}], "gap": 16},
                "slots": [
                    {
                        "id": "left",
                        "elements": [
                            {"type": "kicker", "content": "NOW"},
                            {"type": "body", "content": wx_line or f"{cond or '—'} · {temp_s or '—'}"},
                            {"type": "body", "content": f"Feels like: {now.get('feels_like') or '—'}"},
                            {"type": "body", "content": f"Humidity: {now.get('humidity') or '—'}"},
                            {"type": "body", "content": f"Wind: {now.get('wind') or '—'}"},
                        ],
                    },
                    {
                        "id": "right",
                        "elements": [
                            {"type": "kicker", "content": "OUTLOOK"},
                            {
                                "type": "table",
                                "content": "",
                                "table": {
                                    "headerRows": 1,
                                    "repeatHeader": True,
                                    "columnGap": 5,
                                    "columns": [
                                        {"mode": "fixed", "value": 44},
                                        {"mode": "flex", "fr": 1},
                                        {"mode": "fixed", "value": 36},
                                        {"mode": "fixed", "value": 36},
                                    ],
                                },
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
                    {
                        "type": "table-cell",
                        "content": _stock_change_cell(
                            it.get("change_pct") or it.get("pct") or it.get("change") or "-"
                        ),
                    },
                    {"type": "table-cell", "content": str(it.get("note") or it.get("alert") or "-")},
                ],
            }
        )
    mast = title.upper() if theme == "dispatch" else title
    stk_bg = "#f7f7f7" if theme == "minimal" else "#eef2f6"
    return {
        "documentVersion": "1.1",
        "layout": {
            "pageSize": {"width": 720, "height": 405},
            "orientation": "landscape",
            "margins": {"top": 32, "right": 36, "bottom": 32, "left": 36},
            "fontFamily": "Arimo",
            "fontSize": 10,
            "lineHeight": 1.35,
            "pageBackground": stk_bg,
        },
        "styles": {
            "kicker": {"fontSize": 8, "letterSpacing": 1.4, "marginBottom": 4, "keepWithNext": True, "color": "#334155"},
            "title": {"fontSize": 22, "fontWeight": "bold", "marginBottom": 6, "keepWithNext": True, "color": "#0f172a"},
            "meta": {"fontSize": 9, "marginBottom": 12, "color": "#475569"},
            "table-cell": {"fontSize": 9, "paddingTop": 4, "paddingBottom": 4, "paddingLeft": 5, "paddingRight": 5},
        },
        "elements": [
            {"type": "kicker", "content": "WATCHLIST"},
            {"type": "title", "content": mast},
            {"type": "meta", "content": f"Market snapshot · As of {as_of}"},
            {
                "type": "table",
                "content": "",
                "table": {
                    "headerRows": 1,
                    "repeatHeader": True,
                    "columnGap": 5,
                    "columns": [
                        {"mode": "fixed", "value": 52},
                        {"mode": "flex", "fr": 1.2},
                        {"mode": "fixed", "value": 56},
                        {"mode": "fixed", "value": 64},
                        {"mode": "flex", "fr": 0.9},
                    ],
                },
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


def _ast_from_template(
    template: str,
    data: Dict[str, Any],
    title: str,
    theme: str,
    scripted_colophon: bool = False,
    document_layout: str = "digest_table",
) -> Dict[str, Any]:
    t = (template or "").strip().lower()
    layout = (document_layout or "").strip().lower()
    if t == "daily_brief":
        if layout == "magazine":
            return _daily_brief_magazine_ast(data, title=title, theme=theme)
        if layout == "newspaper":
            return _daily_brief_newspaper_ast(data, title=title, theme=theme)
        return _daily_brief_ast(data, title=title, theme=theme)
    if t == "weather":
        if layout == "magazine":
            return _weather_magazine_ast(data, title=title, theme=theme)
        return _weather_ast(data, title=title, theme=theme)
    if t == "stock":
        if layout == "magazine":
            return _stock_magazine_ast(data, title=title, theme=theme)
        return _stock_ast(data, title=title, theme=theme)
    if t == "web_search":
        if layout == "magazine":
            return _web_search_magazine_ast(data, title=title, theme=theme)
        return _web_search_ast(data, title=title, theme=theme, scripted_colophon=scripted_colophon)
    raise ValueError("template must be one of: daily_brief, weather, stock, web_search")


def _ast_collect_table_rows(ast_doc: Dict[str, Any], max_rows: int) -> list[list[str]]:
    rows: list[list[str]] = []

    def walk(node: Any) -> None:
        if len(rows) >= max_rows:
            return
        if isinstance(node, dict):
            if node.get("type") == "table-row":
                ch = node.get("children") or []
                if isinstance(ch, list):
                    cs: list[str] = []
                    for cell in ch:
                        if not isinstance(cell, dict):
                            continue
                        ct = str(cell.get("type") or "")
                        if ct in ("table-cell", "table-cell-alt", "table-header"):
                            cs.append(str(cell.get("content") or "").strip())
                    if cs:
                        rows.append(cs)
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(ast_doc.get("elements") or [])
    h = ast_doc.get("header") or {}
    if isinstance(h, dict):
        for v in h.values():
            if isinstance(v, dict):
                walk(v.get("elements") or [])
    f = ast_doc.get("footer") or {}
    if isinstance(f, dict):
        for v in f.values():
            if isinstance(v, dict):
                walk(v.get("elements") or [])
    return rows


def _ast_collect_body_digest_rows(ast_doc: Dict[str, Any], max_rows: int = 28, max_cell: int = 1200) -> list[list[str]]:
    """When no table rows exist (e.g. magazine layout), pull body/deck/headline text for the HTML digest."""
    rows: list[list[str]] = []

    def walk_el(el: Any) -> None:
        if len(rows) >= max_rows:
            return
        if not isinstance(el, dict):
            return
        t = str(el.get("type") or "")
        if t in (
            "body",
            "deck",
            "headline",
            "headline-lg",
            "byline",
            "sidebar_body",
            "sidebar-body",
            "masthead",
            "dateline",
            "caption",
        ):
            c = str(el.get("content") or "").strip()
            if c and c != "—":
                rows.append([c[:max_cell]])
        ch = el.get("children")
        if isinstance(ch, list):
            for c in ch:
                walk_el(c)
        for key in ("zones", "slots"):
            arr = el.get(key)
            if isinstance(arr, list):
                for n in arr:
                    if isinstance(n, dict):
                        for sub in n.get("elements") or []:
                            walk_el(sub)

    for top in ast_doc.get("elements") or []:
        walk_el(top)
    return rows


_DIGEST_URL_ONLY = re.compile(r"^https?://[^\s<>'\"]+$", re.I)
_DIGEST_URL_SUB = re.compile(r"https?://[^\s<>'\"]+", re.I)

_DIGEST_HEADER_TO_ROLE: Dict[str, str] = {
    "headline": "title",
    "title": "title",
    "feed": "source",
    "source": "source",
    "site": "source",
    "snippet": "snippet",
    "summary": "snippet",
    "description": "snippet",
    "link": "url",
    "url": "url",
}


def _digest_news_table_column_map(header_cells: list[str]) -> Optional[Dict[str, int]]:
    """Map digest table header (#, Headline, …) to semantic column indices for card layout."""
    if not header_cells or len(header_cells) < 3:
        return None
    if str(header_cells[0]).strip() != "#":
        return None
    roles: Dict[str, int] = {}
    for i in range(1, len(header_cells)):
        key = _DIGEST_HEADER_TO_ROLE.get(str(header_cells[i]).strip().lower())
        if key and key not in roles:
            roles[key] = i
    if "title" not in roles:
        return None
    if "snippet" not in roles and "url" not in roles:
        return None
    return roles


def _digest_render_news_cards(
    roles: Dict[str, int], data_rows: list[list[str]], max_cell: int
) -> str:
    """Vertical article cards: headline, optional source, snippet, URL last (not a multi-column grid)."""
    tit_i = roles["title"]
    snip_i = roles.get("snippet")
    src_i = roles.get("source")
    url_i = roles.get("url")
    parts: list[str] = [
        "<div role='feed' aria-label='Stories' style='margin-top:8px;border-top:2px solid #1c1917;"
        "display:flex;flex-direction:column;gap:16px;font-size:14px'>"
    ]
    for r in data_rows:
        if tit_i >= len(r):
            continue
        title = str(r[tit_i]).strip()
        if not title:
            continue
        snippet = ""
        if snip_i is not None and snip_i < len(r):
            snippet = str(r[snip_i]).strip()
        src = ""
        if src_i is not None and src_i < len(r):
            src = str(r[src_i]).strip()
        url = ""
        if url_i is not None and url_i < len(r):
            url = str(r[url_i]).strip()
        parts.append(
            "<article style='padding:14px 16px;background:#fff;border:1px solid #e7e5e4;border-radius:2px;"
            "box-shadow:0 1px 3px rgba(0,0,0,.06)'>"
        )
        parts.append(
            "<h3 style='margin:0 0 8px;font:600 17px/1.3 Georgia,\"Noto Serif SC\",\"Songti SC\",serif;color:#1c1917'>"
            f"{html.escape(title[:800])}</h3>"
        )
        if src and src != "-":
            parts.append(
                "<p style='margin:0 0 10px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#78716c'>"
                f"{html.escape(src[:240])}</p>"
            )
        if snippet and snippet != "-":
            parts.append(
                f"<p style='margin:0 0 12px;color:#44403c;line-height:1.5'>{_digest_mixed_text_html(snippet, max_cell)}</p>"
            )
        if url and url != "-":
            parts.append(f"<p style='margin:0;font-size:12px'>{_digest_cell_inner_html(url, max_cell)}</p>")
        parts.append("</article>")
    parts.append("</div>")
    return "".join(parts)


def _digest_mixed_text_html(text: str, max_cell: int) -> str:
    """Escape plain text but turn http(s) URLs into <a> tags (multiline-safe)."""
    s = (text or "")[:max_cell]
    if not s.strip():
        return ""
    parts: list[str] = []
    pos = 0
    for m in _DIGEST_URL_SUB.finditer(s):
        parts.append(html.escape(s[pos : m.start()]))
        url = m.group(0)
        while len(url) > 8 and url[-1] in ").,;:]":
            url = url[:-1]
        href_q = html.escape(url, quote=True)
        parts.append(
            f'<a href="{href_q}" target="_blank" rel="noopener noreferrer" '
            'style="color:#0c4a6e;text-decoration:underline;font-weight:500;word-break:break-all">'
            f"{html.escape(url)}</a>"
        )
        pos = m.end()
    parts.append(html.escape(s[pos:]))
    return "".join(parts).replace("\n", "<br>")


def _digest_cell_inner_html(cell: str, max_cell: int) -> str:
    """Table / digest cell: linkify URLs inside text; bare URL cell becomes one link."""
    raw = (cell or "")[:max_cell]
    s = raw.strip()
    if not s:
        return ""
    if s == "-":
        return html.escape(s)
    if _DIGEST_URL_ONLY.match(s):
        return _digest_mixed_text_html(s, max_cell)
    return _digest_mixed_text_html(raw, max_cell)


def _ast_digest_html(ast_doc: Dict[str, Any]) -> str:
    """
    Plain HTML with table text from the AST using browser system fonts so CJK stays readable when
    VMPrint SVG / layout boxes omit Han glyphs (Arimo-only pipeline).
    """
    max_rows = 24
    max_cell = 1500
    max_total = 100_000
    heads: list[str] = []
    for el in ast_doc.get("elements") or []:
        if not isinstance(el, dict):
            continue
        t = str(el.get("type") or "")
        if t == "zone-map":
            break
        c = str(el.get("content") or "").strip()
        if not c:
            continue
        c800 = c[:800]
        if t == "kicker":
            heads.append(
                "<p style='margin:0 0 6px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;"
                f"color:#78716c;font-weight:600'>{html.escape(c800)}</p>"
            )
        elif t == "title":
            heads.append(
                "<p style='margin:0 0 8px;font:600 24px/1.25 Georgia,\"Noto Serif SC\",\"Songti SC\",serif;"
                f"color:#1c1917'>{html.escape(c800)}</p>"
            )
        elif t == "meta":
            heads.append(
                f"<p style='margin:0 0 12px;font-size:13px;color:#57534e;font-style:italic'>{html.escape(c800)}</p>"
            )
        elif t == "masthead":
            heads.append(
                f"<p style='margin:0 0 4px;font:700 22px/1.2 system-ui,serif;letter-spacing:.12em;text-align:center;"
                f"color:#1a1a1a'>{html.escape(c800)}</p>"
            )
        elif t == "dateline":
            heads.append(
                f"<p style='margin:0 0 14px;font-size:11px;letter-spacing:.06em;text-align:center;color:#555'>"
                f"{html.escape(c800)}</p>"
            )
        elif t == "headline-lg":
            heads.append(
                f"<p style='margin:0 0 10px;font:700 18px/1.2 Georgia,\"Noto Serif SC\",serif;color:#111'>"
                f"{html.escape(c800)}</p>"
            )
    rows = _ast_collect_table_rows(ast_doc, max_rows=max_rows)
    if not rows:
        rows = _ast_collect_body_digest_rows(ast_doc, max_rows=max_rows, max_cell=max_cell)
    if not rows and not heads:
        return ""
    parts: list[str] = [
        "<div id='homeclaw-ast-digest' class='homeclaw-ast-digest' style='margin:12px;padding:18px 20px;"
        "background:linear-gradient(180deg,#fffefb 0%,#f7f2e8 100%);color:#292524;"
        "font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,PingFang SC,Microsoft YaHei,Noto Sans SC,sans-serif;"
        "border-radius:2px;border:1px solid #d6d3d1;box-shadow:0 4px 20px rgba(0,0,0,.08);max-width:1280px'>",
        "<div style='font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#78716c;margin-bottom:8px'>"
        "Magazine digest</div>",
        "<div style='font-size:12px;color:#57534e;margin-bottom:12px;line-height:1.45'>"
        "<strong>Links open in a new tab.</strong> This block mirrors story text for accessibility; "
        "the rendered magazine pages appear above this section.</div>",
    ]
    parts.extend(heads)
    if rows:

        def _row_is_table_header(cells: list[str]) -> bool:
            if not cells or str(cells[0]).strip() != "#":
                return False
            blob = " ".join(str(x) for x in cells).lower()
            return (
                "headline" in blob
                or "title" in blob
                or "link" in blob
                or "snippet" in blob
                or "url" in blob
            )

        use_cards = False
        if len(rows) >= 2 and _row_is_table_header(rows[0]):
            cmap = _digest_news_table_column_map(rows[0])
            if cmap is not None:
                card_html = _digest_render_news_cards(cmap, rows[1:], max_cell)
                if card_html:
                    parts.append(card_html)
                    use_cards = True
        if not use_cards:
            parts.append(
                "<div role='list' aria-label='Story excerpts' style='margin-top:8px;border-top:2px solid #1c1917;"
                "display:flex;flex-direction:column;gap:0;font-size:13px'>"
            )
            for i, r in enumerate(rows):
                is_hdr = i == 0 and _row_is_table_header(r)
                bg = "#fafaf9" if is_hdr else ("#ffffff" if i % 2 == 1 else "#faf8f5")
                fw = "font-weight:600;letter-spacing:.04em;text-transform:uppercase;font-size:10px;" if is_hdr else ""
                parts.append(
                    f"<div role='listitem' style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));"
                    f"gap:10px 14px;padding:12px 10px;border-bottom:1px solid #e7e5e4;background:{bg};{fw}'>"
                )
                for cell in r:
                    inner = _digest_cell_inner_html(str(cell), max_cell)
                    parts.append(
                        "<div style='min-width:0;line-height:1.45;text-align:left;border-left:3px solid #e7e5e4;"
                        "padding-left:10px;margin:0'>"
                        f"{inner}</div>"
                    )
                parts.append("</div>")
            parts.append("</div>")
    parts.append("</div>")
    out = "".join(parts)
    return out if len(out) <= max_total else (out[: max_total - 40] + "…</div>")


def _build_browser_preview_html(layout_json_text: str, digest_html: str = "") -> str:
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
        f"{digest_html or ''}"
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


def _magazine_layout_embed_max_chars() -> int:
    try:
        v = os.environ.get("HOMECLAW_VMPRINT_EMBED_LAYOUT_MAX_CHARS")
        if v is not None and str(v).strip() != "":
            return max(0, int(v))
    except Exception:
        pass
    return 600_000


def _magazine_layout_sidecar_path(preview_html: Path) -> Path:
    name = preview_html.name
    if name.lower().endswith(".preview.html"):
        return preview_html.with_name(name[: -len(".preview.html")] + ".layout.json")
    return preview_html.with_suffix(".layout.json")


def _build_hybrid_runtime_preview_html(
    ast_json_text: str,
    fallback_svg_pages: list,
    layout_json_text: Optional[str] = None,
    digest_html: str = "",
    extra_body_script_rels: Optional[Sequence[str]] = None,
) -> str:
    ast_esc = html.escape(ast_json_text or "{}")
    svg_esc = html.escape(json.dumps(fallback_svg_pages or [], ensure_ascii=False))
    ast_chars = len(ast_json_text or "")
    page_count = len(fallback_svg_pages or [])
    max_ast, max_pages = _vmprint_inline_limits()
    ui_hint = "inline" if (ast_chars <= max_ast and page_count <= max_pages) else "link"
    embed = ""
    lim = _magazine_layout_embed_max_chars()
    if layout_json_text and (lim <= 0 or len(layout_json_text) <= lim):
        embed = f"<script id='layout-data' type='application/json'>{html.escape(layout_json_text)}</script>"
    head_ld, body_ld = vmprint_hybrid_preview_loaders(
        _VMPRINT_ASSET_VERSION, extra_body_script_rels=tuple(extra_body_script_rels or ())
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta name='homeclaw-vmprint-ui-hint' content='{ui_hint}'>"
        f"<meta name='homeclaw-vmprint-ast-chars' content='{ast_chars}'>"
        f"<meta name='homeclaw-vmprint-pages' content='{page_count}'>"
        f"<title>VMPrint Browser Preview</title>{head_ld}</head><body>"
        "<div id='root' class='pages'></div>"
        f"{digest_html or ''}"
        f"<script id='ast-data' type='application/json'>{ast_esc}</script>"
        f"{embed}"
        f"<script id='svg-pages-data' type='application/json'>{svg_esc}</script>"
        f"{body_ld}"
        "</body></html>"
    )


def _render_ast_with_vmprint(
    ast_doc: Dict[str, Any],
    out_abs: Path,
    output_format: str,
    also_layout_json: bool = False,
    script_document_yaml: Optional[str] = None,
) -> Tuple[bool, str]:
    root = _repo_root()
    vmprint_dir = _vmprint_root_for_ast(root)
    if vmprint_dir is None:
        return (False, _vmprint_ast_cli_missing_message(root))
    _ensure_vmprint_static_assets(out_abs.parent, root, vmroot=vmprint_dir)
    vm_cli = _vmprint_cli_marker_path(vmprint_dir)
    out_abs.parent.mkdir(parents=True, exist_ok=True)
    ast_tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    ast_tf.close()
    ast_path = ast_tf.name
    try:
        _write_ast_input_file(Path(ast_path), ast_doc, script_document_yaml)
    except Exception as e:
        try:
            Path(ast_path).unlink(missing_ok=True)
        except Exception:
            pass
        return (False, f"Failed to write AST input: {e!s}")
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
        layout_raw = Path(layout_path).read_text(encoding="utf-8", errors="replace")
        if output_format == "layout_json":
            out_abs.write_text(layout_raw, encoding="utf-8")
            return (True, "ok")
        if output_format == "browser_preview_html":
            std_entry = _vmprint_preview_standard_fonts_cjs(vmprint_dir)
            ctx_entry = _vmprint_preview_context_canvas_js(vmprint_dir)
            dep_msg = _vmprint_preview_node_deps_missing_message(vmprint_dir)
            # Upstream monorepo does not always install @vmprint/context-canvas; resolve absolute paths for require().
            canvas_script = (
                "const fs=require('fs');"
                "const stdPath=process.argv[1];"
                "const canvasPath=process.argv[2];"
                "const astInput=process.argv[3];"
                "const {LayoutEngine,ContextRenderer,toLayoutConfig,createPrintEngineRuntime}=require('./engine/dist/index.js');"
                "const {StandardFontManager}=require(stdPath);"
                "const {CanvasContext}=require(canvasPath);"
                "const raw=fs.readFileSync(astInput,'utf8');"
                "let doc;"
                "if(String(raw||'').trimStart().startsWith('---')){const parts=String(raw).split(/\\n---\\n/);doc=JSON.parse(parts[parts.length-1]);}"
                "else{doc=JSON.parse(raw);}"
                "function _resolvePageSize(raw, orientation){"
                "const named={LETTER:{width:612,height:792},A4:{width:595,height:842}};"
                "let s=null;"
                "if(raw&&typeof raw==='object'&&Number(raw.width)>0&&Number(raw.height)>0){s={width:Number(raw.width),height:Number(raw.height)};}"
                "else if(typeof raw==='string'){const k=String(raw||'').toUpperCase().trim(); if(named[k]) s={...named[k]};}"
                "if(!s){s={width:612,height:792};}"
                "const o=String(orientation||'').toLowerCase();"
                "if(o==='landscape'&&s.width<s.height){s={width:s.height,height:s.width};}"
                "if(o==='portrait'&&s.width>s.height){s={width:s.height,height:s.width};}"
                "return s;}"
                "(async()=>{"
                "const runtime=createPrintEngineRuntime({fontManager:new StandardFontManager()});"
                "const cfg=toLayoutConfig(doc);"
                "const rawPageSize=(cfg&&cfg.pageSize)?cfg.pageSize:((doc&&doc.layout)?doc.layout.pageSize:null);"
                "const orientation=(cfg&&cfg.orientation)?cfg.orientation:((doc&&doc.layout)?doc.layout.orientation:null);"
                "const pageSize=_resolvePageSize(rawPageSize, orientation);"
                "const engine=new LayoutEngine(cfg,runtime);"
                "await engine.waitForFonts();"
                "const pages=engine.simulate(doc.elements);"
                "const ctx=new CanvasContext({size:pageSize,margins:cfg.margins,autoFirstPage:false,bufferPages:false,textRenderMode:'text'});"
                "const renderer=new ContextRenderer(cfg,false,runtime);"
                "await renderer.render(pages,ctx); ctx.end();"
                "process.stdout.write(JSON.stringify({svgs:ctx.toSvgPages()}));"
                "})().catch(e=>{console.error(String(e&&e.stack||e)); process.exit(2);});"
            )
            canvas_err = ""
            svgs: list = []
            if std_entry is None or ctx_entry is None:
                canvas_err = dep_msg or "Missing @vmprint/context-canvas or @vmprint/standard-fonts for SVG preview."
            else:
                c = subprocess.run(
                    ["node", "-e", canvas_script, str(std_entry), str(ctx_entry), ast_path],
                    cwd=str(vmprint_dir),
                    capture_output=True,
                    timeout=180,
                    check=False,
                )
                if c.returncode != 0:
                    canvas_err = (c.stderr or c.stdout or b"").decode("utf-8", errors="replace").strip()
                if c.returncode == 0:
                    try:
                        payload = json.loads((c.stdout or b"{}").decode("utf-8", errors="replace"))
                        raw_svgs = payload.get("svgs") if isinstance(payload, dict) else None
                        if isinstance(raw_svgs, list) and raw_svgs:
                            svgs = raw_svgs
                        else:
                            canvas_err = canvas_err or "no pages rendered"
                    except Exception as e:
                        canvas_err = str(e)
            digest = _ast_digest_html(ast_doc)
            if canvas_err or not svgs:
                # Layout emit already succeeded; canvas/SVG often fails on large CJK tables or font edge cases.
                err_short = (canvas_err or "unknown")[:500]
                html_fb = _build_browser_preview_html(layout_raw, digest_html=digest)
                banner = (
                    "<div style='background:#422;color:#fec;padding:10px 12px;font:13px system-ui;border-bottom:1px solid #000'>"
                    "<b>Layout preview (fallback)</b> — Canvas SVG render did not complete; showing VMPrint layout boxes instead. "
                    f"<span style='opacity:.9'>{html.escape(err_short)}</span></div>"
                )
                html_fb = html_fb.replace("<body>", "<body>" + banner, 1)
                out_abs.write_text(html_fb, encoding="utf-8")
                if also_layout_json:
                    side = _magazine_layout_sidecar_path(out_abs)
                    try:
                        side.write_text(layout_raw, encoding="utf-8")
                    except Exception:
                        pass
                return (True, "ok")
            html_out = _build_hybrid_runtime_preview_html(
                json.dumps(ast_doc, ensure_ascii=False),
                svgs,
                layout_json_text=layout_raw,
                digest_html=digest,
            )
            out_abs.write_text(html_out, encoding="utf-8")
            if also_layout_json:
                side = _magazine_layout_sidecar_path(out_abs)
                try:
                    side.write_text(layout_raw, encoding="utf-8")
                except Exception:
                    pass
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


def _template_web_search(data: Dict[str, Any], title: str) -> str:
    items = data.get("results") or data.get("items") or []
    if not isinstance(items, list):
        items = []
    query = str(data.get("query") or data.get("q") or "").strip()
    as_of = str(data.get("as_of") or data.get("generated_at") or "").strip() or _now_local_str()
    lines = [f"# {title}", ""]
    if query:
        lines.append(f"**Query:** {query}")
    lines.append(f"**As of:** {as_of}")
    lines.append("")
    lines.append("| # | Title | Snippet | URL |")
    lines.append("|---:|---|---|---|")
    for i, it in enumerate(items[:25], start=1):
        if not isinstance(it, dict):
            continue
        h = str(it.get("title") or it.get("headline") or "").strip()
        url = str(it.get("url") or it.get("link") or "").strip()
        snip = str(it.get("content") or it.get("snippet") or it.get("summary") or "").strip()
        if len(snip) > 160:
            snip = snip[:157] + "..."
        lines.append(
            f"| {i} | {_md_link(h or 'Result', url)} | {_md_escape_inline(snip)} | {_md_escape_inline(url)} |"
        )
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_json_to_markdown(template: str, data: Dict[str, Any], title: Optional[str]) -> str:
    t = (template or "").strip().lower()
    if not title:
        title = {
            "daily_brief": "Daily Brief",
            "weather": "Weather",
            "stock": "Stocks",
            "web_search": "Search digest",
        }.get(t, "Report")
    if t == "daily_brief":
        return _template_daily_brief(data, title)
    if t == "weather":
        return _template_weather(data, title)
    if t == "stock":
        return _template_stock(data, title)
    if t == "web_search":
        return _template_web_search(data, title)
    raise ValueError("template must be one of: daily_brief, weather, stock, web_search")


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
    p_js.add_argument(
        "--template",
        required=True,
        choices=["daily_brief", "weather", "stock", "web_search"],
        help="Template name.",
    )
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
    p_ast.add_argument(
        "--also-layout-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="With browser_preview_html, write sibling .layout.json next to the preview (default: on).",
    )

    p_dba = sub.add_parser("render-daily-brief-ast", help="Compile daily-brief JSON -> VMPrint AST -> artifact.")
    p_dba.add_argument("--title", default="Daily Brief", help="Document title.")
    p_dba.add_argument("--json", default="", help="Daily-brief JSON text (inline).")
    p_dba.add_argument("--input", default="", help="Path to daily-brief JSON file.")
    p_dba.add_argument("--theme", default="dispatch", choices=["dispatch", "minimal"])
    p_dba.add_argument("--output_format", default="pdf", choices=["pdf", "layout_json", "browser_preview_html"])
    p_dba.add_argument("--out", required=True, help="Output filename under output/ (pdf/json/html depending on output_format).")
    p_dba.add_argument(
        "--also-layout-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="With browser_preview_html, write sibling .layout.json next to the preview (default: on).",
    )
    p_dba.add_argument(
        "--document-layout",
        default="digest_table",
        choices=["digest_table", "magazine", "newspaper"],
        help="digest_table: headline table (default). magazine: lead+rail. newspaper: masthead + multi-column + index (daily brief only).",
    )
    p_dba.add_argument(
        "--chrome-template",
        default="",
        help="Optional path to static chrome JSON (layout/styles/header/footer/meta) merged after building AST; see ast_templates/README.md.",
    )

    p_ta = sub.add_parser("render-template-ast", help="Compile template JSON -> VMPrint AST -> artifact.")
    p_ta.add_argument("--template", required=True, choices=["daily_brief", "weather", "stock", "web_search"])
    p_ta.add_argument("--title", default="Report", help="Document title.")
    p_ta.add_argument("--json", default="", help="Template JSON text (inline).")
    p_ta.add_argument("--input", default="", help="Path to template JSON file.")
    p_ta.add_argument("--theme", default="dispatch", choices=["dispatch", "minimal"])
    p_ta.add_argument("--output_format", default="browser_preview_html", choices=["pdf", "layout_json", "browser_preview_html"])
    p_ta.add_argument("--out", required=True, help="Output filename under output/ (pdf/json/html depending on output_format).")
    p_ta.add_argument(
        "--also-layout-json",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="With browser_preview_html, write sibling .layout.json next to the preview (default: on).",
    )
    p_ta.add_argument(
        "--scripted-colophon",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="With --template web_search only: emit VMPrint YAML scripting + named colophon (settled page count).",
    )
    p_ta.add_argument(
        "--document-layout",
        default="digest_table",
        choices=["digest_table", "magazine", "newspaper"],
        help="digest_table: template default. magazine: portrait lead+rail. newspaper: daily_brief only (front-page style).",
    )

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
            ok, err = _render_ast_with_vmprint(
                ast_doc,
                out_abs,
                str(args.output_format),
                also_layout_json=bool(getattr(args, "also_layout_json", True)),
            )
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
            dlayout = str(getattr(args, "document_layout", "digest_table") or "digest_table").strip().lower()
            if dlayout == "magazine":
                ast_doc = _daily_brief_magazine_ast(
                    data, title=str(args.title or "Daily Brief"), theme=str(args.theme or "dispatch")
                )
            elif dlayout == "newspaper":
                ast_doc = _daily_brief_newspaper_ast(
                    data, title=str(args.title or "Daily Brief"), theme=str(args.theme or "dispatch")
                )
            else:
                ast_doc = _daily_brief_ast(data, title=str(args.title or "Daily Brief"), theme=str(args.theme or "dispatch"))
            _ctp = str(getattr(args, "chrome_template", "") or "").strip()
            if _ctp:
                from ast_template_merge import load_chrome_template, merge_chrome_template_into_ast

                _chrome = load_chrome_template(Path(_ctp))
                ast_doc = merge_chrome_template_into_ast(ast_doc, _chrome)
            _validate_ast_1_1(ast_doc)
            ok, err = _render_ast_with_vmprint(
                ast_doc,
                out_abs,
                str(args.output_format),
                also_layout_json=bool(getattr(args, "also_layout_json", True)),
            )
            if not ok:
                _fail(err)
            _ok(out_rel, f"VMPrint daily-brief AST artifact saved ({dlayout}): {out_rel}")
            return

        if args.cmd == "render-template-ast":
            json_text = (args.json or "").strip()
            if not json_text and args.input:
                json_text = Path(str(args.input)).read_text(encoding="utf-8", errors="replace")
            json_text = _ensure_text_arg(json_text, max_chars=350_000, name="JSON")
            data = _json_loads_strict(json_text)
            _tpl = str(args.template or "").strip().lower()
            _dlayout = str(getattr(args, "document_layout", "digest_table") or "digest_table").strip().lower()
            _sc = bool(getattr(args, "scripted_colophon", False))
            if _sc and _tpl != "web_search":
                _fail("--scripted-colophon is only supported with --template web_search")
            if _sc and _tpl == "web_search" and _dlayout == "magazine":
                _fail("--scripted-colophon is not supported with --document-layout magazine")
            ast_doc = _ast_from_template(
                str(args.template or ""),
                data,
                title=str(args.title or "Report"),
                theme=str(args.theme or "dispatch"),
                scripted_colophon=_sc,
                document_layout=_dlayout,
            )
            _validate_ast_1_1(ast_doc)
            _sy = (
                _WEB_SEARCH_COLOPHON_SCRIPT_YAML if (_sc and _tpl == "web_search" and _dlayout != "magazine") else None
            )
            ok, err = _render_ast_with_vmprint(
                ast_doc,
                out_abs,
                str(args.output_format),
                also_layout_json=bool(getattr(args, "also_layout_json", True)),
                script_document_yaml=_sy,
            )
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

