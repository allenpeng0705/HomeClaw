---
name: desktop-ui
description: macOS-only desktop UI automation (screens, windows, menubar, click, type). Uses peekaboo CLI. Use when the user asks to control or inspect the desktop UI on macOS (e.g. list windows, click an element, capture screen). Not available on Windows or Linux; return a clear message on unsupported platforms.
trigger:
  patterns: ["desktop\\s+ui|peekaboo|list\\s+windows?|click\\s+(on\\s+)?(element|screen)|screen\\s+capture|桌面|自动化"]
  instruction: "The user asked about desktop UI automation (macOS). Use run_skill(skill_name='desktop-ui', script='run.py', args=[list|image|see|click|type, ...]). macOS only; peekaboo required."
---

# Desktop UI (macOS only)

This skill wraps **peekaboo** for macOS desktop automation: list apps/windows/screens, capture screenshots, click UI elements, type text, run hotkeys.

**Platform:** macOS only. On Windows or Linux, `run_skill(desktop-ui, run.py, ...)` returns a clear message; Core and the skill runner do not crash.

**Install (macOS):** `brew install steipete/tap/peekaboo`

**Permissions:** Screen Recording and Accessibility (System Settings → Privacy & Security).

## Usage via run_skill

- **List apps:** `run_skill(skill_name="desktop-ui", script="run.py", args=["list", "apps"])`
- **Capture screen:** `run_skill(..., args=["image", "--path", "/tmp/screen.png"])`
- **See (annotated UI map):** `run_skill(..., args=["see", "--annotate", "--path", "/tmp/see.png"])`
- **Click element:** `run_skill(..., args=["click", "--on", "B1"])`
- **Type text:** `run_skill(..., args=["type", "Hello", "--return"])`

Pass any peekaboo subcommand and flags as `args`. If the platform is not macOS or peekaboo is not installed, the script returns an error message and exits without crashing.
