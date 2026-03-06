#!/usr/bin/env python3
"""
Convert an OpenClaw skill folder into HomeClaw skills/ layout.

Usage:
  # From a local OpenClaw skill folder (must contain SKILL.md):
  python scripts/convert_openclaw_skill.py /path/to/openclaw-skill-folder

  # Output goes to skills/<folder_name>/ by default; override with --output:
  python scripts/convert_openclaw_skill.py /path/to/skill --output skills/my-skill-1.0.0

  # Dry run (print what would be done):
  python scripts/convert_openclaw_skill.py /path/to/skill --dry-run

OpenClaw skills typically have:
  - SKILL.md (required) — same format as HomeClaw; copied as-is or merged with skill.yaml.
  - skill.yaml (optional) — manifest with entryPoint (natural | typescript | shell); we merge name/description into SKILL.md and ensure the script path exists under scripts/.
  - scripts/ — we copy .py, .js, .mjs, .cjs, .sh only (.ts must be compiled to .js separately).
  - references/ — copied as-is.

See docs_design/OpenClawSkillsInvestigationAndConverter.md for full design.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Script extensions HomeClaw run_skill supports (.ts requires tsx or ts-node in PATH)
RUNNABLE_EXTENSIONS = (".py", ".pyw", ".js", ".mjs", ".cjs", ".ts", ".sh", ".bash")


def _project_root() -> Path:
    root = Path(__file__).resolve().parent.parent
    assert (root / "skills").is_dir() or not (root / "base").is_dir(), "Run from HomeClaw repo root"
    return root


def _find_skill_md(dir_path: Path) -> Path | None:
    skill_md = dir_path / "SKILL.md"
    return skill_md if skill_md.is_file() else None


def _read_yaml_safe(path: Path) -> dict:
    try:
        import yaml
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _copy_scripts(src_scripts: Path, dst_scripts: Path, dry_run: bool) -> list[str]:
    copied: list[str] = []
    if not src_scripts.is_dir():
        return copied
    dst_scripts.mkdir(parents=True, exist_ok=True)
    for f in src_scripts.iterdir():
        if f.is_file() and f.suffix.lower() in RUNNABLE_EXTENSIONS:
            copied.append(f.name)
            if not dry_run:
                shutil.copy2(f, dst_scripts / f.name)
    return copied


def convert_skill(
    source: Path,
    output_dir: Path,
    dry_run: bool = False,
    merge_skill_yaml: bool = True,
) -> dict:
    """
    Convert an OpenClaw skill at `source` to HomeClaw layout under `output_dir`.
    Returns a small report dict (skill_id, skill_md, scripts_copied, references_copied, allowlist).
    """
    source = source.resolve()
    if not source.is_dir():
        return {"error": f"Not a directory: {source}"}

    skill_md_src = _find_skill_md(source)
    if not skill_md_src:
        return {"error": f"No SKILL.md in {source}"}

    skill_id = output_dir.name or source.name
    report: dict = {
        "skill_id": skill_id,
        "source": str(source),
        "output": str(output_dir),
        "skill_md": True,
        "scripts_copied": [],
        "references_copied": False,
        "allowlist": [],
    }

    if dry_run:
        report["dry_run"] = True
        report["would_create"] = [str(output_dir), str(output_dir / "SKILL.md")]

    output_dir = output_dir.resolve()
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # 1) SKILL.md
    content = skill_md_src.read_text(encoding="utf-8", errors="replace")
    skill_yaml_path = source / "skill.yaml"
    if merge_skill_yaml and skill_yaml_path.is_file():
        yaml_data = _read_yaml_safe(skill_yaml_path)
        if yaml_data:
            # Prefer manifest name/description if SKILL.md frontmatter is sparse
            name = yaml_data.get("name") or ""
            desc = yaml_data.get("description") or ""
            version = yaml_data.get("version") or ""
            if name or desc or version:
                # Ensure frontmatter has name/description (append if missing)
                if "---" in content:
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        fm, body = parts[1].strip(), parts[2].strip()
                        if name and "name:" not in fm:
                            fm = fm + "\nname: " + name
                        if desc and "description:" not in fm:
                            fm = fm + "\ndescription: " + desc.replace("\n", " ")
                        if version and "version:" not in fm:
                            fm = fm + "\nversion: " + version
                        content = "---\n" + fm + "\n---\n" + body
                else:
                    content = f"---\nname: {name}\ndescription: {desc}\nversion: {version}\n---\n\n" + content

    if not dry_run:
        (output_dir / "SKILL.md").write_text(content, encoding="utf-8")
    report["skill_md"] = True

    # 2) scripts/
    src_scripts = source / "scripts"
    dst_scripts = output_dir / "scripts"
    report["scripts_copied"] = _copy_scripts(src_scripts, dst_scripts, dry_run)
    report["allowlist"] = report["scripts_copied"]

    # 3) references/
    src_ref = source / "references"
    if src_ref.is_dir():
        report["references_copied"] = True
        if not dry_run:
            dst_ref = output_dir / "references"
            if dst_ref.exists():
                shutil.rmtree(dst_ref)
            shutil.copytree(src_ref, dst_ref)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert an OpenClaw skill folder to HomeClaw skills/ layout.",
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
        help="Output directory under project (default: skills/<source_folder_name>)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be done",
    )
    parser.add_argument(
        "--no-merge-yaml",
        action="store_true",
        help="Do not merge skill.yaml into SKILL.md frontmatter",
    )
    args = parser.parse_args()

    root = _project_root()
    source = args.source.resolve()
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()

    output_dir = args.output
    if output_dir is None:
        output_dir = root / "skills" / source.name
    else:
        output_dir = Path(output_dir)
        if not output_dir.is_absolute():
            output_dir = root / output_dir

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
        print("\nSuggested run_skill_allowlist (add to config/core.yml tools section):")
        print("  run_skill_allowlist:", report["allowlist"])
    if args.dry_run:
        print("\n[Dry run] No files written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
