# HomeClaw documentation (website source)

This **`docs/`** folder is the source for the HomeClaw doc site on GitHub Pages (Install, Run, Channels, Tools, Models, Platform, Help).

- **`docs_design/`** in this repo holds design and internal docs (PluginsGuide, MemoryAndDatabase, etc.); not used by the website build.
- **`docs/`** (this folder) = curated, organized content for the public site.

**Build the site locally:** From repo root, `pip install mkdocs-material -e .` (installs the subpath plugin), then `mkdocs build`. Output is in `site/`.  
**Preview:** `mkdocs serve` and open http://127.0.0.1:8000  
**Diagram images (optional):** The intro page uses static SVGs for the system-overview and data-flow diagrams. The GitHub Action generates them from `docs/diagrams/*.mmd` with [mermaid-cli](https://github.com/mermaid-js/mermaid-cli). To build locally with diagrams: `mkdir -p docs/assets && npx -p @mermaid-js/mermaid-cli mmdc -i docs/diagrams/system-overview.mmd -o docs/assets/system-overview.svg && npx -p @mermaid-js/mermaid-cli mmdc -i docs/diagrams/data-flow.mmd -o docs/assets/data-flow.svg` (requires Node.js).  
**Deploy:** Push to `main`; the GitHub Action (`.github/workflows/docs.yml`) builds and deploys to GitHub Pages. Enable Pages in repo Settings → Pages → Source: GitHub Actions.
