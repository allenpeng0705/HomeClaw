#!/usr/bin/env bash
# HomeClaw install script for macOS and Linux.
# Run from project root (existing clone) or from a parent directory (script will clone).
# Do NOT use sudo. Run as your normal user:   bash install.sh   (or   chmod +x install.sh   then   ./install.sh).
# If you see "Permission denied", use   bash install.sh   — it does not require the file to be executable.
# Steps: Python (3.9+) -> Node.js -> tsx -> ClawHub -> [clone if needed] -> VMPrint -> pip install -> Cognee deps (cognee in vendor/) -> document stack -> MemOS (vendor/memos) -> llama.cpp -> GGUF/Ollama -> open Portal.

set -e
REPO_URL="${HOMECLAW_REPO_URL:-https://github.com/allenpeng0705/HomeClaw.git}"
PORTAL_URL="http://127.0.0.1:18472"

echo "=============================================="
echo "  HomeClaw Installer (macOS / Linux)"
echo "=============================================="
echo ""
if [ -n "$SUDO_USER" ]; then
  echo "Note: You ran this with sudo. Prefer running without sudo:  ./install.sh  or  bash install.sh"
  echo "      (Homebrew and pip work as your user. Use full path if you must use sudo: sudo $(pwd)/install.sh)"
  echo ""
fi

# Resolve project root: script may be at project root or we clone into ./HomeClaw
SCRIPT_DIR=""
if [ -n "$BASH_SOURCE" ] && [ -f "$BASH_SOURCE" ]; then
  SCRIPT_DIR="$(cd "$(dirname "$BASH_SOURCE")" && pwd)"
fi
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/main.py" ] && [ -f "$SCRIPT_DIR/requirements.txt" ]; then
  ROOT="$SCRIPT_DIR"
  IN_REPO=1
  echo "Using existing HomeClaw repo at: $ROOT"
else
  # Not in repo: clone into ./HomeClaw (run from parent dir, e.g. cd ~/projects && bash install.sh)
  if [ -f "main.py" ] && [ -f "requirements.txt" ]; then
    ROOT="$PWD"
    IN_REPO=1
    echo "Using existing HomeClaw repo at: $ROOT"
  else
    IN_REPO=0
    CLONE_DIR="HomeClaw"
    if [ -d "$CLONE_DIR" ] && [ -f "$CLONE_DIR/main.py" ]; then
      ROOT="$PWD/$CLONE_DIR"
      IN_REPO=1
      echo "Using existing clone at: $ROOT"
    else
      echo "Cloning HomeClaw into $CLONE_DIR from GitHub (shallow clone, --depth 1)..."
      echo "  Repository: $REPO_URL"
      echo "  This may take 1-3 minutes; progress will stream below."
      echo ""
      if ! git clone --progress --depth 1 "$REPO_URL" "$CLONE_DIR" 2>&1; then
        echo "Error: git clone failed. Check network, repo URL ($REPO_URL), and that you have git installed."
        exit 1
      fi
      echo "Clone complete. Continuing with setup..."
      ROOT="$PWD/$CLONE_DIR"
      cd "$ROOT"
    fi
  fi
fi
if [ "$IN_REPO" = 0 ] && [ -d "$CLONE_DIR" ]; then
  cd "$ROOT"
fi
# Ensure we are in project root for all following steps (venv, paths, etc.)
if [ -z "${ROOT:-}" ] || [ ! -d "$ROOT" ]; then
  echo "Error: could not determine project root."
  exit 1
fi
cd "$ROOT"
echo "Working directory: $ROOT"
echo ""

# ----- Step 1: Python 3.9+ -----
echo ""
echo "=== Step 1: Python ==="
PYTHON=""
for p in python3.12 python3.11 python3.10 python3.9 python3 python; do
  if command -v "$p" >/dev/null 2>&1; then
    if "$p" -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
      PYTHON="$p"
      break
    fi
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.9+ not found. Attempting to install..."
  OS="$(uname -s)"
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      brew install python@3.11 || true
      PYTHON="python3.11"
      if ! command -v "$PYTHON" >/dev/null 2>&1; then
        PYTHON="python3"
      fi
    fi
  elif [ "$OS" = "Linux" ]; then
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update -qq && sudo apt-get install -y python3.11 python3.11-venv python3-pip 2>/dev/null || \
      sudo apt-get install -y python3 python3-venv python3-pip 2>/dev/null || true
      PYTHON="python3"
    fi
  fi
  if [ -z "$PYTHON" ] || ! "$PYTHON" -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
    echo "Please install Python 3.9 or newer from https://www.python.org or your package manager, then re-run this script."
    exit 1
  fi
