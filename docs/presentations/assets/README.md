# Assets for HomeClaw intro presentation

Place optional image files here so the script can embed them in the PowerPoint. **Text uses the default theme** so it stays readable; only add images you want.

## Background (all slides, optional)

- Put **background.png** or **background.jpg** in this folder.
- The script uses it as a **full-slide background** (sent to back) on every slide. Use a light or subtle image so title and bullet text remain clear.

## Logo (title slide)

- **Option A:** Put **HomeClaw_Banner.jpg** in the **repo root** (same folder as README.md).
- **Option B:** Put **logo.png** or **logo.jpg** in this folder.

The script uses the first one found.

## Architecture (Architecture slide)

The **Architecture** slide can show the system overview diagram:

1. Export **docs/assets/system-overview.svg** to PNG (e.g. in a browser: open the SVG → right‑click → Save image / export as PNG, or use a vector tool).
2. Save as **system-overview.png** in this folder.

On macOS, the script may also create this PNG from the SVG using `qlmanage` if the file is missing. You can also install `cairosvg` and the script will try to generate the PNG automatically.
