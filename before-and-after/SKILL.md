---
name: before-and-after
description: Captures before/after screenshots of web pages or elements for visual comparison. Use when user says "take before and after", "screenshot comparison", "visual diff", "PR screenshots", "compare old and new", or needs to document UI changes. Accepts two URLs (file://, http://, https://) or two image paths.
allowed-tools:
  - Bash(npx @vercel/before-and-after *)
  - Bash(before-and-after *)
  - Bash(which before-and-after)
  - Bash(npm install -g @vercel/before-and-after)
  - Bash(*/upload-and-copy.sh *)
  - Bash(curl -s -o /dev/null -w *)
  - Bash(gh pr view *)
  - Bash(gh pr edit *)
  - Bash(vercel inspect *)
  - Bash(vercel whoami)
  - Bash(which vercel)
  - Bash(which gh)
---

# Before-After Screenshot Skill

> **Package:** `@vercel/before-and-after`
> Never use `before-and-after` (wrong package).

## Agent Behavior Rules

**DO NOT:**
- Switch branches or stash another task's changes. Use an isolated worktree for
  any baseline server already authorized by the task.
- Use `--full` unless user explicitly asks for full page / full scroll capture

**DO:**
- Use `--markdown` when user wants PR integration or markdown output
- Use `--mobile` / `--tablet` if user mentions phone, mobile, tablet, responsive, etc.
- Reuse before captures, baseline URLs, and revision information already
  established in the task. Confirm that they show the relevant behavior and
  match the after capture's viewport and starting state.
- Treat the current state as after only when the task context establishes it.
  If the before state remains ambiguous after checking available context, ask
  for the missing baseline. Do not ask again for a URL when a valid image pair
  or earlier baseline is already available.

## Capture and delivery

1. Use an installed `before-and-after` CLI or `npx @vercel/before-and-after`.
2. For remote URLs, check access when needed. A 401/403 indicates protection.
   Existing image pairs do not require a URL or deployment access check.
3. Capture missing images with `before-and-after "<before-url>" "<after-url>"`.
4. When the task calls for uploaded evidence or PR markdown, run
   `before-and-after before.png after.png --markdown` once. For local capture
   requests, deliver the files without uploading them.
5. Append the markdown to the PR when PR integration is part of the task.

Resolve bundled script paths relative to this skill's directory, not the
project working directory. Reuse earlier evidence instead of recapturing it.

## Quick Reference

```bash
# Basic usage
before-and-after <before-url> <after-url>

# With selector
before-and-after url1 url2 ".hero-section"

# Different selectors for each
before-and-after url1 url2 ".old-card" ".new-card"

# Viewports
before-and-after url1 url2 --mobile    # 375x812
before-and-after url1 url2 --tablet    # 768x1024
before-and-after url1 url2 --full      # full scroll

# From existing images
before-and-after before.png after.png --markdown

# Via npx (use full package name!)
npx @vercel/before-and-after url1 url2
```

| Flag | Description |
|------|-------------|
| `-m, --mobile` | Mobile viewport (375x812) |
| `-t, --tablet` | Tablet viewport (768x1024) |
| `--size <WxH>` | Custom viewport |
| `-f, --full` | Full scrollable page |
| `-s, --selector` | CSS selector to capture |
| `-o, --output` | Output directory (default: ~/Downloads) |
| `--markdown` | Upload images & output markdown table |
| `--upload-url <url>` | Custom upload endpoint (default: 0x0.st) |

## Image Upload

```bash
# Default (0x0.st - no signup needed)
./scripts/upload-and-copy.sh before.png after.png --markdown

# GitHub Gist
IMAGE_ADAPTER=gist ./scripts/upload-and-copy.sh before.png after.png --markdown
```

## Vercel Deployment Protection

If `.vercel.app` URL returns 401/403:

1. Check Vercel CLI: `which vercel && vercel whoami`
2. If available: `vercel inspect <url>` to get bypass token
3. If not: Tell user to provide bypass token, take manual screenshots, or disable protection

## PR Integration

```bash
# Check for gh CLI
which gh

# Get current PR
gh pr view --json number,body

# Write the existing body plus the comparison to a temporary file, then:
gh pr edit <number> --body-file /path/to/pr-body.md
```

If no `gh` CLI: output markdown and tell user to paste manually.

## Error Reference

| Error | Fix |
|-------|-----|
| `command not found` | `npm install -g @vercel/before-and-after` |
| `could not determine executable` | Use `npx @vercel/before-and-after` (full name) |
| 401/403 on .vercel.app | See Vercel protection section |
| Element not found | Verify selector exists on page |
