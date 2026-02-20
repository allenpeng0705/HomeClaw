# HomeClaw presentations

## HomeClaw-Intro.pptx

A short PowerPoint introduction to HomeClaw (what it is, why, architecture, companion app, memory, mix mode, plugins & skills, get started). **Text uses the default theme** so it stays readable.

**Optional images** (see `docs/presentations/assets/README.md`):

- **Background** — Put `docs/presentations/assets/background.png` (or `.jpg`) to use one image as full-slide background on all slides. Use a light or subtle image so text stays clear.
- **Logo** — Put `HomeClaw_Banner.jpg` in the repo root, or `docs/presentations/assets/logo.png`. Used on the title slide.
- **Architecture** — Put `docs/presentations/assets/system-overview.png` (export from `docs/assets/system-overview.svg`). On macOS the script may generate this automatically. Used on the Architecture slide.

**To regenerate:**

```bash
pip install python-pptx   # or: python3 -m pip install python-pptx
python scripts/build_homeclaw_intro_ppt.py           # English → HomeClaw-Intro.pptx
python scripts/build_homeclaw_intro_ppt.py --lang zh  # 中文 → HomeClaw-Intro-zh.pptx
```

Output: `docs/presentations/HomeClaw-Intro.pptx` (English) or `HomeClaw-Intro-zh.pptx` (简体中文). Same layout and images; only the text is translated for the Chinese version. If logo or architecture image are missing, the script prints a short tip.
