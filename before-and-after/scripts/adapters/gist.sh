#!/bin/bash
# GitHub Gist adapter - Upload images via gh CLI
#
# Usage: ./gist.sh <file>
# Output: Raw URL to uploaded file (stdout)
#
# Requirements:
#   - gh CLI installed and authenticated
#
# Notes:
#   - Creates a public gist for each upload
#   - Files persist indefinitely
#   - Requires GitHub authentication

set -e

FILE="$1"

if [[ -z "$FILE" ]]; then
    echo "Usage: $0 <file>" >&2
    exit 1
fi

if [[ ! -f "$FILE" ]]; then
    echo "Error: File not found: $FILE" >&2
    exit 1
fi

# Check gh is available
if ! command -v gh &> /dev/null; then
    echo "Error: gh CLI not found. Install from https://cli.github.com" >&2
    exit 1
fi

# Create gist and capture output
GIST_OUTPUT=$(gh gist create "$FILE" --public 2>&1)

# Extract the gist URL from output
GIST_URL=$(echo "$GIST_OUTPUT" | grep -o 'https://gist.github.com/[^ ]*' | head -1)

if [[ -z "$GIST_URL" ]]; then
    echo "Error: Failed to create gist. Output: $GIST_OUTPUT" >&2
    exit 1
fi

# Convert to raw URL
# Format: https://gist.github.com/user/id -> https://gist.githubusercontent.com/user/id/raw/filename
GIST_ID=$(echo "$GIST_URL" | sed 's|.*/||')
FILENAME=$(basename "$FILE")

# Get the raw URL via gh api
RAW_URL=$(gh api "gists/$GIST_ID" --jq ".files[\"$FILENAME\"].raw_url")

if [[ -z "$RAW_URL" ]]; then
    echo "Error: Could not get raw URL for gist" >&2
    exit 1
fi

echo "$RAW_URL"
