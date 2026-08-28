#!/bin/bash
# upload-and-copy.sh - Upload images via pluggable storage adapters
# Usage: ./upload-and-copy.sh <before.png> <after.png> [--markdown]
#
# Options:
#   --markdown    Generate PR markdown table and copy to clipboard
#
# Environment:
#   IMAGE_ADAPTER    Storage adapter to use (default: 0x0st)
#                    Available: 0x0st, gist, blob
#
# Adapter-specific environment variables:
#   blob:  BLOB_UPLOAD_URL - Custom upload endpoint
#
# Examples:
#   ./upload-and-copy.sh before.png after.png
#   ./upload-and-copy.sh before.png after.png --markdown
#   IMAGE_ADAPTER=gist ./upload-and-copy.sh before.png after.png --markdown

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ADAPTERS_DIR="$SCRIPT_DIR/adapters"

# Default adapter
IMAGE_ADAPTER="${IMAGE_ADAPTER:-0x0st}"

BEFORE_FILE="$1"
AFTER_FILE="$2"
shift 2 2>/dev/null || true

MARKDOWN_MODE=false

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --markdown)
            MARKDOWN_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate inputs
if [[ -z "$BEFORE_FILE" || -z "$AFTER_FILE" ]]; then
    echo "Usage: $0 <before.png> <after.png> [--markdown]"
    echo ""
    echo "Environment:"
    echo "  IMAGE_ADAPTER    Storage adapter (default: 0x0st)"
    echo "                   Available: 0x0st, gist, blob"
    exit 1
fi

if [[ ! -f "$BEFORE_FILE" ]]; then
    echo "Error: Before file not found: $BEFORE_FILE"
    exit 1
fi

if [[ ! -f "$AFTER_FILE" ]]; then
    echo "Error: After file not found: $AFTER_FILE"
    exit 1
fi

# Validate adapter exists
ADAPTER_SCRIPT="$ADAPTERS_DIR/$IMAGE_ADAPTER.sh"
if [[ ! -f "$ADAPTER_SCRIPT" ]]; then
    echo "Error: Unknown adapter: $IMAGE_ADAPTER"
    echo ""
    echo "Available adapters:"
    for adapter in "$ADAPTERS_DIR"/*.sh; do
        name=$(basename "$adapter" .sh)
        echo "  - $name"
    done
    exit 1
fi

# Upload function using adapter
upload_file() {
    local file="$1"
    local filename=$(basename "$file")

    echo "Uploading: $filename (via $IMAGE_ADAPTER)" >&2

    # Call the adapter script
    "$ADAPTER_SCRIPT" "$file"
}

# Upload both files
echo "=== Uploading Screenshots ==="
BEFORE_URL=$(upload_file "$BEFORE_FILE")
AFTER_URL=$(upload_file "$AFTER_FILE")

echo ""
echo "Before URL: $BEFORE_URL"
echo "After URL: $AFTER_URL"
echo ""

if [[ "$MARKDOWN_MODE" == "true" ]]; then
    # Generate PR markdown table (centered alignment for GitHub)
    MARKDOWN="| Before | After |
|:------:|:-----:|
| ![Before]($BEFORE_URL) | ![After]($AFTER_URL) |"

    echo "=== PR Markdown Table ==="
    echo "$MARKDOWN"
    echo ""

    # Copy to clipboard (macOS)
    if command -v pbcopy &> /dev/null; then
        echo "$MARKDOWN" | pbcopy
        echo "Markdown table copied to clipboard!"
    elif command -v xclip &> /dev/null; then
        echo "$MARKDOWN" | xclip -selection clipboard
        echo "Markdown table copied to clipboard!"
    else
        echo "(clipboard copy not available - install pbcopy or xclip)"
    fi
else
    # Copy URLs to clipboard
    URLS="Before: $BEFORE_URL
After: $AFTER_URL"

    if command -v pbcopy &> /dev/null; then
        echo "$URLS" | pbcopy
        echo "URLs copied to clipboard!"
    elif command -v xclip &> /dev/null; then
        echo "$URLS" | xclip -selection clipboard
        echo "URLs copied to clipboard!"
    else
        echo "(clipboard copy not available - install pbcopy or xclip)"
    fi
fi
