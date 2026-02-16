# HomeClaw documentation (website source)

This **`docs/`** folder is the source for the HomeClaw doc site on GitHub Pages (Install, Run, Channels, Tools, Models, Platform, Help).

- **`docs_design/`** in this repo holds design and internal docs (PluginsGuide, MemoryAndDatabase, etc.); not used by the website build.
- **`docs/`** (this folder) = curated, organized content for the public site.

**Build the site locally:** From repo root, `pip install mkdocs-material` then `mkdocs build`. Output is in `site/`.  
**Preview:** `mkdocs serve` and open http://127.0.0.1:8000  
**Deploy:** Push to `main`; the GitHub Action (`.github/workflows/docs.yml`) builds and deploys to GitHub Pages. Enable Pages in repo Settings → Pages → Source: GitHub Actions.
