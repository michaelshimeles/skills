# Skills

A collection of [agent skills](https://code.claude.com/docs/en/skills) for Claude Code. Each skill is a folder containing a `SKILL.md` with frontmatter (name, description) and instructions that Claude loads on demand when the task matches.

## Available Skills

### [code-structure](code-structure/SKILL.md)

Service layer architecture guidance. Enforces a two-layer separation where **actions** orchestrate domain rules (the "why/when") and a **service layer** centralizes reusable operational mechanics (the "how").

Use it when:

- Multiple workflows duplicate the same operational logic
- You're deciding what belongs in actions vs. shared services
- A bug fix in one flow doesn't propagate to others doing the same thing
- Adding a feature that shares mechanics with existing ones

Includes a migration checklist for extracting shared logic safely and a table of anti-patterns to avoid (god services, leaky services, over-abstraction).

### [evidence-driven-testing](evidence-driven-testing/SKILL.md)

Records visual proof while testing UI behavior — screen recording with structured test/assertion annotations — then posts the video and a results summary to the PR and tracker issue.

Use it whenever a UI change needs verifiable evidence that it works, instead of prose claims.

> Requires a GUI environment with screen recording, an authenticated browser session for the app under test, and the `gh` CLI (or equivalent) for posting evidence.

### [worktree](worktree/SKILL.md)

Starts every new task in an isolated Git worktree branched from `origin/main` — unique task naming, a scope check against open PRs, fresh dependency installs, and cleanup after merge — so multiple agents can work on the same repo in parallel without conflicts.

Use it when:

- Starting any new feature, fix, or task, before writing code
- Multiple agents (or sessions) work the same repository concurrently
- You need a consistent branch-per-task convention with safe cleanup

Includes harness deltas for Claude Code and Cursor, which manage worktrees themselves.

## Installation

Clone the repo and copy (or symlink) a skill folder into your skills directory:

```bash
# Available in all projects
cp -r code-structure ~/.claude/skills/

# Or scoped to a single project
cp -r code-structure /path/to/project/.claude/skills/
```

Claude Code picks up the skill automatically and invokes it when a task matches the skill's description. You can also invoke one explicitly with `/code-structure` or `/evidence-driven-testing`.

## Adding a New Skill

1. Create a folder named after the skill (kebab-case).
2. Add a `SKILL.md` with `name` and `description` frontmatter — the description is what Claude uses to decide when the skill applies, so make it trigger-focused ("Use when...").
3. Keep instructions concise and actionable; link out to reference files in the folder if they get long.
