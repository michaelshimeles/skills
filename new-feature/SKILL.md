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

2. **Scope check**: run `gh pr list`, inspect changed-file lists
   (`gh pr diff <n> --name-only`), then read relevant diffs for shared files.
   Check for uncommitted work in shared checkouts without changing it. Apply
   the overlap assessment below before implementing the affected area.

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

## Overlap assessment

Shared filenames are a warning signal, not an automatic blocker. Classify the
actual changes and their contracts, not just the names of the files. Separate
worktrees prevent overwrites; they do not prove branches will work together.

| Finding | Action |
| --- | --- |
| Compatible, independent edits | Proceed and report the overlap and expected integration work. Documentation, separate build entries and startup wiring can qualify, but only after inspecting their meaning and ordering. |
| Same implementation or interface with unclear compatibility | Ask before editing the affected area. Continue independent work that does not rely on the unresolved decision. |
| Conflicting behavior, duplicated functionality or unresolved dependency | Pause affected work and request a decision on ownership, contracts or dependency order. |

For each relevant overlap, record the PR or local work involved, the actual
changes, classification, rationale and proposed integration action in the task's
plan or progress report. Reassess when scope or a relevant dependency changes.
If relevant diffs are unavailable, disclose the gap; do not classify uninspected
shared changes as low-risk. Ask when that missing information prevents a safe
assessment of the affected work.

Compatible edits in the same lines may need a mechanical Git resolution. A
clean merge can still hide a behavioral conflict. Keep architectural decisions
and permission requirements separate from the overlap assessment; low-risk
file overlap does not authorize an architecture change.

## Integration responsibility

- The task agent owns keeping its branch compatible with the agreed base and
  resolving its own changes within project policy and permissions.
- Modify only the assigned branch and worktree. Preserve other agents' branches,
  worktrees and uncommitted work.
- Get user agreement before coordinating changes across branches, changing the
  agreed dependency order or rewriting published history. Existing explicit
  authorization remains valid within its scope.
- Resolve uncertain semantic conflicts with the user rather than guessing.
  After integration, verify the combined behavior under the project's testing
  policy. If checks are not authorized, provide commands and state what remains
  unverified.

This policy is a trial. If it allows repeated integration failures or still
causes unnecessary interruptions, record those cases and revisit the rule with
the user rather than silently changing it.

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
