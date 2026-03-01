# How to Distribute HomeClaw via Homebrew, Winget, and Similar Tools

This doc gives **concrete steps** to distribute HomeClaw via package managers. It builds on [DistributionHomebrewAndReleases.md](DistributionHomebrewAndReleases.md) and [DistributionStrategyLightweightCoreAndCompanion.md](DistributionStrategyLightweightCoreAndCompanion.md). You already have **install.sh** (Mac/Linux) and **install.ps1** (Windows) in the project root for script-based installs; below is how to add **Homebrew**, **Winget**, and (optionally) **Chocolatey** / **Linux packages**.

---

## 1. Overview

| Platform | Script (already have) | Package manager | What to add |
|----------|------------------------|-----------------|-------------|
| **Mac** | `install.sh` | **Homebrew** (Formula + optional Cask) | Tap repo + formula; release tarball |
| **Linux** | `install.sh` | **Homebrew** (same formula works on Linux) or distro-specific later | Same formula in tap; optional snap/PPA |
| **Windows** | `install.ps1` | **Winget** (and optionally **Chocolatey**) | GitHub Release + manifest; optional choco package |

**Do Homebrew / Winget run our install scripts?**  
- **No.** **Homebrew** does not run `install.sh`. The formula has its own install path (tarball → venv → pip → `homeclaw` wrapper).  
- **Winget** does not run `install.ps1` unless you make that the installer (e.g. you package an EXE that invokes `install.ps1`, or you ship a ZIP and document “extract then run install.ps1”). The usual Winget approach is to install a fixed artifact (ZIP or EXE); whether that artifact runs `install.ps1` is up to how you build it.

So: **script install** = user runs `install.sh` or `install.ps1` themselves (clone or download). **Package manager** = user runs `brew install homeclaw` or `winget install HomeClaw`; those use the formula/manifest and do not call your scripts unless you explicitly wrap them.

---

## 2. Homebrew (Mac and Linux)

Homebrew lets users run `brew install homeclaw` (Core CLI). Optionally a **Cask** installs a full app (e.g. DMG).

### 2.1 What you need

- A **GitHub Release** with a **source tarball** (e.g. `v1.0.0` → `https://github.com/allenpeng0705/HomeClaw/archive/refs/tags/v1.0.0.tar.gz`). GitHub creates this automatically when you create a release from a tag.
- A **tap** repo: a second repo named `homebrew-homeclaw` (or `homebrew-<something>`) that contains the formula. By convention: `github.com/allenpeng0705/homebrew-homeclaw` with a `Formula/` directory.

### 2.2 Steps

1. **Create the tap repo** (one-time)  
   - On GitHub: New repository → name `homebrew-homeclaw` (or `homebrew-HomeClaw`).  
   - Clone it and add a `Formula` directory.

2. **Copy and adapt the formula**  
   - The repo already has a sample: **`scripts/homebrew/Homeclaw.rb`**.  
   - Copy it to your tap as `Formula/homeclaw.rb` (lowercase `homeclaw` is the brew name).  
   - Edit:
     - `url`: point to the **release tarball** (e.g. `https://github.com/allenpeng0705/HomeClaw/archive/refs/tags/v1.0.0.tar.gz`).
     - `sha256`: run `brew fetch homeclaw` (with the formula in your tap) or `curl -sL <url> | shasum -a 256` to get the checksum; put it in the formula.
     - `homepage`: your repo URL (e.g. `https://github.com/allenpeng0705/HomeClaw`).
   - The formula uses `pkgshare` so Core runs from a fixed path; the `homeclaw` script does `cd pkgshare && python -m main "$@"`. Config lives under that path (or you document `~/HomeClaw` and symlink; the sample caveats say "Put GGUF models in ~/HomeClaw/models").

3. **Install (for users)**  
   ```bash
   brew tap allenpeng0705/homeclaw   # or your-org/homebrew-homeclaw
   brew install homeclaw
   homeclaw start
   ```

4. **On each release**  
   - Tag a new version (e.g. `v1.0.1`).  
   - Create a GitHub Release from that tag (no need to upload the tarball; GitHub provides "Source code (tar.gz)").  
   - In the tap repo: update `Formula/homeclaw.rb` (`url`, `version`, `sha256`), then commit and push. Users get updates with `brew upgrade homeclaw`.

### 2.3 Optional: Homebrew Cask (full app)

If you build a **DMG** (e.g. from `package_homeclaw.sh` or similar) and upload it to a GitHub Release, you can add a **Cask** so users run `brew install --cask homeclaw` and get the app in Applications. The Cask points at the DMG URL and copies the app. See the Cask example in [DistributionHomebrewAndReleases.md](DistributionHomebrewAndReleases.md).

---

## 3. Windows: Winget

Winget is the built-in Windows package manager. Submitting a package makes HomeClaw discoverable via `winget search homeclaw` and `winget install HomeClaw` (or your chosen ID).

### 3.1 What you need

