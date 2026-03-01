# Mac & Linux distribution checklist (Homebrew)

Everything under **HomeClaw** for the formula and tap is in this repo. You only need to do a few things **on GitHub** and in your **tap repo**.

---

## What’s already in this repo

| Item | Location |
|------|----------|
| Formula (for tap) | `scripts/homebrew-tap/Formula/homeclaw.rb` |
| Tap setup instructions | `scripts/homebrew-tap/README.md` |
| SHA256 helper | `scripts/homebrew/get-sha256.sh` |
| Source formula (reference) | `scripts/homebrew/Homeclaw.rb` |

---

## What you need to do

### 1. On GitHub: create the tap repository

- Go to **https://github.com/new**
- **Repository name:** `homebrew-homeclaw` (must start with `homebrew-`)
- **Owner:** your account (e.g. `allenpeng0705`)
- **Public**, create **without** README
- Create the repository

### 2. On your machine: push the Formula to the tap

```bash
# Clone your new tap repo (replace allenpeng0705 with your username)
git clone https://github.com/allenpeng0705/homebrew-homeclaw.git
cd homebrew-homeclaw

# Copy the Formula from the HomeClaw repo
mkdir -p Formula
cp /path/to/HomeClaw/scripts/homebrew-tap/Formula/homeclaw.rb Formula/

# Optional: copy the tap README
cp /path/to/HomeClaw/scripts/homebrew-tap/README.md .

git add .
git commit -m "Add HomeClaw formula"
git push origin main
```

### 3. On GitHub: create a release in the HomeClaw repo

- In **github.com/allenpeng0705/HomeClaw**: go to **Releases** → **Create a new release**
- **Tag:** create a new tag, e.g. `v1.0.0`
- **Release title:** e.g. `v1.0.0`
- Publish the release. GitHub will attach **“Source code (tar.gz)”** automatically.
- The tarball URL will be:  
  `https://github.com/allenpeng0705/HomeClaw/archive/refs/tags/v1.0.0.tar.gz`

### 4. Set the formula’s version and SHA256 in the tap repo

In your **homebrew-homeclaw** repo, edit `Formula/homeclaw.rb`:

1. **url** — set to your release tarball URL (e.g. with `v1.0.0`).
2. **version** — set to `"1.0.0"`.
3. **sha256** — from the **HomeClaw** repo root run:
   ```bash
   ./scripts/homebrew/get-sha256.sh v1.0.0
   ```
   Paste the printed hash into the `sha256 "..."` line in the formula.

Then commit and push the tap repo:

```bash
cd /path/to/homebrew-homeclaw
# edit Formula/homeclaw.rb as above
git add Formula/homeclaw.rb
git commit -m "Set version and sha256 for v1.0.0"
git push
```

### 5. Install and verify

```bash
brew tap allenpeng0705/homeclaw
brew install homeclaw
homeclaw --help
homeclaw portal   # optional: start Portal
```

---

## For each new release (e.g. v1.0.1)

1. **HomeClaw repo:** Create a new tag and GitHub Release (e.g. `v1.0.1`).
2. **Tap repo:** In `Formula/homeclaw.rb` update:
   - `url` → new tarball URL
   - `version` → `"1.0.1"`
   - `sha256` → run `./scripts/homebrew/get-sha256.sh v1.0.1` from HomeClaw repo and paste the result
3. Commit and push the tap repo.
4. Users run `brew upgrade homeclaw` to get the new version.

---

## Summary: your actions

| Step | Where | Action |
|------|--------|--------|
| 1 | GitHub | Create repo **homebrew-homeclaw** (public, empty). |
| 2 | Your machine | Clone tap repo, copy `scripts/homebrew-tap/Formula/homeclaw.rb` into `Formula/`, push. |
| 3 | GitHub (HomeClaw) | Create a release with tag e.g. **v1.0.0** (so the source tarball exists). |
| 4 | Tap repo | Edit formula: set **url**, **version**, **sha256** (use `scripts/homebrew/get-sha256.sh v1.0.0`), push. |
| 5 | Your machine | `brew tap allenpeng0705/homeclaw && brew install homeclaw` to test. |

After that, anyone can run `brew tap allenpeng0705/homeclaw && brew install homeclaw` (and later `brew upgrade homeclaw`).
