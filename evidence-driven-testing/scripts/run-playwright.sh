#!/usr/bin/env bash
# Run a self-contained capture script with dependencies outside the project.
set -euo pipefail

if [[ $# -lt 1 || ! -f "$1" ]]; then
  echo "Usage: bash run-playwright.sh /path/to/record.mjs [script arguments...]" >&2
  exit 1
fi

CAPTURE_SCRIPT="$1"
shift
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CAPTURE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/skill-playwright.XXXXXXXX")
trap 'rm -rf -- "$CAPTURE_DIR"' EXIT

# ESM resolves imports beside the script, independently of the working directory.
cp -- "$CAPTURE_SCRIPT" "$CAPTURE_DIR/record.mjs"
cp -- "$SCRIPT_DIR/playwright/package.json" "$SCRIPT_DIR/playwright/package-lock.json" "$CAPTURE_DIR/"
npm ci --prefix "$CAPTURE_DIR" --no-audit --no-fund --ignore-scripts >&2
"$CAPTURE_DIR/node_modules/.bin/playwright" install chromium >&2
node "$CAPTURE_DIR/record.mjs" "$@"
