#!/usr/bin/env bash
# fix-video-evidence — attach the two .webm files to the PR.
#
# Two modes:
#   PORTABLE (default)         — prints a markdown block for the user to paste
#                                into a PR comment and drag-and-drop the .webm on to.
#   AUTO-UPLOAD (PR_VIDEO_UPLOAD=r2)
#                              — uploads via reference/upload-r2.sh, then appends
#                                CDN-linked markdown to the PR body via `gh pr edit`.
#
# If PR_VIDEO_UPLOAD=r2 but R2_* env vars are missing, falls back to portable
# with a warning — never silently drops the evidence.
#
# Usage:  attach-to-pr.sh <pr-number>
#
# Expects filenames `<repo>-<pr>-before.webm` and `<repo>-<pr>-after.webm`
# in .videos/ (produced by the Playwright template's afterAll hook).

set -euo pipefail

pr="${1:?usage: attach-to-pr.sh <pr-number>}"
repo="$(basename "$(git rev-parse --show-toplevel)")"
here="$(cd "$(dirname "$0")" && pwd)"

before=".videos/${repo}-${pr}-before.webm"
after=".videos/${repo}-${pr}-after.webm"

for f in "$before" "$after"; do
  if [ ! -f "$f" ]; then
    echo "attach-to-pr.sh: missing $f — run the Playwright script for both PHASE=before and PHASE=after first" >&2
    exit 1
  fi
done

size_ok () {   # $1=file — echo "OK" or a warning
  local bytes
  bytes=$(stat -f%z "$1" 2>/dev/null || stat -c%s "$1")
  if [ "$bytes" -gt 10485760 ]; then
    echo "WARN: $1 is $(( bytes / 1024 / 1024 ))MB — GitHub's comment-upload cap is ~10MB. Trim the reproduction or use PR_VIDEO_UPLOAD=r2." >&2
  fi
}
size_ok "$before"
size_ok "$after"

mode="portable"
if [ "${PR_VIDEO_UPLOAD:-}" = "r2" ]; then
  if [ -z "${R2_BUCKET:-}" ] || [ -z "${R2_ACCOUNT_ID:-}" ] \
     || [ -z "${R2_ACCESS_KEY_ID:-}" ] || [ -z "${R2_SECRET_ACCESS_KEY:-}" ]; then
    echo "attach-to-pr.sh: PR_VIDEO_UPLOAD=r2 set but R2_* env vars missing — falling back to portable mode." >&2
  else
    mode="r2"
  fi
fi

if [ "$mode" = "r2" ]; then
  before_url=$(bash "$here/upload-r2.sh" "$before" "pr-evidence/${repo}-${pr}-before.webm")
  after_url=$(bash  "$here/upload-r2.sh" "$after"  "pr-evidence/${repo}-${pr}-after.webm")

  block=$(cat <<EOF

### Fix evidence

| Before (bug) | After (fix) |
|---|---|
| <video src="${before_url}" controls width="480"></video> | <video src="${after_url}" controls width="480"></video> |

<sub>Recorded with Playwright \`recordVideo\` via the \`fix-video-evidence\` skill.</sub>
EOF
)

  if command -v gh >/dev/null 2>&1; then
    tmp=$(mktemp)
    gh pr view "$pr" --json body -q .body > "$tmp"
    printf '%s' "$block" >> "$tmp"
    gh pr edit "$pr" --body-file "$tmp"
    rm -f "$tmp"
    echo "attach-to-pr.sh: appended CDN-linked evidence to PR #${pr} body."
  else
    echo "gh not found — paste this into the PR body yourself:"
    echo "$block"
  fi
  exit 0
fi

# Portable mode.
pr_url=$(gh pr view "$pr" --json url -q .url 2>/dev/null || echo "https://github.com/<owner>/<repo>/pull/${pr}")

human_size () {
  local bytes
  bytes=$(stat -f%z "$1" 2>/dev/null || stat -c%s "$1")
  if [ "$bytes" -ge 1048576 ]; then
    awk -v b="$bytes" 'BEGIN { printf "%.1fMB", b/1048576 }'
  else
    awk -v b="$bytes" 'BEGIN { printf "%dKB", b/1024 }'
  fi
}
before_size=$(human_size "$before")
after_size=$(human_size "$after")

cat <<EOF

### Fix evidence

| Before (bug) | After (fix) |
|---|---|
| _drag \`${before}\` here_ | _drag \`${after}\` here_ |

<sub>Recorded with Playwright \`recordVideo\` via the \`fix-video-evidence\` skill.</sub>

──────────────────────────────────────────────────────
📎  5 seconds of drag-drop:

  1. Open the PR:  ${pr_url}
  2. Click Comment (bottom of the thread).
  3. Paste the markdown table above.
  4. Drag from Finder onto each placeholder:
       • ${before}  (${before_size})
       • ${after}   (${after_size})
  5. Submit. GitHub inlines the .webm - reviewer plays it in-thread.

💡  Doing this on more than a few PRs?  One-time 5-min setup makes it
    zero-touch:

       bash ${here}/setup-r2.sh
──────────────────────────────────────────────────────
EOF
