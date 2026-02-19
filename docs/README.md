# HomeClaw documentation (website source)

This **`docs/`** folder is the source for the HomeClaw doc site on GitHub Pages (Install, Run, Channels, Tools, Models, Platform, Help).

- **`docs_design/`** in this repo holds design and internal docs (PluginsGuide, MemoryAndDatabase, etc.); not used by the website build.
- **`docs/`** (this folder) = curated, organized content for the public site.

**Build the site locally:** From repo root, `pip install mkdocs-material -e .` (installs the subpath plugin), then `mkdocs build`. Output is in `site/`.  
**Preview:** `mkdocs serve` and open http://127.0.0.1:8000  
**Diagram images (optional):** The intro page uses static SVGs for the system-overview and data-flow diagrams. From the **`docs/`** folder: run **`npm run install:no-browser`** (skips Puppeteer’s Chrome download so install completes; use this if `npm install` fails with Chrome download errors). Then generate SVGs: **on macOS** run **`npm run diagrams:mac`** (uses your installed Google Chrome); **on Linux/Windows** set your Chrome path and run diagrams, e.g. `export PUPPETEER_EXECUTABLE_PATH="/usr/bin/google-chrome"` then `npm run diagrams`. If mmdc still can't find Chrome, export SVGs from [Mermaid Live Editor](https://mermaid.live) using `diagrams/*.mmd` and save to `assets/`. The GitHub Action generates diagrams on deploy.  
**Deploy:** Push to `main`; the GitHub Action (`.github/workflows/docs.yml`) builds and deploys to GitHub Pages. Enable Pages in repo Settings → Pages → Source: GitHub Actions.