fi
echo "OK: Python $($PYTHON --version 2>&1)"

# ----- Step 2: Node.js -----
echo ""
echo "=== Step 2: Node.js ==="
if command -v node >/dev/null 2>&1; then
  echo "OK: Node $(node --version 2>&1)"
else
  echo "Node.js not found. Attempting to install..."
  OS="$(uname -s)"
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      brew install node 2>/dev/null || true
    fi
  elif [ "$OS" = "Linux" ]; then
    if command -v apt-get >/dev/null 2>&1; then
      (curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs) 2>/dev/null || \
      sudo apt-get install -y nodejs npm 2>/dev/null || true
    fi
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo "Node.js could not be installed automatically. Install from https://nodejs.org and re-run if you need it (e.g. for browser plugin). Continuing..."
  else
    echo "OK: Node $(node --version 2>&1)"
  fi
fi

# ----- Step 2b: TypeScript runner (for .ts skill scripts) -----
# Skills can use .js (node) or .ts (tsx/ts-node). Node is required for .js; tsx or ts-node for .ts.
echo ""
echo "=== Step 2b: TypeScript runner (for .ts skill scripts) ==="
if command -v node >/dev/null 2>&1; then
  if command -v tsx >/dev/null 2>&1; then
    echo "OK: tsx $(tsx --version 2>&1) (for .ts skills)"
  elif command -v ts-node >/dev/null 2>&1; then
    echo "OK: ts-node (for .ts skills)"
  else
    echo "tsx/ts-node not found. Installing tsx (recommended for running TypeScript skill scripts)..."
    if npm install -g tsx 2>/dev/null; then
      echo "OK: tsx installed (for .ts skills)"
    else
      echo "To run TypeScript (.ts) skill scripts later, install one of: npm install -g tsx  (recommended), or  npm install -g ts-node"
    fi
  fi
else
  echo "Node.js not available; skipping. For .ts skills you need: node on PATH, then npm install -g tsx (or ts-node)."
fi

# ----- Step 2c: ClawHub CLI (for skill search/install from Portal and Companion) -----
echo ""
echo "=== Step 2c: ClawHub CLI (skill search/install) ==="
if command -v clawhub >/dev/null 2>&1; then
  echo "OK: clawhub already on PATH"
else
  if command -v npm >/dev/null 2>&1; then
    echo "Installing ClawHub CLI (npm i -g clawhub)..."
    if npm install -g clawhub 2>/dev/null; then
      echo "OK: clawhub installed (for skill search/install from Portal and Companion)"
    else
      echo "ClawHub CLI install failed or needs sudo. To install later: npm i -g clawhub"
    fi
  else
    echo "npm not available; skipping. For skill search/install from Companion/Portal, install Node.js then: npm i -g clawhub"
  fi
fi

# ----- Step 3: already done if IN_REPO -----
# (clone was done above if needed)

# ----- Step 4b: VMPrint (Markdown → PDF tool) -----
echo ""
echo "=== Step 4b: VMPrint (Markdown to PDF) ==="
VMPRINT_DIR="$ROOT/tools/vmprint"
VMPRINT_MAIN="$ROOT/tools/vmprint-main"
# If user downloaded GitHub ZIP, folder is vmprint-main; rename to vmprint so config path works
if [ -d "$VMPRINT_MAIN" ] && [ ! -d "$VMPRINT_DIR" ]; then
  echo "Renaming tools/vmprint-main to tools/vmprint ..."
  mv "$VMPRINT_MAIN" "$VMPRINT_DIR" 2>/dev/null || { echo "Warning: could not rename vmprint-main to vmprint (e.g. permission). You can rename manually."; true; }
fi
if [ -d "$VMPRINT_DIR/draft2final" ] && [ -f "$VMPRINT_DIR/package.json" ]; then
  echo "OK: VMPrint already at tools/vmprint"
