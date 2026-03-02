#!/usr/bin/env bash
# Build signal-cli for macOS from source.
# Run on a Mac. Requires: Git, JDK 17+ (Gradle). For signal-cli runtime, JRE 25 may be required; check signal-cli README.
# Optional: export JAVA_HOME=/path/to/jdk17 before running.

set -e
SIGNAL_CLI_REPO="https://github.com/AsamK/signal-cli.git"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PARENT_ROOT="$(dirname "$REPO_ROOT")"
BUILD_ROOT="${SIGNAL_CLI_BUILD_ROOT:-$PARENT_ROOT/signal-cli-build}"
SIBLING_CLONE="$PARENT_ROOT/signal-cli"
if [[ -d "$SIBLING_CLONE/.git" ]]; then
  CLONE_DIR="$SIBLING_CLONE"
else
  CLONE_DIR="$BUILD_ROOT/signal-cli"
fi
OUTPUT_TAR="$BUILD_ROOT/signal-cli-mac.tar.gz"

# Gradle requires JVM 17+
check_java() {
  local java_exe
  if [[ -n "$JAVA_HOME" && -x "$JAVA_HOME/bin/java" ]]; then
    java_exe="$JAVA_HOME/bin/java"
  else
    java_exe=$(command -v java 2>/dev/null) || true
  fi
  if [[ -z "$java_exe" ]]; then
    echo "Java not found. Install JDK 17+ (e.g. from https://adoptium.net/) and set JAVA_HOME."
    exit 1
  fi
  local ver
  ver=$("$java_exe" -version 2>&1) || true
  echo "$ver"
  if echo "$ver" | grep -qE 'version "1\.([0-9]+)'; then
    local major
    major=$(echo "$ver" | sed -nE 's/.*version "1\.([0-9]+).*/\1/p')
    if [[ -n "$major" && "$major" -lt 17 ]]; then
      echo "Gradle requires JVM 17 or later. Current is 1.$major. Set JAVA_HOME to a JDK 17+ and run again."
      exit 1
    fi
  fi
  if echo "$ver" | grep -qE 'version "([0-9]+)'; then
    local major
    major=$(echo "$ver" | sed -nE 's/.*version "([0-9]+).*/\1/p')
    if [[ -n "$major" && "$major" -lt 17 ]]; then
      echo "Gradle requires JVM 17 or later. Current is $major. Set JAVA_HOME to a JDK 17+ and run again."
      exit 1
    fi
  fi
}

check_java
echo "Build root: $BUILD_ROOT"
mkdir -p "$BUILD_ROOT"

if [[ ! -d "$CLONE_DIR/.git" ]]; then
  echo "Cloning signal-cli..."
  git clone --depth 1 "$SIGNAL_CLI_REPO" "$CLONE_DIR"
else
  echo "Repo already cloned at $CLONE_DIR; pulling latest..."
  (cd "$CLONE_DIR" && git pull --depth 1)
fi

echo "Building (installDist)..."
(cd "$CLONE_DIR" && ./gradlew installDist)

INSTALL_DIR="$CLONE_DIR/build/install/signal-cli"
if [[ ! -d "$INSTALL_DIR" ]]; then
  echo "Expected output not found: $INSTALL_DIR"
  exit 1
fi

echo "macOS build succeeded: $INSTALL_DIR"
echo "Run with: $INSTALL_DIR/bin/signal-cli -u +YOUR_NUMBER receive"

# Optional: create a tarball for distribution
if command -v tar &>/dev/null; then
  (cd "$(dirname "$INSTALL_DIR")" && tar czf "$OUTPUT_TAR" signal-cli)
  echo "Tarball: $OUTPUT_TAR"
fi
