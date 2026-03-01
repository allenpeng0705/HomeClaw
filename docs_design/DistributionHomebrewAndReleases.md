# HomeClaw Distribution: Homebrew, Releases, and Easy Install

This doc outlines how to make HomeClaw easy to distribute (e.g. **Homebrew on Mac**) and what to publish on GitHub Releases.

## Options Overview

| Method | Audience | What it installs | Effort |
|--------|----------|------------------|--------|
| **GitHub Releases** | Everyone | DMG (Mac), ZIP (Windows), tarball (full package) | Low: upload artifacts from CI or scripts |
| **Homebrew Formula** | Mac/Linux (devs) | Core (Python) + `homeclaw` CLI | Medium: maintain a formula |
| **Homebrew Cask** | Mac (end users) | Full HomeClaw.app (Core + Companion) from DMG | Medium: maintain a cask |
| **pip install** | Python users | Core only (if we add a proper pyproject.toml for Core) | Medium: package Core as a Python package |

---

## 1. GitHub Releases (recommended first step)

- Create a **tag** (e.g. `v1.0.0`) and a **Release** on GitHub.
- Attach artifacts built by your existing scripts:
  - **Mac:** `dist/HomeClawApp.dmg` (Companion only) and/or full package `dist/HomeClaw-package-YYYYMMDD.tar.gz` (from `package_homeclaw.sh`).
  - **Windows:** `dist/HomeClaw-Companion-windows.zip`.
- Users download the right file for their OS. No extra tooling.

---

## 2. Homebrew on Mac (and Linux)

Homebrew has two concepts:

- **Formula** — builds from source or a tarball; installs CLI tools and libraries. Good for the **Core** (Python) so users run `homeclaw start` (or `python -m main start`).
- **Cask** — installs GUI apps (e.g. from a DMG). Good for the **full HomeClaw.app** (Core + Companion in one app).

### Option A: Homebrew Formula (Core CLI)

A formula can:

1. Download a **source tarball** from a GitHub Release (e.g. `https://github.com/your-org/HomeClaw/archive/refs/tags/v1.0.0.tar.gz`).
2. Or **clone the repo** and use a specific tag.
3. Create a **virtualenv** (or use `pip install --prefix`), run `pip install -r requirements.txt`.
4. Install a **wrapper script** (e.g. `homeclaw`) that runs `python -m main "$@"` from the installed tree.

Then users run:

```bash
brew tap your-org/homeclaw   # one-time, if using a tap
brew install homeclaw
homeclaw start
```

Example formula is in **`scripts/homebrew/Homeclaw.rb`** (see below). You can put it in a **personal tap** (e.g. `your-org/homebrew-homeclaw`) so you don’t need to submit to homebrew-core.

### Option B: Homebrew Cask (full app)

If you build a **single DMG** that contains the full **HomeClaw.app** (from `package_homeclaw.sh`), you can add a **Cask** that:

1. Downloads that DMG from a GitHub Release.
2. Opens the DMG and copies `HomeClaw.app` to `/Applications`.

Then users run:

```bash
brew tap your-org/homeclaw
brew install --cask homeclaw
# Then open HomeClaw from Applications
```

Cask file would look like (adjust URL and app name to your release):

```ruby
cask "homeclaw" do
  version "1.0.0"
  sha256 "..."  # sha256 of the DMG file

  url "https://github.com/your-org/HomeClaw/releases/download/v#{version}/HomeClaw-#{version}.dmg"
  name "HomeClaw"
  desc "HomeClaw Core + Companion app"
  homepage "https://github.com/your-org/HomeClaw"

  app "HomeClaw.app"
end
```

You’d need to **build and upload** that DMG (or a zip of the .app) on each release.

---

## 3. What to add in this repo

1. **Scripts or CI** to build and attach to GitHub Releases:
   - `dist/HomeClawApp.dmg` (Companion only, Mac)
   - `dist/HomeClaw-Companion-windows.zip` (Companion only, Windows)
   - Optional: full Mac package (e.g. `HomeClaw-1.0.0-mac.tar.gz` or a DMG containing HomeClaw.app).

2. **Homebrew tap repo** (e.g. `your-org/homebrew-homeclaw`) with:
   - `Formula/homeclaw.rb` — installs Core + `homeclaw` CLI (see sample below).
   - Optional: `Cask/homeclaw.rb` — installs HomeClaw.app from DMG.

3. **Docs** (e.g. in README): “Install via Homebrew” and “Download from Releases”.

---

## 4. Summary

- **Easiest:** Use **GitHub Releases** and document “Download the DMG (Mac) or ZIP (Windows) from the Releases page.”
- **Mac power users:** Add a **Homebrew formula** (and optionally a cask) in a **tap**; point them to `brew tap` + `brew install homeclaw` (and/or `brew install --cask homeclaw`).
- **Later:** If you package Core as a Python package (`pyproject.toml` for the main app), `pip install homeclaw` becomes another option.

The sample formula in `scripts/homebrew/Homeclaw.rb` assumes installation from a **GitHub source tarball** and installs a `homeclaw` script that runs Core.

**Concrete steps** to set up the tap, release tarball, and (optionally) Winget/Chocolatey: see **[DistributionHowTo.md](DistributionHowTo.md)**.
