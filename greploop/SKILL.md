---
name: greploop
description: Address Greptile feedback on a PR, MR, or shelved changelist through bounded review and fix cycles. Use when the task includes a Greptile review loop. Supports the alternate @greptile-apps trigger for large PRs.
license: MIT
compatibility: GitHub automation requires Python 3.10+ and authenticated gh. GitLab requires glab; Perforce requires p4 and the site's review integration. Greptile must be installed.
metadata:
  author: greptileai
  version: "2.0"
---

# Greploop

Improve the requested change using Greptile feedback. Success means a fresh
5/5 review of the current revision with no unresolved actionable Greptile
findings. The bot's score complements the project's checks and your judgment.

## Inputs

- PR, MR, or changelist number. Infer it from the current task when omitted.
- `--max-iterations N`, a positive integer, defaults to 10 review cycles.
- `--trigger @greptile` by default, or `@greptile-apps` for the alternate route.
  Use the alternate when the normal trigger reports too many changed files.
- `--vcs github|gitlab|perforce` when repository context is ambiguous.

Apply the user's existing authorization and task scope. A read-only review
request does not authorize code edits or posting comments. Keep your own task's
worktree and branch; do not switch another task's checkout to the PR branch.

## Choose the platform

Use the repository and session context, not an installed executable alone.
Read only the relevant reference:

- [GitHub](references/github.md): the bundled helper tracks each trigger and
  waits for a scored review tied to the current commit.
- [GitLab](references/gitlab-api.md): use notes and resolvable discussions;
  CI pipeline activity alone does not identify a Greptile review.
- [Perforce](references/perforce.md): use the configured Swarm or site adapter.

## Review cycle

1. Confirm the target revision, clean task ownership, and effective iteration
   cap. Run relevant checks before publishing edits and push or shelve them.
2. Start one review attempt using the platform reference. Record its trigger
   and revision. Wait at most 10 minutes for fresh results; do not reuse an
   earlier score just because it belongs to the same commit.
3. Read the entire fresh summary, including general-comment findings. Fetch
   all pages of unresolved Greptile threads. An empty inline-comment list does
   not prove the summary contains no remaining work. Older unresolved threads
   remain relevant until addressed, even after their lines become outdated.
4. If the current review is 5/5, no actionable Greptile findings remain, and
   relevant checks pass, finish. Otherwise evaluate each finding in context.
   Fix valid issues within the task. For a false positive, record the reason
   and supporting evidence before resolving it. Do not change correct code
   merely to chase the score or resolve other reviewers' threads.
5. Run checks for the fixes. Commit only task files, push or re-shelve, then
   resolve the specific threads whose fixes are published. Use explicit file
   paths when staging. If no code changed, skip the commit and push.
6. Start a new attempt for the resulting revision if the cap permits it.
   A changed head invalidates the old attempt. Do not reuse an attempt file
   or retrigger merely because a poll has not returned yet.

Stop when the cap is reached, a review times out, the integration is unavailable,
or the remaining findings require a scope decision. Report the actual result
and remaining work. Do not raise the cap automatically or call a partial
result complete. The iteration cap includes reviews that produce no edits.

## Report

Give the PR/MR URL or changelist, reviewed revision, number of cycles, current
score, checks run, resolved findings, and remaining findings. Distinguish a
successful review from a timeout or capped run. Do not merge unless requested.
