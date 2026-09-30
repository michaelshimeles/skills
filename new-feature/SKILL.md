---
name: new-feature
description: Start a new task in an isolated Git worktree after resolving the project's branching policy, starting base and PR target. Use at the beginning of every new feature, fix, or task before writing code.
---

# New Feature

Every task gets its own worktree and task branch. Resolve the starting base and
PR target before creating it. Work on the task branch rather than directly on
an integration branch, and never reuse another agent's workspace.

## Branch selection

1. Search the target project's `AGENTS.md`, `README.md`, `CONTRIBUTING.md` and
   linked development/release documentation for branching rules. Branch lists,
   the currently checked-out branch and CI filters are clues, not a policy.
2. Follow documented project rules and explicit task instructions. If they
   conflict, ask before creating a worktree.
3. Without a project-specific rule or explicit override, default to starting
   from `origin/main` with a PR targeting `main`. If that branch or remote does
   not exist, ask rather than choosing another silently.
4. State the selected starting base and PR target before creating the worktree.
   Ask for confirmation when policy is ambiguous, a non-default choice has not
   already been authorized, or work depends on an unmerged feature. Record the
   dependency and intended integration order; do not assume the starting base
   and final PR target are interchangeable.
5. Keep these selections with the task and use the selected base for later
   synchronization or rebasing. If it merges, disappears or changes role, resolve
   the new base and target before proceeding. Tags name fixed revisions and are
   not PR target branches.

## Harness deltas — read first

- **Claude Code**: the harness creates and manages worktrees itself (under
  `.claude/worktrees/<name>`). **Skip steps 3–4 below** (no manual
  `git worktree add` / `remove`), and keep the harness-assigned branch name.
  Steps 1–2 and 5 still apply.
- **Cursor-managed worktrees** (branches named `worktree-*`): same idea —
  keep the assigned branch and worktree, apply steps 2 and 5.
- Any other harness: follow all steps.

Resolve branch selection even when the harness supplies the worktree. If its
assigned base conflicts with the project's policy, report it before changing
workspace history.

## Steps

1. **Select and sync**: resolve branch selection above, then `git fetch origin`.
   Verify the selected remote base exists before creating the worktree.

2. **Scope check**: run `gh pr list` and skim the open PRs' changed files
   (`gh pr diff <n> --name-only`). If your task needs files another open PR
   is editing, **stop and ask for direction** instead of proceeding. Also
   check for uncommitted work in the checkout — another agent may be
   mid-task.

3. **Name the task**: lowercase-with-hyphens plus a short unique suffix,
   e.g. `user-auth-0816a`. If `git worktree add` fails because the name
   exists, pick a different name — never force or reuse.

4. **Create the worktree** from the repo root:

   ```bash
   git worktree add <worktrees-dir>/<task-name> \
     -b <branch-prefix>/<task-name> <selected-remote-base>
   ```

   Use a **gitignored** directory for worktrees (e.g. `.claude/worktrees/`
   or `.worktrees/`) so they can never be committed by accident, and a
   consistent branch prefix (e.g. `agent/`). Follow the repo's conventions
   if it defines them.

5. **Enter and verify**:

   ```bash
   cd <worktrees-dir>/<task-name>
   git branch --show-current   # must print your assigned task branch
   ```

   Then install dependencies fresh inside the worktree (worktrees don't
   share `node_modules`/virtualenvs) and confirm the runtime version the
   repo requires before running anything.

## Remember

- Worktrees do **not** isolate shared resources: dev-server ports, shared
  databases, and dependency lockfiles are global. Confirm a port answers
  *your* process (`lsof -i :<port>`) before trusting what it serves, and
  resolve lockfile conflicts by regenerating, never by hand-merging.
- Keep the worktree until the PR is merged or closed. Cleanup after merge:

  ```bash
  git worktree remove <worktrees-dir>/<task-name>
  git branch -D <branch-prefix>/<task-name>
  ```

  `-D` is expected: after a squash- or rebase-merge, `-d` refuses even
  though the work is merged.
