#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "python-pptx>=0.6.21",
# ]
# ///
"""
Create PowerPoint (.pptx) from outline, source, structured slides, or documents.
Run via: run_skill(skill_name='ppt-generation-1.0.0', script='create_pptx.py', args=[...]).
When HOMECLAW_OUTPUT_DIR is set (by Core), saves there and prints JSON with output_rel_path so Core can append the open link.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
except ImportError:
    print('{"success": false, "error": "python-pptx not installed. Install with: pip install python-pptx"}', flush=True)
    sys.exit(1)

LAYOUT_TITLE = 0
LAYOUT_TITLE_BODY = 1


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _output_dir() -> Path:
    out = os.environ.get("HOMECLAW_OUTPUT_DIR", "").strip()
    if out:
        return Path(out)
    root = _skill_root()
    # Default when not run via Core: project/config/workspace/presentations or skill/output
    project = root.parent.parent
    ws = project / "config" / "workspace" / "presentations"
    if ws.parent.is_dir():
        return ws
    return root / "output"


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\s\-\.]", "", name)
    name = name.strip()[:80] or "presentation"
    return name + ".pptx" if not name.lower().endswith(".pptx") else name


def _add_bullets(shape, bullets: List[str], level: int = 0) -> None:
    tf = shape.text_frame
    tf.clear()
    for i, line in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.level = level
        p.space_after = Pt(6)


def _build_pptx(main_title: str, subtitle: str, slides_list: List[Dict[str, Any]], out_path: Path) -> None:
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[LAYOUT_TITLE])
    slide.shapes.title.text = main_title or "Presentation"
    if subtitle and hasattr(slide, "placeholders") and len(slide.placeholders) > 1:
        slide.placeholders[1].text = subtitle
    for item in slides_list:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip() or "Slide"
        bullets = item.get("bullets")
        if not isinstance(bullets, list):
            bullets = [str(bullets)] if bullets else []
        bullets = [str(b).strip() for b in bullets if b]
        slide = prs.slides.add_slide(prs.slide_layouts[LAYOUT_TITLE_BODY])
        slide.shapes.title.text = title
        if bullets and hasattr(slide, "placeholders") and len(slide.placeholders) > 1:
            _add_bullets(slide.placeholders[1], bullets)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))


def _parse_outline(outline: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    main_title = ""
    subtitle = ""
    slides_list: List[Dict[str, Any]] = []
    current_title = None
    current_bullets: List[str] = []

    def flush_slide():
        nonlocal current_title, current_bullets
        if current_title is not None:
            slides_list.append({"title": current_title, "bullets": list(current_bullets)})
        current_title = None
        current_bullets = []

    lines = (outline or "").strip().split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            flush_slide()
            current_title = stripped[2:].strip() or "Slide"
            current_bullets = []
        elif stripped.startswith("-") or stripped.startswith("*"):
            bullet = stripped[1:].strip()
            if current_title is not None:
                current_bullets.append(bullet)
            else:
                if not main_title:
                    main_title = bullet
                elif not subtitle:
                    subtitle = bullet
                else:
                    if not current_title:
                        current_title = "Content"
                    current_bullets.append(bullet)
        elif stripped:
            if current_title is not None:
                current_bullets.append(stripped)
            else:
                if not main_title:
                    main_title = stripped
                elif not subtitle:
                    subtitle = stripped
                else:
                    current_title = "Content"
                    current_bullets.append(stripped)
    flush_slide()
    if not main_title and slides_list:
        main_title = slides_list[0].get("title") or "Presentation"
    return main_title, subtitle, slides_list


def _parse_document_to_slides(content: str, doc_title: str = "") -> List[Dict[str, Any]]:
    if not (content or "").strip():
        return [{"title": doc_title or "Document", "bullets": ["(No content)"]}]
    text = (content or "").strip()
    slides: List[Dict[str, Any]] = []
    if "##" in text or text.startswith("#"):
        main_title, subtitle, slides_list = _parse_outline(text)
        if slides_list:
            for s in slides_list:
                slides.append(s)
        elif main_title:
            slides.append({"title": main_title, "bullets": [subtitle] if subtitle else []})
    else:
        blocks = re.split(r"\n\s*\n", text)
        max_bullets_per_slide = 12
        max_bullet_len = 400
        for i, block in enumerate(blocks):
            block = block.strip()
            if not block:
                continue
            lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
            if not lines:
                continue
            title = lines[0][:120]
            bullets = []
            for ln in lines[1:]:
                bullets.append(ln[:max_bullet_len] if len(ln) > max_bullet_len else ln)
            if not bullets and len(lines) == 1 and len(lines[0]) > 80:
                first = lines[0]
                for part in re.split(r"(?<=[.!?])\s+", first)[:max_bullets_per_slide]:
                    if part.strip():
                        bullets.append(part.strip()[:max_bullet_len])
            if len(bullets) > max_bullets_per_slide:
                slides.append({"title": title, "bullets": bullets[:max_bullets_per_slide]})
                for j in range(max_bullets_per_slide, len(bullets), max_bullets_per_slide):
                    chunk = bullets[j : j + max_bullets_per_slide]
                    slides.append({"title": f"{title} (continued)", "bullets": chunk})
            else:
                slides.append({"title": title, "bullets": bullets or [title]})
    if not slides and doc_title:
        slides.append({"title": doc_title, "bullets": [text[:500]]})
    return slides


def _resolve_document_path(path_str: str, base_dirs: List[Path]) -> Optional[Path]:
    path_str = (path_str or "").strip()
    if not path_str:
        return None
    p = Path(path_str)
    bases = [b.resolve() for b in base_dirs if b.is_dir()]
    if p.is_absolute():
        resolved = p.resolve()
        for base in bases:
            try:
                resolved.relative_to(base)
                if resolved.is_file():
                    return resolved
            except ValueError:
                continue
        return None
    for base in bases:
        candidate = (base / p).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None


def _read_arg_or_file(value: Optional[str], path_value: Optional[str]) -> str:
    """Return inline value or file content. File path must be under skill root or project (no path escape)."""
    if value is not None and value.strip():
        return value.strip()
    if not path_value or not path_value.strip():
        return ""
    p = Path(path_value.strip())
    try:
        if not p.is_file():
            return ""
        root = _skill_root()
        project = root.parent.parent
        resolved = p.resolve()
        for base in (root, project):
            try:
                if base.exists() and resolved.relative_to(base.resolve()):
                    return resolved.read_text(encoding="utf-8", errors="replace")
            except ValueError:
                continue
    except (OSError, RuntimeError):
        pass
    return ""


def run_outline(args: argparse.Namespace) -> Dict[str, Any]:
    outline = _read_arg_or_file(getattr(args, "outline", None), getattr(args, "outline_file", None))
    if not outline:
        return {"success": False, "error": "outline is required (--outline or --outline-file)."}
    main_title, subtitle, slides_list = _parse_outline(outline)
    if not slides_list and not main_title:
        return {"success": False, "error": "Could not parse any slides from the outline."}
    out_dir = _output_dir()
    out_filename = (getattr(args, "output_filename", None) or "").strip()
    if not out_filename:
        out_filename = _safe_filename(main_title) or f"outline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
    elif not out_filename.lower().endswith(".pptx"):
        out_filename += ".pptx"
    out_path = out_dir / out_filename
    _build_pptx(main_title, subtitle, slides_list, out_path)
    payload = {"success": True, "path": str(out_path.resolve()), "message": f"Presentation saved to {out_path.resolve()}"}
    if os.environ.get("HOMECLAW_OUTPUT_DIR"):
        payload["output_rel_path"] = f"output/{out_filename}"
    return payload


def run_source(args: argparse.Namespace) -> Dict[str, Any]:
    source = _read_arg_or_file(getattr(args, "source", None), getattr(args, "source_file", None))
    if not source:
        return {"success": False, "error": "source is required (--source or --source-file)."}
    main_title = ""
    subtitle = ""
    all_slides: List[Dict[str, Any]] = []
    stripped = source.strip()
    if stripped.startswith("["):
        try:
            content_list = json.loads(source)
        except json.JSONDecodeError:
            content_list = None
    elif stripped.startswith("{"):
        try:
            obj = json.loads(source)
            content_list = obj.get("results") or obj.get("documents") or (obj.get("items") if isinstance(obj.get("items"), list) else None)
        except json.JSONDecodeError:
            content_list = None
    else:
        content_list = None
    if isinstance(content_list, list) and content_list:
        for i, item in enumerate(content_list):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or item.get("query") or f"Source {i+1}").strip() or f"Source {i+1}"
            content = str(item.get("content") or item.get("body") or item.get("snippet") or "").strip()
            if not content and isinstance(item.get("results"), list):
                for r in item.get("results", [])[:5]:
                    if isinstance(r, dict):
                        content += str(r.get("content") or r.get("body") or r.get("snippet") or r.get("title") or "") + "\n"
            slides = _parse_document_to_slides(content, title)
            if not main_title and slides:
                main_title = title or (slides[0].get("title") if slides else "")
            all_slides.extend(slides)
        if all_slides and not main_title:
            main_title = all_slides[0].get("title", "Presentation") if all_slides else "Presentation"
    if not all_slides:
        main_title, subtitle, slides_list = _parse_outline(source)
        if slides_list:
            all_slides = slides_list
        elif main_title:
            all_slides = [{"title": main_title, "bullets": [subtitle] if subtitle else []}]
    if not all_slides:
        return {"success": False, "error": "Could not extract any slides from the source."}
    if not main_title:
        main_title = str((all_slides[0] or {}).get("title") or "Presentation") if all_slides else "Presentation"
    main_title = (main_title or "Presentation").strip() or "Presentation"
    out_dir = _output_dir()
    out_filename = (getattr(args, "output_filename", None) or "").strip()
    if not out_filename:
        out_filename = _safe_filename(main_title) or f"source_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
    elif not out_filename.lower().endswith(".pptx"):
        out_filename += ".pptx"
    out_path = out_dir / out_filename
    _build_pptx(main_title, subtitle or "", all_slides, out_path)
    payload = {"success": True, "path": str(out_path.resolve()), "message": f"Presentation saved to {out_path.resolve()}"}
    if os.environ.get("HOMECLAW_OUTPUT_DIR"):
        payload["output_rel_path"] = f"output/{out_filename}"
    return payload


def run_presentation(args: argparse.Namespace) -> Dict[str, Any]:
    main_title = (getattr(args, "main_title", None) or "").strip() or "Presentation"
    subtitle = (getattr(args, "subtitle", None) or "").strip()
    slides_raw = getattr(args, "slides", None)
    if not slides_raw:
        return {"success": False, "error": "slides is required (JSON array of {title, bullets})."}
    if isinstance(slides_raw, str):
        try:
            slides_list = json.loads(slides_raw)
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON in slides."}
    else:
        slides_list = slides_raw
    if not isinstance(slides_list, list):
        return {"success": False, "error": "slides must be an array."}
    slides_list = [x for x in slides_list if isinstance(x, dict)]
    if not slides_list:
        return {"success": False, "error": "slides must be an array of objects with title and bullets."}
    out_dir = _output_dir()
    out_filename = (getattr(args, "output_filename", None) or "").strip()
    if not out_filename:
        out_filename = _safe_filename(main_title) or f"presentation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
    elif not out_filename.lower().endswith(".pptx"):
        out_filename += ".pptx"
    out_path = out_dir / out_filename
    _build_pptx(main_title, subtitle, slides_list, out_path)
    payload = {"success": True, "path": str(out_path.resolve()), "message": f"Presentation saved to {out_path.resolve()}"}
    if os.environ.get("HOMECLAW_OUTPUT_DIR"):
        payload["output_rel_path"] = f"output/{out_filename}"
    return payload


def run_documents(args: argparse.Namespace) -> Dict[str, Any]:
    paths_raw = getattr(args, "document_paths", None)
    contents_raw = getattr(args, "document_contents", None)
    if not paths_raw and not contents_raw:
        return {"success": False, "error": "Provide at least one of --document_paths or --document_contents."}
    main_title = (getattr(args, "main_title", None) or "").strip()
    all_slides: List[Dict[str, Any]] = []
    sources: List[str] = []
    root = _skill_root()
    project = root.parent.parent
    base_dirs = [project, project / "config" / "workspace"]

    if paths_raw:
        if isinstance(paths_raw, str):
            try:
                path_list = json.loads(paths_raw)
            except json.JSONDecodeError:
                return {"success": False, "error": "document_paths must be a JSON array of strings."}
        else:
            path_list = paths_raw if isinstance(paths_raw, list) else []
        if not isinstance(path_list, list):
            return {"success": False, "error": "document_paths must be an array."}
        for path_str in path_list:
            if not isinstance(path_str, str):
                continue
            resolved = _resolve_document_path(path_str, base_dirs)
            if not resolved:
                return {"success": False, "error": f"File not found or not allowed: {path_str}"}
            try:
                content = resolved.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return {"success": False, "error": f"Could not read {path_str}: {e}"}
            doc_title = resolved.stem
            slides = _parse_document_to_slides(content, doc_title)
            if not main_title and slides:
                main_title = doc_title or slides[0].get("title", "Document")
            all_slides.extend(slides)
            sources.append(resolved.name)

    if contents_raw:
        if isinstance(contents_raw, str):
            try:
                content_list = json.loads(contents_raw)
            except json.JSONDecodeError:
                return {"success": False, "error": "document_contents must be a JSON array of {title, content}."}
        else:
            content_list = contents_raw if isinstance(contents_raw, list) else []
        if not isinstance(content_list, list):
            return {"success": False, "error": "document_contents must be an array."}
        for i, item in enumerate(content_list):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("name") or f"Document {i+1}").strip()
            content = (item.get("content") or "").strip()
            slides = _parse_document_to_slides(content, title)
            if not main_title and slides:
                main_title = title
            all_slides.extend(slides)
            sources.append(title)

    if not all_slides:
        return {"success": False, "error": "No slides could be parsed from the document(s)."}
    if not main_title:
        main_title = all_slides[0].get("title", "Presentation") if all_slides else "Presentation"
    out_dir = _output_dir()
    out_filename = (getattr(args, "output_filename", None) or "").strip()
    if not out_filename:
        out_filename = _safe_filename(main_title) or f"documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pptx"
    elif not out_filename.lower().endswith(".pptx"):
        out_filename += ".pptx"
    out_path = out_dir / out_filename
    _build_pptx(main_title, "", all_slides, out_path)
    payload = {
        "success": True,
        "path": str(out_path.resolve()),
        "message": f"Presentation created from {len(sources)} document(s) and saved to {out_path.resolve()}",
        "sources": sources,
    }
    if os.environ.get("HOMECLAW_OUTPUT_DIR"):
        payload["output_rel_path"] = f"output/{out_filename}"
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="Create .pptx from outline, source, slides, or documents.")
    ap.add_argument("--capability", required=True, choices=["outline", "source", "presentation", "documents"], help="Which mode to run")
    ap.add_argument("--outline", default="", help="Markdown outline (## titles, - bullets)")
    ap.add_argument("--outline-file", default="", help="Path to file containing outline")
    ap.add_argument("--source", default="", help="Plain text or JSON array of {title, content}")
    ap.add_argument("--source-file", default="", help="Path to file containing source")
    ap.add_argument("--main_title", default="", help="Title slide title")
    ap.add_argument("--subtitle", default="", help="Title slide subtitle")
    ap.add_argument("--slides", default="", help='JSON array of {"title", "bullets"}')
    ap.add_argument("--document_paths", default="", help='JSON array of file paths')
    ap.add_argument("--document_contents", default="", help='JSON array of {"title", "content"}')
    ap.add_argument("--output_filename", default="", help="Output .pptx filename")
    ap.add_argument("--language", default="en", help="en or zh (reserved)")
    args = ap.parse_args()

    try:
        if args.capability == "outline":
            payload = run_outline(args)
        elif args.capability == "source":
            payload = run_source(args)
        elif args.capability == "presentation":
            payload = run_presentation(args)
        else:
            payload = run_documents(args)
    except (OSError, IOError, ValueError, TypeError, KeyError) as e:
        payload = {"success": False, "error": str(e)}
    except Exception as e:
        payload = {"success": False, "error": f"Unexpected error: {e}"}
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    if not payload.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
