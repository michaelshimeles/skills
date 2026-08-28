#!/bin/bash
# capture.sh - Core screenshot capture using agent-browser
# Usage: ./capture.sh <url> <output.png> [--full] [--element <selector>]
#
# Options:
#   --full              Full page screenshot (viewport 1500x1000)
#   --element <sel>     Element screenshot (auto-sized to element bounds)
#
# Examples:
#   ./capture.sh "http://localhost:3000" ~/Downloads/screenshot.png --full
#   ./capture.sh "http://localhost:3000" ~/Downloads/button.png --element ".btn-primary"

set -e

URL="$1"
OUTPUT="$2"
shift 2

# Default to full page
MODE="full"
SELECTOR=""

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            MODE="full"
            shift
            ;;
        --element)
            MODE="element"
            SELECTOR="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$URL" || -z "$OUTPUT" ]]; then
    echo "Usage: $0 <url> <output.png> [--full] [--element <selector>]"
    exit 1
fi

# Ensure output directory exists
mkdir -p "$(dirname "$OUTPUT")"

echo "Opening: $URL"
agent-browser:open "$URL"

echo "Waiting for page load..."
agent-browser:wait --load networkidle

if [[ "$MODE" == "element" && -n "$SELECTOR" ]]; then
    echo "Capturing element: $SELECTOR"
    agent-browser:screenshot --selector "$SELECTOR" --output "$OUTPUT"
else
    echo "Capturing full page (1500x1000)"
    agent-browser:screenshot --viewport 1500x1000 --output "$OUTPUT"
fi

echo "Screenshot saved: $OUTPUT"
