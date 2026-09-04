#!/usr/bin/env bash
# fix-video-evidence - one-time Cloudflare R2 setup wizard.
#
# Walks you through creating a Cloudflare R2 bucket + API token, tests
# an actual upload, and prints the four R2_* env-var exports for your
# shell profile. After running this once, PR_VIDEO_UPLOAD=r2 in your
# environment makes attach-to-pr.sh auto-upload every future PR video.
#
# Cost: Cloudflare R2 free tier is 10GB storage + 1M Class A ops/month.
# No card required for sign-up. Videos this skill uploads are ~1-5MB each,
# so the free tier realistically covers thousands of PRs before you hit it.

set -euo pipefail

blue () { printf "\033[1;34m%s\033[0m\n" "$*"; }
green () { printf "\033[1;32m%s\033[0m\n" "$*"; }
red () { printf "\033[1;31m%s\033[0m\n" "$*"; }
gray () { printf "\033[0;37m%s\033[0m\n" "$*"; }

blue "fix-video-evidence - Cloudflare R2 setup wizard"
gray "One-time setup that lets attach-to-pr.sh auto-upload .webm files instead of asking you to drag them into the PR by hand."
echo ""

here="$(cd "$(dirname "$0")" && pwd)"

# Step 0: check if all four env vars are already set - if so, just test upload
already_set=1
for var in R2_BUCKET R2_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
  if [ -z "${!var:-}" ]; then already_set=0; break; fi
done

if [ "$already_set" = "1" ]; then
  green "All four R2_* env vars are already set in this shell. Skipping wizard, testing the upload path directly..."
else
  gray "One or more R2_* env vars are missing. Starting the guided setup."
  echo ""

  blue "Step 1/5: Cloudflare account + R2 enabled"
  echo "  You need a Cloudflare account with R2 enabled. Free tier (10GB + 1M ops/mo) is more than enough."
  echo "    - Sign up:    https://dash.cloudflare.com/sign-up"
  echo "    - Enable R2:  https://dash.cloudflare.com/?to=/:account/r2 (click 'Enable R2'; no card required for free tier)"
  read -p "  Ready? Press Enter when you have a Cloudflare account and R2 is enabled. "
  echo ""

  blue "Step 2/5: Create the bucket"
  echo "  In the R2 dashboard, click 'Create bucket'."
  echo "  Suggested name pattern: pr-video-evidence-<your-github-username> (must be unique across your R2 account)."
  read -p "  Bucket name you created: " R2_BUCKET
  export R2_BUCKET
  echo ""

  blue "Step 3/5: Enable public access (so PR video links load)"
  echo "  Open the bucket -> Settings -> Public access -> Allow Access -> confirm."
  echo "  Cloudflare shows a public URL like  https://pub-<hash>.r2.dev  - copy it."
  echo "  (Or configure a custom domain if you already have one; either works.)"
  read -p "  Public base URL (e.g. https://pub-xxxx.r2.dev  OR  https://cdn.yourdomain.com): " R2_PUBLIC_BASE
  export R2_PUBLIC_BASE
  echo ""

  blue "Step 4/5: Cloudflare Account ID"
  echo "  In the Cloudflare dashboard, look at the right sidebar - 'Account ID'. Copy it."
  read -p "  Cloudflare Account ID: " R2_ACCOUNT_ID
  export R2_ACCOUNT_ID
  echo ""

  blue "Step 5/5: R2 API token (Access Key + Secret)"
  echo "  URL: https://dash.cloudflare.com/?to=/:account/r2/api-tokens -> 'Create API token'."
  echo "  Permissions: 'Object Read & Write'."
  echo "  Scope: 'Apply to specific buckets only' -> pick '$R2_BUCKET'."
  echo "  After creating, Cloudflare shows the Access Key ID + Secret Access Key ONCE. Copy both."
  read -p "  R2 Access Key ID: " R2_ACCESS_KEY_ID
  read -s -p "  R2 Secret Access Key (hidden): " R2_SECRET_ACCESS_KEY
  echo ""
  export R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY
  echo ""
fi

# Test upload with a tiny dummy file
blue "Testing an actual upload to verify all four values..."
tmp=$(mktemp -t fvd-r2-test.XXXXXX)
echo "fix-video-evidence R2 test $(date -u +%FT%TZ)" > "$tmp"

if bash "$here/upload-r2.sh" "$tmp" "_setup-check.txt" >/dev/null 2>&1; then
  green "OK - test upload succeeded. R2 is wired up correctly."
else
  red "FAIL - test upload failed. One of the env vars is wrong. Re-run this wizard, or check upload-r2.sh output:"
  echo ""
  bash "$here/upload-r2.sh" "$tmp" "_setup-check.txt" || true
  rm -f "$tmp"
  exit 1
fi
rm -f "$tmp"
echo ""

# Print exports for shell profile
blue "Add these lines to your shell profile (~/.zshrc or ~/.bashrc) so R2 is on for all future sessions:"
cat <<EOF

# fix-video-evidence - auto-upload PR videos to R2
export PR_VIDEO_UPLOAD=r2
export R2_BUCKET="$R2_BUCKET"
export R2_ACCOUNT_ID="$R2_ACCOUNT_ID"
export R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
EOF

if [ -n "${R2_PUBLIC_BASE:-}" ]; then
  echo "export R2_PUBLIC_BASE=\"$R2_PUBLIC_BASE\""
fi

echo ""
green "Done. Copy the block above into your shell profile, then reload (source ~/.zshrc)."
gray "From here on, every fix-video-evidence run auto-uploads the .webm files and inlines a video-tag link in the PR body. No drag-drop."
