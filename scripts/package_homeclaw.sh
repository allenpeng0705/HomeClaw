#!/usr/bin/env bash
# Package HomeClaw as a single launcher app (macOS) or folder:
#   - Embedded Python (no user install required)
#   - Core + full config (core.yml with all comments/fields)
#   - Dependencies installed into the bundle
#   - Companion app; launcher starts Core then opens Companion
# Models are NOT included; users put GGUF etc. in ~/HomeClaw/models (see PACKAGE_README).
#
# Usage: ./scripts/package_homeclaw.sh [--no-companion] [--no-launcher] [--output DIR] [--no-archive]
#   --no-launcher  Only produce folder (Core + config + Companion), no embedded Python or .app launcher.
#   Default on macOS: build launcher app (HomeClaw.app) with embedded Python + Node.js + Core + Companion.
#   Node.js is bundled so system_plugins/homeclaw-browser (WebChat, Control UI) works without user installing Node.
#
# Usage: ./scripts/package_homeclaw.sh [--no-companion] [--no-launcher] [--no-node] [--output DIR] [--no-archive]

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Options
BUILD_COMPANION=1
OUTPUT_DIR=""
CREATE_ARCHIVE=1
BUILD_LAUNCHER=1
BUNDLE_NODE=1
# Python build-standalone release (astral-sh); use 3.11 for compatibility (version must match release assets)
PYTHON_STANDALONE_RELEASE="20260211"
PYTHON_VERSION="3.11.14"
# Node.js LTS for homeclaw-browser (system_plugins)
NODE_VERSION="20.18.0"

while [[ $# -gt 0 ]]; do
  case $1 in
    --no-companion)
      BUILD_COMPANION=0
      shift
      ;;
    --no-launcher)
      BUILD_LAUNCHER=0
      shift
      ;;
    --no-node)
      BUNDLE_NODE=0
      shift
      ;;
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --no-archive)
      CREATE_ARCHIVE=0
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--no-companion] [--no-launcher] [--no-node] [--output DIR] [--no-archive]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$REPO_ROOT/dist/HomeClaw-package-$(date +%Y%m%d)"
fi

# On non-macOS or --no-launcher, only build folder (no embedded Python / .app)
if [[ "$(uname -s)" != "Darwin" ]]; then
  BUILD_LAUNCHER=0
fi

echo "Package output: $OUTPUT_DIR"
echo "Launcher app (embedded Python + Core + Companion): $([[ $BUILD_LAUNCHER -eq 1 ]] && echo 'yes' || echo 'no')"
mkdir -p "$OUTPUT_DIR"

# ---------- Copy Core code and config (full core.yml) ----------
echo "Copying Core code and config (full core.yml)..."

rsync -a \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.git' \
  --exclude='database' \
  --exclude='logs' \
  --exclude='models' \
  --exclude='*.gguf' \
  --exclude='.env' \
  --exclude='venv' \
  --exclude='.DS_Store' \
  --exclude='node_modules' \
  --exclude='site' \
  --exclude='docs' \
  --exclude='docs_design' \
  --exclude='tests' \
  --exclude='plugs_disabled' \
  --exclude='llama.cpp-master' \
  --exclude='mkdocs_subpath_plugin.egg-info' \
  --exclude='clients' \
  "$REPO_ROOT/main.py" \
  "$REPO_ROOT/base" \
  "$REPO_ROOT/core" \
  "$REPO_ROOT/llm" \
  "$REPO_ROOT/memory" \
  "$REPO_ROOT/tools" \
  "$REPO_ROOT/hybrid_router" \
  "$REPO_ROOT/plugins" \
  "$REPO_ROOT/channels" \
  "$REPO_ROOT/system_plugins" \
  "$REPO_ROOT/examples" \
  "$REPO_ROOT/ui" \
  "$REPO_ROOT/requirements.txt" \
  "$OUTPUT_DIR/"

mkdir -p "$OUTPUT_DIR/config"
cp "$REPO_ROOT/config/core.yml" "$OUTPUT_DIR/config/"
cp "$REPO_ROOT/config/user.yml" "$OUTPUT_DIR/config/"
cp "$REPO_ROOT/config/core.yml" "$OUTPUT_DIR/config/core.yml.reference" 2>/dev/null || true
rsync -a \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "$REPO_ROOT/config/workspace" \
  "$REPO_ROOT/config/skills" \
  "$REPO_ROOT/config/prompts" \
  "$REPO_ROOT/config/hybrid" \
  "$OUTPUT_DIR/config/" 2>/dev/null || true