- A **stable download URL** for the installer or portable package. Best: a **GitHub Release** with a fixed URL per version, e.g.  
  `https://github.com/allenpeng0705/HomeClaw/releases/download/v1.0.0/HomeClaw-1.0.0-win.zip`.
- A **manifest** (YAML) that describes the package. Winget uses a community repo: [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs). You submit a PR that adds your manifest.

### 3.2 Steps

1. **Create a release asset**  
   - For Core-only (no embedded Python): a **ZIP** of the repo (or a minimal bundle with `main.py`, `base/`, `core/`, `config/`, etc.) that users extract and run with their own Python, or run `install.ps1` from that zip.  
   - Alternatively: an **EXE installer** (e.g. NSIS or Inno Setup) that installs Core + optional launcher.  
   - Upload the ZIP or EXE to a GitHub Release (e.g. `HomeClaw-1.0.0-win.zip`).

2. **Create the manifest**  
   - Install: `winget install wingetcreate`.  
   - Run: `wingetcreate new` and follow prompts (PackageIdentifier e.g. `AllenPeng0705.HomeClaw`, download URL, version, etc.).  
   - Or create YAML manually: see [Create your package manifest](https://learn.microsoft.com/en-us/windows/package-manager/package/manifest). You need at least:
     - `PackageIdentifier` (e.g. `AllenPeng0705.HomeClaw`)
     - `PackageVersion`, `Publisher`, `PackageName`
     - `InstallerType` (e.g. `zip` or `exe`) and `InstallerUrl` (your release URL)

3. **Submit to winget-pkgs**  
   - Fork [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs), add your manifest under `manifests/a/AllenPeng0705/HomeClaw/1.0.0/` (structure required by the repo).  
   - Or use: `wingetcreate submit --prtitle "Add HomeClaw" --token <GITHUB_TOKEN> <path-to-manifest>` (see [winget-create submit](https://github.com/microsoft/winget-create/blob/main/doc/submit.md)).  
   - After the PR is merged, users can run: `winget install AllenPeng0705.HomeClaw`.

4. **Updates**  
   - For each new version: new release asset + new manifest version (or update existing manifest); submit another PR to winget-pkgs.

---

## 4. Windows: Chocolatey (optional)

Chocolatey is another Windows package manager. Many users run `choco install <name>`.

### 4.1 Steps

1. **Create a package**  
   - You need a **nuspec** file and (usually) a script (PowerShell) that downloads your release ZIP/EXE and installs it.  
   - Docs: [Create packages](https://docs.chocolatey.org/en-us/create/create-packages).  
   - Install URL: point at the same GitHub Release asset you use for Winget.

2. **Publish**  
   - Push the package to [Chocolatey community repository](https://community.chocolatey.org/packages) (requires approval) or host your own feed.

---

## 5. Linux (besides Homebrew and install.sh)

- **Homebrew on Linux:** The same Formula in your tap works with `brew install homeclaw` on Linux; no extra work.
- **install.sh:** Already supports Linux; users can `curl -sL <url>/install.sh | bash` or clone and run `./install.sh`.
- **Snap / Flatpak / PPA:** Possible later. They require building a snapcraft.yaml, flatpak manifest, or PPA packaging; more effort. Prefer documenting **install.sh** and **Homebrew** first.

---

## 6. Summary checklist

| Step | Mac/Linux | Windows |
|------|-----------|---------|
| **Script install** | ✅ `install.sh` in repo | ✅ `install.ps1` in repo |
| **GitHub Release** | Tag + release; use "Source code (tar.gz)" for Homebrew | Tag + release; add ZIP or EXE asset for Winget |
| **Homebrew** | Create tap repo; add `Formula/homeclaw.rb` (from `scripts/homebrew/Homeclaw.rb`); set url/sha256/version to release | N/A |
| **Winget** | N/A | Build release ZIP/EXE; create manifest; submit PR to winget-pkgs |
| **Chocolatey** | N/A | Optional: nuspec + script; publish to choco |

**Order of operations:** (1) Start tagging releases and creating GitHub Releases. (2) Add the Homebrew tap and formula so Mac/Linux users can `brew install homeclaw`. (3) Add a Windows release asset and Winget manifest so Windows users can `winget install HomeClaw`. (4) Optionally add Chocolatey and/or a Homebrew Cask for a full app.

**References:**  
- [DistributionHomebrewAndReleases.md](DistributionHomebrewAndReleases.md) — options, formula/cask examples.  
- [DistributionStrategyLightweightCoreAndCompanion.md](DistributionStrategyLightweightCoreAndCompanion.md) — what to ship (Core vs Companion, models path).  
- **Mac/Linux step-by-step:** [DistributionMacLinuxChecklist.md](DistributionMacLinuxChecklist.md) — what to do on GitHub and in the tap repo.  
- Tap contents: **`scripts/homebrew-tap/`** (Formula + README). SHA256 helper: **`scripts/homebrew/get-sha256.sh`**.
