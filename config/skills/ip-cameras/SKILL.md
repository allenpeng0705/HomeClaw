---
name: ip-cameras
description: Capture frames or clips from RTSP/ONVIF IP cameras. Uses camsnap CLI (and ffmpeg). Use when the user asks to snapshot or record from a configured network camera. Cross-platform if camsnap and ffmpeg are installed; if not, returns a clear error without crashing.
---

# IP Cameras (RTSP/ONVIF)

This skill wraps **camsnap** for network cameras: snap a frame, record a short clip, or watch for motion.

**Requirements:** `camsnap` and `ffmpeg` on PATH. Config: `~/.config/camsnap/config.yaml`. Add a camera: `camsnap add --name kitchen --host 192.168.0.10 --user user --pass pass`.

**Platform:** Cross-platform (Windows, Linux, macOS) if camsnap is installed. If camsnap or ffmpeg is missing, the script returns a clear error; Core and the skill runner do not crash.

**Install (macOS):** `brew install steipete/tap/camsnap` and `brew install ffmpeg`

## Usage via run_skill

- **Discover cameras:** `run_skill(skill_name="ip-cameras", script="run.py", args=["discover", "--info"])`
- **Snapshot:** `run_skill(..., args=["snap", "kitchen", "--out", "/tmp/shot.jpg"])`
- **Clip (video):** `run_skill(..., args=["clip", "kitchen", "--dur", "5s", "--out", "/tmp/clip.mp4"])`
- **Doctor (check config):** `run_skill(..., args=["doctor", "--probe"])`

Pass any camsnap subcommand and flags as `args`. If camsnap is not found, the script returns an error message and exits without crashing.