else
  if command -v git >/dev/null 2>&1; then
    mkdir -p "$ROOT/tools"
    if [ -d "$VMPRINT_DIR/.git" ]; then
      echo "Updating VMPrint at tools/vmprint ..."
      (cd "$VMPRINT_DIR" && git pull --quiet 2>/dev/null || true)
    else
      echo "Cloning VMPrint from GitHub into tools/vmprint (optional Markdown-to-PDF tool)..."
      git clone --progress --depth 1 https://github.com/cosmiciron/vmprint.git "$VMPRINT_DIR" 2>&1 || true
    fi
    if [ -d "$VMPRINT_DIR/draft2final" ] && command -v npm >/dev/null 2>&1; then
      echo "Installing VMPrint dependencies (npm install) ..."
      (cd "$VMPRINT_DIR" && npm install --silent 2>/dev/null) || true
      if [ -d "$VMPRINT_DIR/node_modules" ]; then
        echo "Building VMPrint workspaces (transmuters then draft2final) ..."
        (cd "$VMPRINT_DIR" && npm run build --workspace=@vmprint/transmuter-mkd-mkd --workspace=@vmprint/transmuter-mkd-academic --workspace=@vmprint/transmuter-mkd-literature --workspace=@vmprint/transmuter-mkd-manuscript --workspace=@vmprint/transmuter-mkd-screenplay 2>/dev/null) || true
        (cd "$VMPRINT_DIR" && npm run build --workspace=draft2final 2>/dev/null) || true
        echo "OK: VMPrint installed at tools/vmprint"
      else
        echo "VMPrint clone present; run manually: cd $VMPRINT_DIR && npm install"
      fi
    elif [ -d "$VMPRINT_DIR/draft2final" ]; then
      echo "VMPrint cloned; Node/npm not found. Install Node from https://nodejs.org then run: cd $VMPRINT_DIR && npm install"
    else
      echo "VMPrint clone skipped (git failed or no network). Markdown-to-PDF will use pandoc/weasyprint if available."
    fi
  else
    echo "VMPrint skipped (git not found). Markdown-to-PDF will use pandoc or weasyprint if available."
  fi
fi

# ----- Step 5: pip install -r requirements.txt -----
echo ""
echo "=== Step 5: Python dependencies ==="
cd "$ROOT"
if [ -d ".venv" ]; then
  echo "Using existing .venv"
  # shellcheck source=/dev/null
  . .venv/bin/activate 2>/dev/null || true
fi
# Upgrade pip first (old pip can cause 403 with some mirrors)
"$PYTHON" -m pip install --quiet --upgrade pip 2>/dev/null || true
if ! "$PYTHON" -m pip install --quiet -r requirements.txt; then
  echo "First attempt failed. Retrying automatically with official PyPI (ignoring mirror config)..."
  echo "This may take a few minutes (downloading from pypi.org). You will see progress below."
  # Unset mirror env so -i is the only index (pip.conf or PIP_INDEX_URL may point to a mirror that returned 403)
  # Run without --quiet so user sees download/install progress and knows it is not stuck
  if ! PIP_INDEX_URL= PIP_EXTRA_INDEX_URL= "$PYTHON" -m pip install -r requirements.txt -i https://pypi.org/simple; then
    echo "Error: pip install failed."
    echo "  If you saw 403 Forbidden: your pip index (e.g. Tsinghua mirror) may be blocking. Try:"
    echo "    $PYTHON -m pip install -r requirements.txt -i https://pypi.org/simple"
    echo "  If you see permission errors: $PYTHON -m pip install --user -r requirements.txt"
    exit 1
  fi
fi
echo "OK: requirements installed"

# ----- Step 5b: Cognee dependencies (for memory backend) -----
# Cognee is the default memory backend. Cognee is vendored in vendor/cognee; we only
# install its dependencies here. Do not run "pip install cognee".
echo ""
echo "=== Step 5b: Cognee dependencies (memory backend) ==="
if [ -f "$ROOT/requirements-cognee-deps.txt" ]; then
  echo "Installing Cognee dependencies (instructor, etc.)..."
  if PIP_INDEX_URL= PIP_EXTRA_INDEX_URL= "$PYTHON" -m pip install -r "$ROOT/requirements-cognee-deps.txt" -i https://pypi.org/simple; then
    echo "OK: Cognee dependencies installed"
  else
    echo "Cognee deps install failed or skipped. To retry: $PYTHON -m pip install -r requirements-cognee-deps.txt -i https://pypi.org/simple"
  fi