# ---------- Companion app (macOS) ----------
if [[ $BUILD_COMPANION -eq 1 ]]; then
  echo "Building Companion app (macOS)..."
  COMPANION_DIR="$REPO_ROOT/clients/homeclaw_companion"
  if [[ ! -d "$COMPANION_DIR" ]]; then
    echo "Companion not found at $COMPANION_DIR, skipping." >&2
  else
    (cd "$COMPANION_DIR" && flutter pub get && flutter build macos --release)
    COMPANION_APP="$COMPANION_DIR/build/macos/Build/Products/Release/homeclaw_companion.app"
    if [[ -d "$COMPANION_APP" ]]; then
      mkdir -p "$OUTPUT_DIR/companion"
      cp -R "$COMPANION_APP" "$OUTPUT_DIR/companion/"
      echo "Companion app copied to $OUTPUT_DIR/companion/"
    else
      echo "Companion build did not produce .app at $COMPANION_APP" >&2
    fi
  fi
else
  echo "Skipping Companion build (--no-companion)."
fi

# ---------- Bundle Node.js and npm install for system_plugins/homeclaw-browser ----------
# Core starts homeclaw-browser with "node server.js"; bundling Node ensures it works without user install.
if [[ $BUILD_LAUNCHER -eq 1 ]] && [[ $BUNDLE_NODE -eq 1 ]]; then
  echo "Bundling Node.js and installing homeclaw-browser dependencies..."
  ARCH=$(uname -m)
  if [[ "$ARCH" == "arm64" ]]; then
    NODE_ARCH="arm64"
  else
    NODE_ARCH="x64"
  fi
  NODE_TAR="node-v${NODE_VERSION}-darwin-${NODE_ARCH}.tar.gz"
  NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TAR}"
  NODE_CACHE="$REPO_ROOT/dist/node-standalone-cache"
  mkdir -p "$NODE_CACHE"
  if [[ ! -f "$NODE_CACHE/$NODE_TAR" ]]; then
    echo "Downloading Node.js ${NODE_VERSION} for darwin-${NODE_ARCH}..."
    curl -sL -o "$NODE_CACHE/$NODE_TAR" "$NODE_URL"
  fi
  echo "Extracting Node.js into package..."
  tar -xzf "$NODE_CACHE/$NODE_TAR" -C "$OUTPUT_DIR"
  # Tarball extracts to node-v20.x.x-darwin-arm64; rename to "node"
  NODE_EXTRACTED="$OUTPUT_DIR/node-v${NODE_VERSION}-darwin-${NODE_ARCH}"
  if [[ -d "$NODE_EXTRACTED" ]]; then
    mv "$NODE_EXTRACTED" "$OUTPUT_DIR/node"
  fi
  NODE_BIN="$OUTPUT_DIR/node/bin/node"
  NPM_BIN="$OUTPUT_DIR/node/bin/npm"
  if [[ ! -x "$NODE_BIN" ]]; then
    echo "Node.js not found at $OUTPUT_DIR/node/bin/node" >&2
    exit 1
  fi
  BROWSER_PLUGIN="$OUTPUT_DIR/system_plugins/homeclaw-browser"
  if [[ -f "$BROWSER_PLUGIN/package.json" ]]; then
    echo "Running npm install in system_plugins/homeclaw-browser..."
    (cd "$BROWSER_PLUGIN" && "$NPM_BIN" install --omit=dev --no-fund --no-audit)
    echo "homeclaw-browser dependencies installed (node_modules included in bundle)."
  else
    echo "system_plugins/homeclaw-browser not found, skipping npm install." >&2
  fi
elif [[ $BUILD_LAUNCHER -eq 1 ]] && [[ $BUNDLE_NODE -eq 0 ]]; then
  echo "Skipping Node.js bundle (--no-node). homeclaw-browser will need Node on PATH at run time."
fi

