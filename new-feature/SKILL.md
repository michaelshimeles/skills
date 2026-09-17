---
name: new-feature
description: Isolate repository edits in a Git worktree before starting a feature, fix, or documentation change. Preserve a worktree already assigned to the same task. Read-only reviews and investigations do not need a new worktree.
---

# New Feature

Each editing task gets its own worktree and branch, created from the latest
`origin/main` unless the user specifies a different base. Read-only work can
use the existing checkout. Never build on `main` or reuse another task's work.

## Check existing isolation first

Inspect `git worktree list`, `git status --short`, the current branch, and the
session's task assignment. If the environment already created a worktree for
this task, keep its path and branch and skip steps 3 and 4. In step 5, use the
actual assigned path. Do not infer isolation from the editor name or a branch
prefix alone. Otherwise follow all steps.

## Steps

1. **Sync**: `git fetch origin`.

2. **Scope check**: run `gh pr list` and skim the open PRs' changed files
   (`gh pr diff <n> --name-only`). For shared files, read the overlapping
   diffs. Independent edits may proceed in your own worktree. Ask for direction
   only when the changes conflict in behavior, require another task's unfinished
   work, or ownership is unclear. Check shared checkouts for uncommitted work
   without changing it. On another hosting platform, use its equivalent PR/MR
   tools; if unavailable, report the scope-check limitation and still isolate.

3. **Name the task**: lowercase-with-hyphens plus a short unique suffix,
   e.g. `user-auth-0816a`. If `git worktree add` fails because the name
   exists, pick a different name — never force or reuse.

4. **Create the worktree** from the repo root:

   ```bash
   git worktree add <worktrees-dir>/<task-name> \
     -b <branch-prefix>/<task-name> origin/main
   ```

   Use a directory outside the checkout, or a **gitignored** directory inside
   it, so worktrees cannot be committed by accident. Use a
   consistent branch prefix (e.g. `agent/`). Follow the repo's conventions
   if it defines them.

5. **Enter and verify**:

   ```bash
   cd <worktrees-dir>/<task-name>
   git branch --show-current   # must print your new branch, not main
   ```

   Confirm the required runtime version. Install dependencies inside the
   worktree when needed for the task's checks. Documentation-only work does
   not require installing an unrelated application toolchain.

## Remember

- Worktrees do **not** isolate dev-server ports or shared databases.
  Tracked dependency lockfiles are separate in each worktree. Confirm a port answers
  *your* process (`lsof -i :<port>`) before trusting what it serves, and
  resolve lockfile conflicts by regenerating, never by hand-merging.
- Keep the worktree until the PR is merged or closed. Cleanup after merge:

  ```bash
  git worktree remove <worktrees-dir>/<task-name>
  git branch -D <branch-prefix>/<task-name>
  ```

  `-D` is expected: after a squash- or rebase-merge, `-d` refuses even
  though the work is merged.