else
  echo "requirements-cognee-deps.txt not found; skipping."
fi

# ----- Step 5c: Document stack (unstructured, opencv) — separate to avoid backtracking -----
echo ""
echo "=== Step 5c: Document support (document_read: PDF, Word, images) ==="
if [ -f "$ROOT/requirements-document.txt" ]; then
  echo "Installing document stack (pinned versions)..."
  if PIP_INDEX_URL= PIP_EXTRA_INDEX_URL= "$PYTHON" -m pip install -r "$ROOT/requirements-document.txt" -i https://pypi.org/simple; then
    echo "OK: document stack installed"
  else
    echo "Document stack install failed or skipped. To install later: $PYTHON -m pip install -r requirements-document.txt -i https://pypi.org/simple"
  fi
else
  echo "requirements-document.txt not found; skipping."
fi

# ----- Step 5d: MemOS (memory backend, optional) -----
# MemOS is a built-in memory backend (like Cognee). Clone MemOS app into vendor/memos, add standalone server script, npm install.
# When memory_backend is memos or composite, Core can auto-start the MemOS server if memos.url is local and memos.auto_start is true.
echo ""
echo "=== Step 5d: MemOS (memory backend) ==="
MEMOS_DIR="$ROOT/vendor/memos"
if [ -f "$MEMOS_DIR/server-standalone.ts" ]; then
  if [ ! -d "$MEMOS_DIR/src" ] || [ ! -f "$MEMOS_DIR/package.json" ]; then
    echo "MemOS app source missing in vendor/memos. Cloning MemOS and copying app..."
    if command -v git >/dev/null 2>&1; then
      MEMOS_TMP="${ROOT:?}/.tmp_memos_clone"
      [ ! -d "$MEMOS_TMP" ] || rm -rf "$MEMOS_TMP"
      if git clone --depth 1 https://github.com/MemTensor/MemOS.git "$MEMOS_TMP" 2>/dev/null; then
        MEMOS_APP="$MEMOS_TMP/apps/memos-local-openclaw"
        if [ -d "$MEMOS_APP" ]; then
          for f in "$MEMOS_APP"/*; do
            [ -e "$f" ] || continue
            fn="$(basename "$f")"
            if [ "$fn" = "server-standalone.ts" ] || [ "$fn" = "HOMECLAW-STANDALONE.md" ] || [ "$fn" = "memos-standalone.json.example" ]; then
              continue
            fi
            cp -R "$f" "$MEMOS_DIR/" 2>/dev/null || true
          done
          echo "MemOS app copied to vendor/memos"
        fi
        rm -rf "$MEMOS_TMP"
      else
        echo "MemOS clone failed (network or repo). To use MemOS later: git clone https://github.com/MemTensor/MemOS.git /tmp/MemOS && cp -r /tmp/MemOS/apps/memos-local-openclaw/* $MEMOS_DIR/"
      fi
    else
      echo "git not found; skipping MemOS app copy. See vendor/memos/HOMECLAW-STANDALONE.md for manual setup."
    fi
  fi
  if [ -f "$MEMOS_DIR/package.json" ] && command -v npm >/dev/null 2>&1; then
    if ! grep -q '"standalone"' "$MEMOS_DIR/package.json" 2>/dev/null; then
      if command -v node >/dev/null 2>&1; then
        MEMOS_DIR="$MEMOS_DIR" node -e '
        const fs = require("fs");
        const path = require("path");
        const d = process.env.MEMOS_DIR;
        if (!d) process.exit(1);
        const p = path.join(d, "package.json");
        try {
          const j = JSON.parse(fs.readFileSync(p, "utf8"));
          j.scripts = j.scripts || {};
          j.scripts.standalone = "tsx server-standalone.ts";
          fs.writeFileSync(p, JSON.stringify(j, null, 2));
        } catch (e) { process.exit(1); }
        ' 2>/dev/null && echo "Added standalone script to MemOS package.json" || true
      fi
    fi
    echo "Installing MemOS dependencies (npm install in vendor/memos)..."
    (cd "$MEMOS_DIR" && npm install --silent 2>/dev/null) || true
    if [ -d "$MEMOS_DIR/node_modules" ]; then
      echo "OK: MemOS installed at vendor/memos (run automatically with Core when memory_backend is memos or composite)"
    else
      echo "MemOS npm install failed or skipped. To retry: cd $MEMOS_DIR && npm install"
    fi
  elif [ ! -f "$MEMOS_DIR/package.json" ]; then
    echo "MemOS package.json missing; run Step 5d again after copying MemOS app (see vendor/memos/HOMECLAW-STANDALONE.md)"
  else
    echo "npm not found; skipping MemOS dependencies. Install Node.js then: cd $MEMOS_DIR && npm install"
  fi
else
  echo "vendor/memos/server-standalone.ts not found; skipping MemOS (optional memory backend)"
fi

# ----- Step 6a: llama.cpp -----
echo ""
echo "=== Step 6a: llama.cpp ==="
LLAMA_OK=0
if command -v llama-server >/dev/null 2>&1 || command -v llama-server.exe >/dev/null 2>&1; then
  echo "OK: llama-server already on PATH"
  LLAMA_OK=1
else
  OS="$(uname -s)"
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      if brew install llama.cpp 2>/dev/null; then
        echo "OK: llama.cpp installed via Homebrew"
        LLAMA_OK=1
      fi
    fi
    [ "$LLAMA_OK" = 0 ] && command -v port >/dev/null 2>&1 && sudo port install llama.cpp 2>/dev/null && LLAMA_OK=1
  elif [ "$OS" = "Linux" ]; then
    if command -v brew >/dev/null 2>&1; then
      if brew install llama.cpp 2>/dev/null; then
        echo "OK: llama.cpp installed via Homebrew"
        LLAMA_OK=1
      fi
    fi
  fi
fi
if [ "$LLAMA_OK" = 0 ]; then
  echo "llama.cpp could not be installed via command line. You can use Method A — Copy binary into project:"
  echo "  Download the executable for your platform from https://github.com/ggml-org/llama.cpp/releases"
  echo "  (e.g. llama-b...-bin-macos-arm64.tar.gz for Mac Apple Silicon, llama-b...-bin-win-cuda-12.4-x64.zip for Windows CUDA)."
  echo "  Unzip and copy llama-server (or llama-server.exe on Windows) into llama.cpp-master/<platform>/ in this repo"
  echo "  (mac, win_cpu, win_cuda, linux_cpu, or linux_cuda). See llama.cpp-master/README.md for folder layout."
  echo "  Install via package manager: Windows: winget install llama.cpp; Mac/Linux: brew install llama.cpp"
fi

# ----- Step 6b: GGUF / Ollama instructions -----
echo ""
echo "=== Step 6b: GGUF models / Ollama ==="
echo "Local GGUF models are used by llama.cpp. To add more:"
echo "  Download GGUF models from Hugging Face (huggingface.co)."
echo "  In China you can use ModelScope (modelscope.cn) or HF Mirror (https://hf-mirror.com/)."
echo "  Put .gguf files in the models folder and add entries in config/llm.yml under local_models with path set to the filename (e.g. model.gguf)."
echo ""
echo "Alternatively use Ollama: install from https://ollama.com then run: python -m main ollama pull <model> and set main_llm via Portal or config."

# ----- Step 7: Done; open Portal -----
echo ""
echo "=== Installation complete ==="
echo "Starting Portal and opening browser at $PORTAL_URL ..."
cd "$ROOT"
# Use nohup so Portal keeps running after the script exits (avoids SIGHUP when terminal closes)
nohup "$PYTHON" -m main portal --no-open-browser </dev/null >>/dev/null 2>&1 &
PORTAL_PID=$!
sleep 3
OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
  open "$PORTAL_URL" 2>/dev/null || true
elif [ "$OS" = "Linux" ]; then
  xdg-open "$PORTAL_URL" 2>/dev/null || true
fi
echo "Portal running (PID $PORTAL_PID). To stop: kill $PORTAL_PID"
echo ""
echo "--- Next steps ---"
echo "  1. In Portal ($PORTAL_URL): create admin account, choose model, add users, start Core."
echo "  2. Check setup: cd $ROOT && $PYTHON -m main doctor"
echo "  3. Start Core: cd $ROOT && $PYTHON -m main start"
echo "  4. Run Portal again: cd $ROOT && $PYTHON -m main portal"
echo ""
echo "Docs: https://github.com/allenpeng0705/HomeClaw"
