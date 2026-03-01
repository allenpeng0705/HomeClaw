# Homebrew tap for HomeClaw

This folder contains the **exact files** to put in your **Homebrew tap repo** so users can run `brew install homeclaw` on Mac and Linux.

## What you need to do (one-time)

### 1. Create the tap repository on GitHub

- Go to [GitHub](https://github.com/new).
- Repository name: **`homebrew-homeclaw`** (must start with `homebrew-`).
- Owner: your account (e.g. `allenpeng0705`).
- Public, no need to add README (you’ll push these files).
- Create the repo.

### 2. Copy these files into the tap repo

Clone your new tap repo and copy the contents of this folder into it:

```bash
# Replace allenpeng0705 with your GitHub username
git clone https://github.com/allenpeng0705/homebrew-homeclaw.git
cd homebrew-homeclaw

# Copy the Formula from the HomeClaw repo (from this repo’s root)
cp /path/to/HomeClaw/scripts/homebrew-tap/Formula/homeclaw.rb Formula/

git add Formula/homeclaw.rb
git commit -m "Add HomeClaw formula"
git push
```

So the tap repo root should contain:

```
homebrew-homeclaw/
  Formula/
    homeclaw.rb
```

You can also copy this README into the tap repo if you want (e.g. as `README.md` in the tap root).

**Note:** The formula does not run `install.sh` or install Node.js/llama.cpp. Those are documented in the **install scripts** (`install.sh` for Mac/Linux, `install.ps1` for Windows) and in [DistributionHowTo.md](../docs_design/DistributionHowTo.md).

### 3. Create a release in the main HomeClaw repo

Before users can install, the formula needs a **release tarball**:

- In **github.com/allenpeng0705/HomeClaw**: create a **tag** (e.g. `v1.0.0`) and a **Release**.
- GitHub will add “Source code (tar.gz)” to the release. The URL will be:
  `https://github.com/allenpeng0705/HomeClaw/archive/refs/tags/v1.0.0.tar.gz`

### 4. Set the formula version and checksum

In your **tap repo**, edit `Formula/homeclaw.rb`:

1. Set `url` to the tarball URL for your release (e.g. `v1.0.0`).
2. Set `version` to the version string (e.g. `"1.0.0"`).
3. Set `sha256` to the checksum of that tarball.

To get the checksum from the HomeClaw repo:

```bash
# From the HomeClaw repo root
./scripts/homebrew/get-sha256.sh v1.0.0
```

Or manually:

```bash
curl -sL "https://github.com/allenpeng0705/HomeClaw/archive/refs/tags/v1.0.0.tar.gz" | shasum -a 256
```

Paste the first column (the hex string) into `sha256` in the formula, then commit and push the tap repo.

### 5. Install (for you and your users)

```bash
brew tap allenpeng0705/homeclaw
brew install homeclaw
homeclaw start
# or: homeclaw portal
```

---

## On each new release

1. In **HomeClaw** repo: create a new tag (e.g. `v1.0.1`) and a GitHub Release.
2. In your **tap** repo: update `Formula/homeclaw.rb`:
   - `url` → new tarball URL
   - `version` → new version
   - `sha256` → run `scripts/homebrew/get-sha256.sh v1.0.1` from HomeClaw repo and paste the result
3. Commit and push the tap repo.
4. Users run `brew upgrade homeclaw` to get the new version.