# ---------- Launcher app (macOS): embedded Python + venv + HomeClaw.app ----------
if [[ $BUILD_LAUNCHER -eq 1 ]]; then
  echo "Building launcher app (embedded Python + venv + HomeClaw.app)..."

  # Detect arch
  ARCH=$(uname -m)
  if [[ "$ARCH" == "arm64" ]]; then
    PYTHON_ARCH="aarch64-apple-darwin"
  else
    PYTHON_ARCH="x86_64-apple-darwin"
  fi

  PYTHON_TAR="cpython-${PYTHON_VERSION}+${PYTHON_STANDALONE_RELEASE}-${PYTHON_ARCH}-install_only.tar.gz"
  PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_STANDALONE_RELEASE}/${PYTHON_TAR}"
  CACHE_DIR="$REPO_ROOT/dist/python-standalone-cache"
  mkdir -p "$CACHE_DIR"

  if [[ ! -f "$CACHE_DIR/$PYTHON_TAR" ]]; then
    echo "Downloading standalone Python ${PYTHON_VERSION} for ${PYTHON_ARCH}..."
    curl -sL -o "$CACHE_DIR/$PYTHON_TAR" "$PYTHON_URL"
  fi
  # If download failed (e.g. 404), the "archive" may be HTML; tar would fail with "Unrecognized archive format"
  if ! tar -tzf "$CACHE_DIR/$PYTHON_TAR" >/dev/null 2>&1; then
    echo "Downloaded file is not a valid tar.gz (wrong Python version or URL?). Try removing $CACHE_DIR/$PYTHON_TAR and re-run. Expected asset: $PYTHON_TAR" >&2
    exit 1
  fi

  echo "Extracting Python into package..."
  tar -xzf "$CACHE_DIR/$PYTHON_TAR" -C "$OUTPUT_DIR"
  # Tarball has top-level "python/"; may have python/install/ with the actual install
  if [[ -d "$OUTPUT_DIR/python/install" ]]; then
    mv "$OUTPUT_DIR/python/install" "$OUTPUT_DIR/python_install"
    rm -rf "$OUTPUT_DIR/python"
    mv "$OUTPUT_DIR/python_install" "$OUTPUT_DIR/python"
  fi
  # Fallback: if python/bin/python3 missing, find any extracted dir that has it (e.g. cpython-3.11.11+...)
  if [[ ! -x "$OUTPUT_DIR/python/bin/python3" ]] && [[ ! -x "$OUTPUT_DIR/python/bin/python" ]]; then
    for d in "$OUTPUT_DIR"/*/; do
      if [[ -x "${d}bin/python3" ]] || [[ -x "${d}bin/python" ]]; then
        rm -rf "$OUTPUT_DIR/python" 2>/dev/null
        mv "$d" "$OUTPUT_DIR/python"
        break
      fi
      if [[ -d "${d}install/bin" ]] && ( [[ -x "${d}install/bin/python3" ]] || [[ -x "${d}install/bin/python" ]] ); then
        rm -rf "$OUTPUT_DIR/python" 2>/dev/null
        mv "${d}install" "$OUTPUT_DIR/python"
        rm -rf "$d"
        break
      fi
    done
  fi

  PYTHON_BIN="$OUTPUT_DIR/python/bin/python3"
  [[ ! -x "$PYTHON_BIN" ]] && PYTHON_BIN="$OUTPUT_DIR/python/bin/python"
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Standalone Python not found (expected $OUTPUT_DIR/python/bin/python3). Contents:" >&2
    ls -la "$OUTPUT_DIR/python" 2>/dev/null || true
    exit 1
  fi

  echo "Installing dependencies into bundle (pip install -r requirements.txt)..."
  # Use default PyPI index so packaging does not depend on local pip.conf (e.g. mirrors that may 403)
  "$PYTHON_BIN" -m pip install --quiet --upgrade pip
  "$PYTHON_BIN" -m pip install --quiet --index-url https://pypi.org/simple/ -r "$OUTPUT_DIR/requirements.txt"

  echo "Creating HomeClaw.app launcher..."
  APP_NAME="HomeClaw.app"
  APP_DIR="$OUTPUT_DIR/$APP_NAME"
  mkdir -p "$APP_DIR/Contents/MacOS"
  mkdir -p "$APP_DIR/Contents/Resources"

  # Move Core + config into Resources/core (launcher will run from here)
  mv "$OUTPUT_DIR/main.py" "$OUTPUT_DIR/base" "$OUTPUT_DIR/core" "$OUTPUT_DIR/llm" "$OUTPUT_DIR/memory" \
     "$OUTPUT_DIR/tools" "$OUTPUT_DIR/hybrid_router" "$OUTPUT_DIR/plugins" "$OUTPUT_DIR/channels" \
     "$OUTPUT_DIR/system_plugins" "$OUTPUT_DIR/examples" "$OUTPUT_DIR/ui" "$APP_DIR/Contents/Resources/" 2>/dev/null || true
  mv "$OUTPUT_DIR/config" "$APP_DIR/Contents/Resources/"
  # Python and companion stay in OUTPUT_DIR for the launcher to reference
  # Launcher script lives in .app; it will use relative path to Resources
  RESOURCES_REL="../Resources"
  CORE_REL="$RESOURCES_REL/core"
  PYTHON_REL="$RESOURCES_REL/../python"
  COMPANION_REL="$RESOURCES_REL/companion/homeclaw_companion.app"

  # Python, companion, and optionally Node inside the .app so the bundle is self-contained
  cp -R "$OUTPUT_DIR/python" "$APP_DIR/Contents/Resources/"
  [[ -d "$OUTPUT_DIR/companion" ]] && cp -R "$OUTPUT_DIR/companion" "$APP_DIR/Contents/Resources/"
  [[ -d "$OUTPUT_DIR/node" ]] && cp -R "$OUTPUT_DIR/node" "$APP_DIR/Contents/Resources/"
  PYTHON_REL="$RESOURCES_REL/python"
  PYTHON_BIN_APP="$APP_DIR/Contents/Resources/python/bin/python3"
  [[ -x "$APP_DIR/Contents/Resources/python/bin/python" ]] && PYTHON_BIN_APP="$APP_DIR/Contents/Resources/python/bin/python"

  # Core is already at Contents/Resources/base, core, etc. - we moved them as single dirs, so they're at Contents/Resources/base, Contents/Resources/core, ... and config at Contents/Resources/config. So "Core root" for main.py is Contents/Resources (where main.py, base, core, ... live). We need main.py at the root that has base/ and config/. So we should have put everything under Contents/Resources/core_work and set cwd there. Let me fix: Core expects to be run from a directory that contains main.py, base/, config/. So Contents/Resources should have main.py, base/, core/, config/, etc. We moved main.py, base, core, ... to Contents/Resources - so main.py is at Contents/Resources/main.py. Good. So CORE_ROOT for the launcher is Contents/Resources.
  CORE_ROOT="$APP_DIR/Contents/Resources"
  LAUNCHER_SCRIPT="$APP_DIR/Contents/MacOS/HomeClaw"
  cat > "$LAUNCHER_SCRIPT" << 'LAUNCHER'
#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOURCES="$SCRIPT_DIR/../Resources"
CORE_ROOT="$RESOURCES"
PYTHON_BIN="$RESOURCES/python/bin/python3"
[[ -x "$RESOURCES/python/bin/python" ]] && PYTHON_BIN="$RESOURCES/python/bin/python"
COMPANION_APP="$RESOURCES/companion/homeclaw_companion.app"
# So Core can start system_plugins/homeclaw-browser (node server.js) without user-installed Node
[[ -d "$RESOURCES/node/bin" ]] && export PATH="$RESOURCES/node/bin:$PATH"

# Start Core in background (cwd = Core root so config and base are found)
cd "$CORE_ROOT"
"$PYTHON_BIN" -m main start --no-open-browser &
CORE_PID=$!

# Wait for Core /ready (up to 60s)
READY_URL="http://127.0.0.1:9000/ready"
for i in {1..60}; do
  if curl -s -o /dev/null -w "%{http_code}" "$READY_URL" 2>/dev/null | grep -q 200; then
    break
  fi
  sleep 1
done

# Open Companion if present (skip when built with --no-companion)
[[ -d "$COMPANION_APP" ]] && open "$COMPANION_APP"

# Wait for Core so closing the launcher doesn't kill it immediately (optional: detach fully)
wait $CORE_PID 2>/dev/null || true
LAUNCHER
  chmod +x "$LAUNCHER_SCRIPT"

  # Info.plist for the app
  PLIST="$APP_DIR/Contents/Info.plist"
  cat > "$PLIST" << PLIST_XML
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>HomeClaw</string>
  <key>CFBundleIdentifier</key><string>com.homeclaw.app</string>
  <key>CFBundleName</key><string>HomeClaw</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
</dict>
</plist>
PLIST_XML

  # Move PACKAGE_README to bundle and leave a copy in OUTPUT_DIR
  echo "Launcher app created at $APP_DIR"
fi

# ---------- PACKAGE_README ----------
if [[ $BUILD_LAUNCHER -eq 1 ]]; then
  README_FILE="$OUTPUT_DIR/PACKAGE_README.txt"
  APP_DIR="$OUTPUT_DIR/HomeClaw.app"
  cat > "$README_FILE" << PACKAGE_README
HomeClaw — one app: run HomeClaw.app to start Core and open Companion.

MODELS (not included)
  Put your model files (e.g. .gguf) in:
    ~/HomeClaw/models
  Edit config inside the app if needed: right-click HomeClaw.app → Show Package Contents
  → Contents/Resources/config/core.yml — set model_path to ~/HomeClaw/models (or your path).

RUN
  Double-click HomeClaw.app. It will:
  1. Start HomeClaw Core (embedded Python, no install needed).
  2. Open the Companion app; set Core URL to http://127.0.0.1:9000 if prompted.

SYSTEM PLUGIN (homeclaw-browser)
  WebChat, Control UI, and browser automation are provided by system_plugins/homeclaw-browser (Node.js).
  Node.js is bundled in the app; its dependencies (npm install) are already in the bundle. If you use
  browser automation (Playwright), the first time the plugin runs it may need to install a browser;
  see the plugin docs or run "npx playwright install chromium" from the plugin folder if needed.

CONFIG
  Full config (all comments and fields) is inside the app at:
  HomeClaw.app/Contents/Resources/config/core.yml and user.yml.
  Edit as needed (LLM, ports, auth, model_path, etc.). system_plugins_auto_start and system_plugins
  in core.yml control whether homeclaw-browser starts with Core.
PACKAGE_README
else
  README_FILE="$OUTPUT_DIR/PACKAGE_README.txt"
  cat > "$README_FILE" << 'PACKAGE_README'
HomeClaw package — Core + config + Companion (folder only; no launcher).

MODELS (not included)
  Put your model files (e.g. .gguf) in:
    ~/HomeClaw/models
  Set model_path in config/core.yml to that path.

RUN CORE
  From this directory (Python 3 and deps required):
    pip install -r requirements.txt
    python -m main start

RUN COMPANION (macOS)
  Open: companion/homeclaw_companion.app
  Set Core URL to http://127.0.0.1:9000 in Settings.

HOMECLAW-BROWSER (system_plugins)
  WebChat and Control UI need system_plugins/homeclaw-browser (Node.js). Install Node.js (>=18) and run:
  cd system_plugins/homeclaw-browser && npm install
  Then ensure system_plugins_auto_start and system_plugins in config/core.yml are set so Core starts it.

CONFIG
  config/core.yml — full reference with all options and comments.
  config/user.yml — users and permissions.
PACKAGE_README
fi

echo "Wrote $README_FILE"

# ---------- Archive ----------
if [[ $CREATE_ARCHIVE -eq 1 ]]; then
  ARCHIVE_BASE="$(basename "$OUTPUT_DIR")"
  ARCHIVE_DIR="$(dirname "$OUTPUT_DIR")"
  echo "Creating archive..."
  (cd "$ARCHIVE_DIR" && tar czf "${ARCHIVE_BASE}.tar.gz" "$ARCHIVE_BASE")
  echo "Created $ARCHIVE_DIR/${ARCHIVE_BASE}.tar.gz"
fi

echo "Done. Package directory: $OUTPUT_DIR"
if [[ $BUILD_LAUNCHER -eq 1 ]]; then
  echo "Launcher app: $OUTPUT_DIR/HomeClaw.app — double-click to start Core and open Companion."
fi
