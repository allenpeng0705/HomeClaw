#!/usr/bin/env python3
"""
Convert an OpenClaw skill folder into HomeClaw skill layout (SKILL.md + scripts/ + references/).

Use this to reuse OpenClaw skills in HomeClaw. Supports Python (.py), JavaScript (.js, .mjs, .cjs),
TypeScript (.ts), and shell (.sh). Output goes to external_skills/ by default so you can try
converted skills there; when stable, move the folder to skills/.

Usage:
  # Convert to external_skills/<source_folder_name>/ (default):
  python scripts/convert_openclaw_skill.py /path/to/openclaw-skill-folder

  # Custom output (e.g. skills/ or another path under project root):
  python scripts/convert_openclaw_skill.py /path/to/skill --output external_skills/my-skill-1.0.0

  # Dry run (print what would be done, no files written):
  python scripts/convert_openclaw_skill.py /path/to/skill --dry-run

OpenClaw layout:
  - SKILL.md (required) — copied and optionally merged with skill.yaml name/description/version.
  - skill.yaml (optional) — manifest; we merge name, description, version. If entryPoint.path
    points to a file (e.g. dist/index.js, src/index.ts), we copy it into scripts/.
  - scripts/ — we copy .py, .pyw, .js, .mjs, .cjs, .ts, .sh, .bash.
  - references/ — copied as-is.

See docs_design/OpenClawSkillsInvestigationAndConverter.md.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional

# HomeClaw run_skill supports these; .ts runs via tsx or ts-node when in PATH
RUNNABLE_EXTENSIONS = (".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".sh", ".bash")


def _project_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root


def _find_skill_md(dir_path: Path) -> Optional[Path]:
    if not dir_path or not dir_path.is_dir():
        return None
    skill_md = dir_path / "SKILL.md"
    return skill_md if skill_md.is_file() else None


def _read_yaml_safe(path: Path) -> dict:
    if not path or not path.is_file():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_str(value: object, max_len: int = 2000) -> str:
    """Coerce to str for frontmatter; truncate if very long."""
    if value is None:
        return ""
    s = str(value).strip()
    if max_len > 0 and len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def _merge_skill_yaml_into_content(content: str, yaml_data: dict) -> str:
    """Merge skill.yaml name/description/version into SKILL.md frontmatter. Returns new content."""
    name = _safe_str(yaml_data.get("name"), 200)
    desc = _safe_str(yaml_data.get("description"), 500)
    version = _safe_str(yaml_data.get("version"), 50)
    if not name and not desc and not version:
        return content
    # Normalize description for YAML: single line for frontmatter
    if desc and "\n" in desc:
        desc = desc.replace("\n", " ").strip()
    if "---" in content:
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm, body = parts[1].strip(), parts[2].strip()
            if name and "name:" not in fm:
                fm = fm + "\nname: " + name
            if desc and "description:" not in fm:
                fm = fm + "\ndescription: " + desc
            if version and "version:" not in fm:
                fm = fm + "\nversion: " + version
            return "---\n" + fm + "\n---\n" + body
    return f"---\nname: {name}\ndescription: {desc}\nversion: {version}\n---\n\n" + content


def _copy_scripts_dir(src_scripts: Path, dst_scripts: Path, dry_run: bool) -> List[str]:
    """Copy runnable script files from src_scripts to dst_scripts. Returns list of copied filenames."""
    copied: List[str] = []
    if not src_scripts.is_dir():
        return copied
    try:
        if not dry_run:
            dst_scripts.mkdir(parents=True, exist_ok=True)
        dst_resolved = dst_scripts.resolve()
        for f in src_scripts.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in RUNNABLE_EXTENSIONS:
                continue
            name = f.name
            if ".." in name or name.startswith("."):
                continue
            copied.append(name)
            if not dry_run:
                try:
                    dst_file = (dst_scripts / name).resolve()
                    if dst_resolved not in dst_file.parents and dst_file != dst_resolved:
                        continue
                    shutil.copy2(f, dst_file)
                except OSError:
                    pass
    except Exception:
        pass
    return copied


def _copy_entrypoint_script(source_root: Path, output_dir: Path, entry_path: str, dry_run: bool) -> Optional[str]:
    """If skill.yaml entryPoint.path points to a file, copy it to output_dir/scripts/. Return basename or None."""
    if not entry_path or not isinstance(entry_path, str):
        return None
    entry_path = entry_path.strip().replace("\\", "/")
    if not entry_path or ".." in entry_path:
        return None
    src_file = (source_root / entry_path).resolve()
    try:
        if not src_file.is_file():
            return None
        if not str(src_file).startswith(str(source_root.resolve())):
            return None
        name = src_file.name
        if name.startswith(".") or src_file.suffix.lower() not in RUNNABLE_EXTENSIONS:
            return None
        dst_scripts = output_dir / "scripts"
        if not dry_run:
            dst_scripts.mkdir(parents=True, exist_ok=True)
        dst_file = dst_scripts / name
        if not dry_run:
            shutil.copy2(src_file, dst_file)
        return name
    except Exception:
        return None


def _copy_references(src_ref: Path, output_dir: Path, dry_run: bool) -> bool:
    """Copy references/ directory. Returns True if copied."""
    if not src_ref.is_dir():
        return False
    try:
        dst_ref = output_dir / "references"
        if dry_run:
            return True
        if dst_ref.exists():
            shutil.rmtree(dst_ref)
        shutil.copytree(src_ref, dst_ref)
        return True
    except Exception:
        return False


def convert_skill(
    source: Path,
    output_dir: Path,
    dry_run: bool = False,
    merge_skill_yaml: bool = True,
) -> dict:
    """
    Convert an OpenClaw skill at source to HomeClaw layout under output_dir.
    Returns a report dict (skill_id, output, skill_md, scripts_copied, references_copied, allowlist)
    or {"error": "..."} on failure. Never raises.
    """
    try:
        source = source.resolve()
        if not source.is_dir():
            return {"error": f"Not a directory: {source}"}

        skill_md_src = _find_skill_md(source)
        if not skill_md_src:
            return {"error": f"No SKILL.md in {source}"}

        skill_id = (output_dir.name if output_dir.name else source.name).strip() or "skill"
        report: dict = {
            "skill_id": skill_id,
            "source": str(source),
            "output": str(output_dir),
            "skill_md": True,
            "scripts_copied": [],
            "references_copied": False,
            "allowlist": [],
        }

        output_dir = output_dir.resolve()
        if not dry_run:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                return {"error": f"Cannot create output directory {output_dir}: {e}"}

        # 1) SKILL.md
        try:
            content = skill_md_src.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return {"error": f"Cannot read SKILL.md: {e}"}
        if not isinstance(content, str):
            content = ""

        skill_yaml_path = source / "skill.yaml"
        if merge_skill_yaml and skill_yaml_path.is_file():
            yaml_data = _read_yaml_safe(skill_yaml_path)
            if yaml_data:
                content = _merge_skill_yaml_into_content(content, yaml_data)

        if not dry_run:
            try:
                (output_dir / "SKILL.md").write_text(content, encoding="utf-8")
            except OSError as e:
                return {"error": f"Cannot write SKILL.md: {e}"}

        # 2) scripts/
        src_scripts = source / "scripts"
        dst_scripts = output_dir / "scripts"
        report["scripts_copied"] = _copy_scripts_dir(src_scripts, dst_scripts, dry_run)

        # If skill.yaml has entryPoint.path (e.g. dist/index.js), copy that file into scripts/ too
        if merge_skill_yaml and skill_yaml_path.is_file():
            yaml_data = _read_yaml_safe(skill_yaml_path)
            entry = yaml_data.get("entryPoint") if isinstance(yaml_data, dict) else None
            if isinstance(entry, dict) and entry.get("path"):
                ep_name = _copy_entrypoint_script(source, output_dir, entry.get("path"), dry_run)
                if ep_name and ep_name not in report["scripts_copied"]:
                    report["scripts_copied"] = report["scripts_copied"] + [ep_name]

        report["allowlist"] = list(report["scripts_copied"])

        # 3) references/
        src_ref = source / "references"
        report["references_copied"] = _copy_references(src_ref, output_dir, dry_run)

        return report
    except Exception as e:
        return {"error": f"Conversion failed: {e}"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert an OpenClaw skill folder to HomeClaw layout (default: external_skills/).",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Path to OpenClaw skill folder (must contain SKILL.md)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory (default: external_skills/<source_folder_name>)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be done; do not write files",
    )
    parser.add_argument(
        "--no-merge-yaml",
        action="store_true",
        help="Do not merge skill.yaml name/description/version into SKILL.md",
    )
    args = parser.parse_args()

    root = _project_root()
    source = args.source
    try:
        source = source.resolve()
    except Exception:
        source = (Path.cwd() / args.source).resolve()
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()

    if args.output is None:
        output_dir = root / "external_skills" / source.name
    else:
        output_dir = Path(args.output)
        if not output_dir.is_absolute():
            output_dir = (root / output_dir).resolve()
        else:
            output_dir = output_dir.resolve()

    report = convert_skill(
        source,
        output_dir,
        dry_run=args.dry_run,
        merge_skill_yaml=not args.no_merge_yaml,
    )

    if "error" in report:
        print(report["error"], file=sys.stderr)
        return 1

    print("Converted skill:", report["skill_id"])
    print("  Output:", report["output"])
    print("  SKILL.md: yes")
    print("  Scripts copied:", report["scripts_copied"] or "(none)")
    print("  References:", "yes" if report["references_copied"] else "no")
    if report.get("allowlist"):
        print("\nSuggested run_skill_allowlist (config/skills_and_plugins.yml or tools section):")
        print("  run_skill_allowlist:", report["allowlist"])
    if args.dry_run:
        print("\n[Dry run] No files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
