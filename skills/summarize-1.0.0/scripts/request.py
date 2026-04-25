#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
Summarize CLI wrapper for HomeClaw run_skill.

Usage:
  request.py <url or file path> [--model <model>] [--length <length>] [--json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


def _summarize_binary() -> str:
    """Return path to summarize binary, or raise ValueError if not found."""
    bin_path = shutil.which("summarize")
    if not bin_path:
        raise ValueError(
            "summarize not found on PATH. Install: curl -Ls https://summarize.sh/install | sh\n"
            "Or see https://summarize.sh for other installation options."
        )
    return bin_path


def _run_summarize(argv: list[str], timeout_sec: int = 120) -> tuple[int, str, str]:
    """Run summarize with given argv. Returns (returncode, stdout, stderr)."""
    binary = _summarize_binary()
    try:
        proc = subprocess.run(
            [binary] + argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        raise ValueError(f"summarize timed out after {timeout_sec}s")
    except Exception as e:
        raise ValueError(f"Failed to run summarize: {e}")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: request.py <url or file path> [--model <model>] [--length <short|medium|long>] [--json]", file=sys.stderr)
        return 1

    # Parse known args so we can pass through extras
    parser = argparse.ArgumentParser(prog="request.py")
    parser.add_argument("input", nargs="?", default="", help="URL or file path to summarize")
    parser.add_argument("--model", dest="model", default=None)
    parser.add_argument("--length", dest="length", default=None)
    parser.add_argument("--json", dest="json", action="store_true")
    parser.add_argument("--extract-only", dest="extract_only", action="store_true")
    parser.add_argument("--firecrawl", dest="firecrawl", default=None)
    parser.add_argument("--youtube", dest="youtube", default=None)
    known, extra = parser.parse_known_args(sys.argv[1:])

    if not known.input:
        print("Error: URL or file path is required as the first argument.", file=sys.stderr)
        return 1

    argv = [known.input]
    if known.model:
        argv.extend(["--model", known.model])
    if known.length:
        argv.extend(["--length", known.length])
    if known.json:
        argv.append("--json")
    if known.extract_only:
        argv.append("--extract-only")
    if known.firecrawl:
        argv.extend(["--firecrawl", known.firecrawl])
    if known.youtube:
        argv.extend(["--youtube", known.youtube])
    argv.extend(extra)

    rc, stdout, stderr = _run_summarize(argv)

    if rc != 0:
        combined = (stderr or stdout or "").strip()
        print(f"summarize exited with {rc}: {combined}", file=sys.stderr)
        return 1

    if known.json:
        # Already JSON — pass through
        print(stdout.strip())
    else:
        # Plain text: wrap in structured output
        try:
            print(json.dumps({
                "success": True,
                "summary": stdout.strip(),
                "input": known.input,
            }, ensure_ascii=False, indent=2))
        except Exception:
            # Fallback: just print raw output
            print(stdout.strip())

    return 0


if __name__ == "__main__":
    sys.exit(main())
