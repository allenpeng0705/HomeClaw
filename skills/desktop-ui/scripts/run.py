#!/usr/bin/env python3
"""
Desktop UI skill runner: macOS-only, runs peekaboo CLI.
On non-macOS or if peekaboo is missing, prints a clear error and exits; never crashes.
"""
import sys
import subprocess
import shutil


def main() -> int:
    if sys.platform != "darwin":
        print("Error: Desktop UI automation is only available on macOS. On this platform the desktop-ui skill cannot run peekaboo.", file=sys.stderr)
        return 1

    peekaboo = shutil.which("peekaboo")
    if not peekaboo:
        print("Error: peekaboo not found. On macOS install with: brew install steipete/tap/peekaboo", file=sys.stderr)
        return 1

    args = sys.argv[1:]
    try:
        result = subprocess.run(
            [peekaboo] + args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if err:
            out = f"{out}\nstderr:\n{err}" if out else f"stderr:\n{err}"
        print(out or "(no output)")
        return result.returncode
    except subprocess.TimeoutExpired:
        print("Error: peekaboo timed out after 120s", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
