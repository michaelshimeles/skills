---
name: fix-video-evidence
description: Use to record two short videos of a bug-fix cycle (broken state on the pre-fix commit, working state on the post-fix commit) and attach them to the PR. Trigger on "record fix video", "video proof of fix", "before/after video", "attach video to PR", "PR video evidence", "reproduce and record the bug", or any request to hand a reviewer a moving-picture demo instead of just screenshots. Uses Playwright's built-in recordVideo — no paid API, no extra service. Portable-mode (drag-and-drop the .webm into the PR comment box) is default; auto-upload to R2 is opt-in via env vars.
---

# Fix Video Evidence

## Overview

The Claude Code equivalent of Cursor Cloud's "record a video of the fix" pattern. On the pre-fix commit you record the bug reproducing; on the post-fix commit you re-run the same script and record it working. Two `.webm` files, both attached to the PR. Static screenshots answer "did the pixels change?"; video answers "did the flow actually work?" — much stronger craft signal for a reviewer.

This skill wraps the record + attach cycle. **The fix itself is out of scope** — you (or another skill / agent) apply the code fix between the two recordings.

> **Project rule precedence:** if the repo's `CLAUDE.md` / `AGENTS.md` sets a stricter QA gate (e.g. a mandated machine-human browser QA checklist), honor it. This skill produces evidence for that gate, it doesn't replace it.

## When to Use

- Any bug-fix PR the reviewer will want to *see*: interactive UI, a broken flow, a regression, a visual bug that a still screenshot misses.
- Portfolio-facing repos where every PR should carry proof-of-craft.
- Anywhere `before-and-after` (still screenshots) is not enough because the bug is temporal (loading state that never resolves, jank, wrong sequence, off-screen redirect, focus jump).

**Don't** use for pure-backend PRs with no rendered surface, docs-only PRs, or refactors with no behavior change — a video of nothing changing is noise.

## Prerequisites (fail-loud, install nothing globally)

Check, don't install:

```bash
# In the target repo:
test -f package.json || { echo "No package.json — install Playwright in the repo first"; exit 1; }
npx --no-install playwright --version 2>/dev/null || {
  echo "Playwright not installed. In the target repo, run:"
  echo "  npm i -D @playwright/test"
  echo "  npx playwright install chromium"
  exit 1
}
gh auth status 2>&1 | grep -q "Logged in" || { echo "gh not authenticated. Run: gh auth login"; exit 1; }
```

If any of the three fails, **stop and print the fix**. Do not npm-install into the user's project without permission. Do not proceed silently.

## Step 1 — Locate the PR + set naming

```bash
REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
PR_NUM=$(gh pr view --json number -q .number 2>/dev/null) || {
  echo "No PR for the current branch. Push the branch and open a PR first (gh pr create)."
  exit 1
}
mkdir -p .videos
grep -qxF ".videos/" .gitignore 2>/dev/null || echo ".videos/" >> .gitignore
```

Filenames are `<repo>-<pr>-before.webm` and `<repo>-<pr>-after.webm`. That is the naming convention — do not vary it, `attach-to-pr.sh` grep's for it.

## Step 2 — Write the reproduction script

Copy the template into the repo (not tracked — the .videos/ location is fine, or a scratch dir):

```bash
cp ~/.claude/skills/fix-video-evidence/reference/playwright-template.mjs .videos/repro.mjs
```

Then edit `.videos/repro.mjs` for the specific bug:
- Set `TARGET_URL` (the deployed preview, staging, or `http://localhost:<port>`).
- Fill in the reproduction steps (`click`, `fill`, `waitFor`).
- Leave BOTH the "before" and "after" assertion blocks in place — a `PHASE=before|after` env var flips which one runs. Keep the flow above them identical between phases; that is the whole point.

**One script, two runs.** Never write two scripts — divergence between them is exactly the failure mode this skill exists to catch.

## Step 3 — Record the BEFORE (bug reproduces)

