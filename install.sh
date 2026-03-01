#!/usr/bin/env bash
# HomeClaw install script for macOS and Linux.
# Run from project root (existing clone) or from a parent directory (script will clone).
# Steps: Python (3.9+) -> Node.js -> [clone if needed] -> pip install -> llama.cpp -> GGUF/Ollama instructions -> open Portal.

set -e
REPO_URL="${HOMECLAW_REPO_URL:-https://github.com/allenpeng0705/HomeClaw.git}"
PORTAL_URL="http://127.0.0.1:18472"

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
      echo "Cloning HomeClaw into $CLONE_DIR ..."
      if ! git clone "$REPO_URL" "$CLONE_DIR" 2>&1; then
        echo "Error: git clone failed. Check network, repo URL ($REPO_URL), and that you have git installed."
        exit 1
      fi
      ROOT="$PWD/$CLONE_DIR"
      cd "$ROOT"
    fi
  fi
fi
if [ "$IN_REPO" = 0 ] && [ -d "$CLONE_DIR" ]; then
  cd "$ROOT"
fi

# ----- Step 1: Python 3.9+ -----
echo ""
echo "=== Step 1: Python ==="
PYTHON=""
for p in python3.12 python3.11 python3.10 python3.9 python3; do
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

# ----- Step 3: already done if IN_REPO -----
# (clone was done above if needed)

# ----- Step 5: pip install -r requirements.txt -----
echo ""
echo "=== Step 5: Python dependencies ==="
cd "$ROOT"
if [ -d ".venv" ]; then
  echo "Using existing .venv"
  # shellcheck source=/dev/null
  . .venv/bin/activate 2>/dev/null || true
fi
"$PYTHON" -m pip install --quiet -r requirements.txt
echo "OK: requirements installed"

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
"$PYTHON" -m main portal --no-open-browser &
PORTAL_PID=$!
sleep 3
OS="$(uname -s)"
if [ "$OS" = "Darwin" ]; then
  open "$PORTAL_URL" 2>/dev/null || true
elif [ "$OS" = "Linux" ]; then
  xdg-open "$PORTAL_URL" 2>/dev/null || true
fi
echo "Portal running (PID $PORTAL_PID). To stop: kill $PORTAL_PID"
echo "To run Portal again later: cd $ROOT && $PYTHON -m main portal"
