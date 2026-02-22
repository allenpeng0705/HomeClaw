# HomeClaw marketing site (www.homeclaw.cn)

Static marketing website for HomeClaw: **English and Chinese**, texts with images, links to **GitHub** and the **documentation site**, plus curated docs suitable for the website.

## Structure

```
site/
├── index.html          # Language redirect (browser lang → en/ or zh/)
├── en/
│   ├── index.html      # Home (EN)
│   └── docs.html       # Curated docs (EN)
├── zh/
│   ├── index.html      # Home (中文)
│   └── docs.html       # Curated docs (中文)
├── assets/
│   ├── style.css       # Shared styles
│   ├── homeclaw-logo.png
│   ├── homeclaw-promo.png
│   ├── homeclaw-promo-zh.png
│   ├── section-mix-mode.png      # Optional: image for Mix mode section
│   ├── section-plugins-skills.png # Optional: image for Plugins & skills
│   ├── section-channels.png      # Optional: image for Channels
│   ├── section-companion.png     # Optional: image for Companion app
│   ├── section-multi-agent.png   # Optional: image for Multi-agent
│   ├── section-memory.png        # Optional: image for Memory
│   ├── section-knowledge-base.png # Optional: image for Knowledge base
│   └── section-profile.png       # Optional: image for Profile
└── README.md           # This file
```

Promo images are copied from `docs/assets/`. If you add new ones there, copy them to `site/assets/`.

**Section images:** The home page (EN + ZH) uses one image per feature section. Add these optional PNGs to `site/assets/` for a richer look; recommended size about 280×160 or similar aspect. If a file is missing, the image is hidden so the layout stays clean.

## Run locally

From the **repository root** (HomeClaw):

```bash
# Option 1: Python
python3 -m http.server 8080 --directory site

# Option 2: npx serve (if you have Node)
npx serve site -p 8080
```

Then open:

- **http://localhost:8080** — redirects to en/ or zh/ by browser language
- **http://localhost:8080/en/** — English home
- **http://localhost:8080/zh/** — 中文首页
- **http://localhost:8080/en/docs.html** — Curated docs (EN)
- **http://localhost:8080/zh/docs.html** — 本站文档 (中文)

## Deploy to Cloudflare Pages

1. **Cloudflare Dashboard** → Pages → Create project → **Upload assets** (or connect Git).
2. **Upload:**
   - Build output directory: upload the contents of the **`site/`** folder (not the repo root).
   - So: `site/index.html`, `site/en/`, `site/zh/`, `site/assets/` as the root of the deployment.
3. **Custom domain:** Add **www.homeclaw.cn** (and optionally **homeclaw.cn** with redirect to www) in Pages → Custom domains.

If you use **Git** with Cloudflare Pages:

- Set **Build configuration**: Build command = *(leave empty)*, Build output directory = **site** (so Cloudflare uses the `site/` folder as the root).
- Or use a static export: build output = **site** so the deployed root is the contents of `site/`.

## Links to GitHub and docs

- **GitHub:** `https://github.com/allenpeng0705/HomeClaw` (change in the HTML files or via search‑replace if your repo URL differs).
- **Documentation site:** Set to your MkDocs/docs deployment (e.g. `https://allenpeng0705.github.io/HomeClaw/` or `https://docs.homeclaw.cn`). Replace that URL in:
  - `site/en/index.html`
  - `site/en/docs.html`
  - `site/zh/index.html`
  - `site/zh/docs.html`

## Add or change content

- **Home:** Edit `en/index.html` and `zh/index.html` (hero, features, CTAs).
- **Curated docs:** Edit `en/docs.html` and `zh/docs.html`.
- **Styles:** Edit `assets/style.css`.
- **Images:** Add under `site/assets/` and reference as `../assets/your-image.png` from `en/` or `zh/`.

No build step: plain HTML and CSS. After editing, refresh the browser (or re-upload to Cloudflare).