On the pre-fix commit (or `git stash` your fix if it's already in your working tree):

```bash
git stash push -u -m "fix-video-evidence: temporarily park fix" || true
PHASE=before PR_NUM=$PR_NUM REPO_NAME=$REPO_NAME \
  npx playwright test .videos/repro.mjs --reporter=line
```

The context is created with `recordVideo: { dir: '.videos/', size: { width: 1280, height: 720 } }`, and the template renames the raw output to `<repo>-<pr>-before.webm` on teardown.

Check it played the bug back:
```bash
ls -lh .videos/*-before.webm
# On macOS: open .videos/*-before.webm     (QuickTime plays .webm via extensions; else use VLC / a browser: file://…)
```

If the assertion in the "before" phase FAILED (the bug didn't reproduce), the script is wrong — fix the reproduction, not the fix. A "before" video without the visible bug is worthless.

## Step 4 — Apply the fix, then record the AFTER

Pop the fix back (or apply it now if you hadn't yet):

```bash
git stash pop || true
# ... apply the code fix, commit it ...
PHASE=after PR_NUM=$PR_NUM REPO_NAME=$REPO_NAME \
  npx playwright test .videos/repro.mjs --reporter=line
ls -lh .videos/*-after.webm
```

The "after" phase asserts the fix (the flow completes, the error is gone, the correct state renders). If that assertion fails, the fix isn't done — do not attach a passing-looking video.

## Step 5 — Size-check before attaching (GitHub's 10MB cap)

GitHub's comment-box video upload caps at ~10MB per file. Check both:

```bash
find .videos -name "*-${PR_NUM}-*.webm" -exec ls -lh {} \; \
  -exec sh -c 'test $(stat -f%z "$1" 2>/dev/null || stat -c%s "$1") -gt 10485760 \
    && echo "WARN: $1 exceeds 10MB — trim the reproduction, drop the viewport, or use PR_VIDEO_UPLOAD=r2"' _ {} \;
```

If either is over 10MB: shorten the reproduction (fewer `waitForTimeout` calls, tighter viewport, headless-first), or switch to auto-upload mode (Step 6b).

## Step 6a — Portable mode (default): drag-and-drop into the PR

> **When to prefer this**: one-off PRs, or your first time using the skill. 5 seconds of drag-drop per PR, works on any machine with no cloud config. If you'll run this on many PRs, R2 auto-upload (Step 6b) is faster in aggregate - 5-minute one-time setup via the wizard, then zero-touch forever.

```bash
bash ~/.claude/skills/fix-video-evidence/reference/attach-to-pr.sh $PR_NUM
```

That prints a ready-to-paste markdown block like:

```md
### Fix evidence

| Before (bug) | After (fix) |
|---|---|
| _drag `.videos/<repo>-<pr>-before.webm` here_ | _drag `.videos/<repo>-<pr>-after.webm` here_ |
```

Open the PR in a browser, paste the markdown into a comment, then drag each `.webm` from Finder onto its cell. GitHub uploads them and rewrites the placeholder to a `<video>` embed. This works from any machine, no cloud config needed.

## Step 6b — Auto-upload mode (opt-in): R2 → CDN URL → `gh pr edit`

**First-time R2 setup**: run the guided wizard once and never think about it again.

```bash
bash ~/.claude/skills/fix-video-evidence/reference/setup-r2.sh
```

It opens the Cloudflare dashboard, walks you through bucket + API token creation, tests an actual upload, and prints the four `R2_*` `export` lines to paste into your shell profile. Cloudflare's R2 free tier (10GB storage + 1M ops/month) covers a lot of PR videos - no card required for sign-up.

Or, if you prefer manual setup, set the four R2 env vars yourself (any S3-compatible R2 bucket the user already owns):

```bash
export PR_VIDEO_UPLOAD=r2
export R2_BUCKET=<bucket>
export R2_ACCOUNT_ID=<id>
export R2_ACCESS_KEY_ID=<key>
export R2_SECRET_ACCESS_KEY=<secret>
# Optional: R2_PUBLIC_BASE=https://cdn.example.com   (else uses the r2.dev URL from `wrangler r2` or the default account subdomain)
```

Then:

```bash
bash ~/.claude/skills/fix-video-evidence/reference/attach-to-pr.sh $PR_NUM
```

The helper detects `PR_VIDEO_UPLOAD=r2`, uploads both files via `reference/upload-r2.sh` (uses `aws s3 cp` against the R2 S3 endpoint), and appends the CDN-linked markdown to the PR body via `gh pr edit --body-file`. No hardcoded bucket name — everything reads from env.

If the R2 env vars are missing but `PR_VIDEO_UPLOAD=r2` is set, the helper falls back to portable-mode output with a warning. Never silently drops the evidence.

## Gotchas

1. **`.webm` on GitHub** — GitHub renders `.webm` inline in comments and PR bodies. Do NOT convert to `.mp4` "to be safe" — that adds ffmpeg dependency for no benefit.
2. **Playwright's chromium is not on PATH after a fresh install** — always invoke via `npx playwright test`, never a bare `chromium` binary. `npx playwright install chromium` is a one-time-per-machine step; the skill's prereq check catches it.
3. **The recorded video is finalized on context close.** Do not `process.exit()` mid-test — the template uses `test.afterAll` + `context.close()` so the `.webm` header is written correctly. A killed process leaves a zero-byte file.
4. **Rename happens after close, not during.** Playwright names videos by the internal test id; the template's `afterAll` hook moves `.videos/*.webm` to `<repo>-<pr>-<phase>.webm`. If you see raw hex-named files, teardown didn't run.
5. **Viewport bigger than 1280×720 balloons the file size fast.** Stick to 720p unless a bug is genuinely only visible at 1440p+.
6. **Never record credential entry.** If the flow needs auth, log in headlessly BEFORE the `recordVideo` context opens (`storageState`), or blank the password field on-screen. A `.webm` in a public PR is public.
7. **Claude Code's Bash tool resets cwd between calls** — always use absolute paths or re-`cd` in the same compound command. This skill's helpers assume they're invoked from the target repo root.
8. **Do not commit `.videos/`.** The skill appends it to `.gitignore` on first run. If a `.webm` is somehow staged, unstage it — the PR embeds carry the file, the repo shouldn't.
9. **Cursor's cloud videos vs this** — Cursor auto-records for cloud runs only. Locally-run Claude Code needs this skill; there is no equivalent native harness feature. Do not tell the user to "use the built-in" — there isn't one.

## Follow-ups this skill deliberately does not do

- No auto-caption / transcript. (Reviewer accessibility gap.)
- No side-by-side single-video composite (would need ffmpeg).
- No hosted-service fallback for users without R2 (portable mode is that fallback today).

## Verification Checklist

- [ ] Prereqs verified (Playwright installed in repo, `gh` authed, chromium browser installed).
- [ ] ONE `repro.mjs` script; `PHASE=before` and `PHASE=after` flip only the assertion, not the flow.
- [ ] Before video actually shows the bug (assertion `PHASE=before` passed).
- [ ] After video actually shows the fix (assertion `PHASE=after` passed on the post-fix commit).
- [ ] Both files ≤10MB OR auto-upload mode active.
- [ ] Markdown attached to the PR (comment for portable, body for auto-upload).
- [ ] `.videos/` in `.gitignore`; no `.webm` staged for commit.
