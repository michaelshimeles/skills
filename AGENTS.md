# Agent-assisted delivery workflow

This is Sille's personal adaptation of the workflow from
[michaelshimeles/skills](https://github.com/michaelshimeles/skills). It governs
work in this collection and can be referenced by a consuming project. For
Helios Lite, call it the Agent-Assisted Firmware Delivery Workflow, or Helios
Delivery Workflow for short.

## Scope and precedence

The core workflow is independent of model provider and coding-agent harness.
Model choice does not change delivery rules. Put harness-specific behavior in
its own section; apply [Pi instructions](#pi-specific-instructions) only in Pi.

Follow the consuming project's architecture, permissions and test-execution
policy before this collection's generic guidance. Flag conflicts before acting.
Invoking a skill or this workflow does not override an existing approval boundary.
If the project reserves tests for the user, request authorization or provide
commands instead of running them.

This file is the workflow source of truth for this fork. Read the applicable
skills at their stages. Skill names in the core are references, not portable
slash commands; read `<skill-name>/SKILL.md` relative to this repository or from
a known installation. Resolve bundled scripts and references relative to the
skill directory. If instructions are unavailable, report that instead of
inventing them.

The adaptations so far separate scope and harness guidance, remove the web
screenshot-comparison skill and make branch selection project-aware. Overlap
handling, broader verification and the Greptile gate remain for later discussion.

## Workflow

1. **Isolate.** Read `new-feature/SKILL.md` and follow its branch-selection rules.
   Find the project's policy, state the starting base and PR target, then create
   an isolated task branch and worktree. Without project rules or a task override,
   the default is `origin/main` with a PR targeting `main`.
2. **Build.** Read `code-structure/SKILL.md` where its advice fits the
   project's architecture. Its service-layer guidance separates orchestration
   from reusable mechanics; it does not replace the project's module ownership
   and dependency rules.
3. **Prove.** Read `evidence-driven-testing/SKILL.md`. Verify with the repo's checks
   plus runtime evidence. Capture the **before** state while reproducing the
   issue — prior to fixing it, when it is cheapest — and the **after** once
   the change works.
4. **Ship.** Read `greploop/SKILL.md`. Open the PR with evidence appropriate to
   the change, such as test output, serial logs, protocol traces, terminal
   captures or hardware observations. Screenshots and video are not mandatory
   for every visible change. State missing verification explicitly. Follow
   `greploop`, or `greploop-apps` when the PR exceeds Greptile's file-count limit,
   until Greptile reports **5/5 with zero unresolved comments**. Finish by
   presenting the PR URL.

## Writing for humans

Read `unslop/SKILL.md` and apply it to anything a person will read before you commit, post, or
send it: commit messages, the PR title and body, README and doc edits, code
comments, and the closing reply. It strips AI tells (em dashes, filler,
hedging, chatbot phrases, puffery, bold-label lists) and replaces fancy
words with plain ones and passive voice with active. Apply it to text you
wrote or changed, not to prose you didn't touch.

## Multi-agent rules

- Commit task changes on their assigned branch, not directly on the integration
  branch selected as their base or PR target.
- One worktree and one branch per task and per agent — never reuse or modify
  another agent's worktree, branch, or uncommitted work.
- **Scope check** before starting: skim open PRs' changed files
  (`gh pr list`, `gh pr diff <n> --name-only`) and look for uncommitted work
  in shared checkouts. On overlap, stop and ask for direction.
- Never force-push an integration branch or use plain `--force`. Use
  `--force-with-lease` only on your own task branch and within project permissions.
- Resolve lockfile conflicts by regenerating, never by hand-merging.
- Worktrees don't isolate shared resources: confirm a dev-server port
  answers *your* process before trusting it, and don't run schema
  experiments against a shared database.
- If a conflict can't be resolved confidently, stop and report instead of
  guessing.

## Completing a task

1. Keep changes limited to the assigned task.
2. Run the repo's checks within its authorization policy. Otherwise list the
   commands for the user and mark them unexecuted. Get exact commands from the
   project's maintained documentation.
3. Assemble the evidence captured along the way. Include before/after results
   when they help demonstrate the change; no screenshot table is required.
4. Commit with a clear message. If rebasing is appropriate under the project's
   policy, use the task's selected base rather than hard-coded `origin/main`.
   Resolve any changed dependency or target first. Rerun checks only within the
   project's authorization policy.
5. Push (`git push -u origin <branch>`; after rebasing an already-pushed
   branch, `--force-with-lease`).
6. Open the PR. The body must explain what changed, how it was tested (every
   claim backed by evidence), any missing verification, and risks or follow-up
   work. Apply `unslop` to the title and body before posting.
7. Follow `greploop` or `greploop-apps` until **5/5 with zero unresolved
   comments**.
8. End by presenting the PR URL.

Do not merge the PR unless explicitly instructed. Keep the worktree until
the PR is merged or closed.

## Pi-specific instructions

Apply this section only when running in Pi. Keep these mechanics out of the
model-neutral core.

- Discover skills through the configured Pi locations. User-level
  `~/.agents/skills/` supports reuse across projects and worktrees; project
  `.agents/skills/` discovery stops at the repository root. A separate clone is
  not automatically a discovered skill installation.
- Use `/skill:<name>` for explicit skill invocation, such as
  `/skill:new-feature`. Automatic loading depends on discovery and frontmatter.
  `disable-model-invocation: true` makes a skill explicit-only. Do not assume
  upstream `/new-feature` command syntax is a Pi command.
- Read a skill by its known path when it is not installed. This collection has no
  workflow wrapper skill yet; a request to follow `AGENTS.md` selects the full
  workflow, while a component command selects that component.
- Use `/reload` after editing installed skills. Changes to this clone do not
  update separately installed skill copies.
- Inspect the current branch, worktree and harness instructions before managing
  Git workspaces. In ordinary Pi sessions, create the task worktree yourself
  according to the isolation policy. If an integration already assigned a task
  worktree, use it rather than creating another one or changing another agent's
  workspace. This is a harness difference, not a model-provider difference.
- Use the tools actually exposed in the session. Browser controls, MCP services
  and delegation are optional integrations; report missing capabilities rather
  than assuming they exist or weakening the required checks silently.

## Repo-specific sections to add

When dropping this file into a project, append what agents need to execute
the beats there: commands & checks, hard invariants (security and
architecture rules), an environment quick reference, local test
infrastructure (stubs, fixtures), and anything that can't be tested locally.

## Skill sources

| Skill | Source |
|---|---|
| `new-feature`, `code-structure`, `evidence-driven-testing` | this repo |
| `greploop` | this repo, vendored from [greptileai/skills](https://github.com/greptileai/skills) |
| `greploop-apps` | this repo (local variant of greploop for huge PRs; no separate upstream) |
| `unslop` | this repo, vendored from [cursor/plugins (pstack)](https://github.com/cursor/plugins/tree/main/pstack/skills/unslop); frontmatter edited so agents apply it unprompted (`disable-model-invocation` dropped, description scoped to text the agent writes or edits for people), body untouched |
