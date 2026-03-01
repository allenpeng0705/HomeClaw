#!/usr/bin/env bash
# Print the SHA256 of the GitHub source tarball for the given tag.
# Usage: ./scripts/homebrew/get-sha256.sh v1.0.0
# Use this to update the formula's sha256 when cutting a new release.

set -e
TAG="${1:-v1.0.0}"
REPO="${HOMECLAW_REPO_URL:-https://github.com/allenpeng0705/HomeClaw}"
URL="${REPO}/archive/refs/tags/${TAG}.tar.gz"
echo "Fetching: $URL" >&2
curl -sL "$URL" | shasum -a 256 | awk '{print $1}'
