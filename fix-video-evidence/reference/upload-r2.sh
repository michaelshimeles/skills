#!/usr/bin/env bash
# fix-video-evidence — upload one .webm to a Cloudflare R2 bucket via the S3-compatible API.
#
# Portable: reads bucket/creds from env only. NEVER hardcodes a bucket name.
#
# Required env:
#   R2_BUCKET             the R2 bucket name
#   R2_ACCOUNT_ID         Cloudflare account id (for the R2 S3 endpoint)
#   R2_ACCESS_KEY_ID      R2 access key
#   R2_SECRET_ACCESS_KEY  R2 secret
# Optional:
#   R2_PUBLIC_BASE        public URL prefix for the uploaded object.
#                         If unset, prints the r2.dev URL (works only if the bucket
#                         has public dev access enabled). Set this to your CDN.
#
# Usage:  upload-r2.sh <local-file> <object-key>
# Echoes: the public URL for the uploaded object (stdout, one line).

set -euo pipefail

file="${1:?missing local file path}"
key="${2:?missing object key (e.g. pr-evidence/repo-42-before.webm)}"

for var in R2_BUCKET R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
  if [ -z "${!var:-}" ]; then
    echo "upload-r2.sh: missing env $var" >&2
    exit 2
  fi
done

if ! command -v aws >/dev/null 2>&1; then
  echo "upload-r2.sh: aws CLI not found — install with 'brew install awscli' (or use 'wrangler r2 object put' instead)" >&2
  exit 3
fi

if [ ! -f "$file" ]; then
  echo "upload-r2.sh: file not found: $file" >&2
  exit 4
fi

endpoint="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
AWS_DEFAULT_REGION=auto \
aws s3 cp "$file" "s3://${R2_BUCKET}/${key}" \
  --endpoint-url "$endpoint" \
  --content-type video/webm \
  --only-show-errors >&2

if [ -n "${R2_PUBLIC_BASE:-}" ]; then
  echo "${R2_PUBLIC_BASE%/}/${key}"
else
  # Bucket-level r2.dev URL. Works only if public dev access is on for the bucket.
  # Real deployments should set R2_PUBLIC_BASE to a CDN hostname.
  echo "https://pub-${R2_ACCOUNT_ID}.r2.dev/${key}"
fi
