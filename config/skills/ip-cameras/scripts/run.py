#!/usr/bin/env python3
"""
IP Cameras skill runner: runs camsnap CLI for RTSP/ONVIF cameras.
If camsnap or ffmpeg is missing, prints a clear error and exits; never crashes.
"""
import sys
import subprocess
import shutil


def main() -> int:
    camsnap = shutil.which("camsnap")
    if not camsnap:
        print(
            "Error: ip-cameras: camsnap not found. Install camsnap (e.g. brew install steipete/tap/camsnap) and ensure ffmpeg is on PATH.",
            file=sys.stderr,
        )
        return 1

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(
            "Error: ip-cameras: ffmpeg not found. camsnap requires ffmpeg on PATH (e.g. brew install ffmpeg).",
            file=sys.stderr,
        )
        return 1

    args = sys.argv[1:]
    try:
        result = subprocess.run(
            [camsnap] + args,
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
        print("Error: camsnap timed out after 120s", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
