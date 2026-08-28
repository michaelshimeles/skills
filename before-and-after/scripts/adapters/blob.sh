#!/bin/bash
# Custom blob storage adapter - For self-hosted or custom endpoints
#
# Usage: ./blob.sh <file>
# Output: URL to uploaded file (stdout)
#
# Environment:
#   BLOB_UPLOAD_URL    Required. URL endpoint for uploading images
#
# Notes:
#   - Expects endpoint to accept multipart form upload with "file" field
#   - Expects response to be either:
#     - Plain text URL
#     - JSON with "url" field

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

if [[ -z "$BLOB_UPLOAD_URL" ]]; then
    echo "Error: BLOB_UPLOAD_URL environment variable not set" >&2
    echo "" >&2
    echo "Set it with:" >&2
    echo "  export BLOB_UPLOAD_URL='https://your-blob-service.com/upload'" >&2
    exit 1
fi

# Upload file
RESPONSE=$(curl -s -X POST -F "file=@$FILE" "$BLOB_UPLOAD_URL")

# Try to extract URL from JSON response
URL=$(echo "$RESPONSE" | grep -o '"url"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"url"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//' || true)

# Fallback: maybe the response is just the URL
if [[ -z "$URL" ]]; then
    URL="$RESPONSE"
fi

# Validate we got a URL back
if [[ ! "$URL" =~ ^https?:// ]]; then
    echo "Error: Upload failed. Response: $RESPONSE" >&2
    exit 1
fi

echo "$URL"
