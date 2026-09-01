# Skills

A collection of [agent skills](https://code.claude.com/docs/en/skills) for Claude Code. Each skill is a folder containing a `SKILL.md` with frontmatter (name, description) and instructions that Claude loads on demand when the task matches.

## Available Skills

### [before-and-after](before-and-after/SKILL.md)

Captures before/after screenshots of web pages or elements and outputs a PR-ready markdown comparison table, driving the `@vercel/before-and-after` CLI.

Use it when:

- A PR needs visual proof that a UI change does what it claims
- You want a `| Before | After |` table generated and uploaded in one step
- Comparing two URLs, two existing images, or a mix of both

> Vendored from [vercel-labs/before-and-after](https://github.com/vercel-labs/before-and-after) (PolyForm Shield 1.0.0 — license included in the folder). Install the CLI with `npm i -g @vercel/before-and-after agent-browser`.

### [code-structure](code-structure/SKILL.md)

Service layer architecture guidance. Enforces a two-layer separation where **actions** orchestrate domain rules (the "why/when") and a **service layer** centralizes reusable operational mechanics (the "how").

Use it when:

- Multiple workflows duplicate the same operational logic
- You're deciding what belongs in actions vs. shared services
- A bug fix in one flow doesn't propagate to others doing the same thing
- Adding a feature that shares mechanics with existing ones

Includes a migration checklist for extracting shared logic safely and a table of anti-patterns to avoid (god services, leaky services, over-abstraction).

### [evidence-driven-testing](evidence-driven-testing/SKILL.md)

Records visual proof while testing UI behavior — the agent drives the app live via computer use (or [cua-driver](https://github.com/trycua/cua) when the harness has no computer-use tools) while the bundled recorder captures the session — then posts the video and a results summary to the PR and tracker issue. The recorder (`scripts/evidence.py`, Python 3 + FFmpeg) runs on Linux, macOS, and Windows and has `doctor`, `start`, `annotate`, and `stop` commands: annotations are timestamped as the agent tests, burned into `evidence.mp4` on stop, and summarized in a generated `report.md` and `manifest.json`. Headless environments swap the recorder for scripted screenshots and Playwright captures; non-UI changes still get evidence (measured numbers, output pairs, transcript excerpts).

Use it whenever a change needs verifiable evidence that it works, instead of prose claims.

> The recorder needs `ffmpeg`/`ffprobe` built with `libx264` and the `ass` filter, plus a screen-capture source: X11 (`DISPLAY`) or wlroots Wayland (`wf-recorder`; GNOME/KDE are not supported) on Linux, Screen Recording permission on macOS, any standard ffmpeg on Windows. `python3 scripts/evidence.py doctor` reports both. The raw capture is MPEG-TS, so a crashed or hard-killed recorder still yields usable evidence. The headless path needs only a running app and a scriptable browser (Playwright via npx). Posting evidence requires the `gh` CLI (or equivalent). `tests/test_evidence.py` smoke-tests the recorder end to end with a synthetic video source (`python3 -m pytest tests/ -q`).

### [greploop](greploop/SKILL.md)

Iteratively fixes a PR (GitHub), MR (GitLab), or shelved changelist (Perforce) until Greptile gives a perfect review: 5/5 confidence with zero unresolved comments. Triggers the review, fixes actionable comments, resolves threads, pushes, and repeats (max 5 iterations).

Use it when a PR should be fully optimized against Greptile's code review standards before merge.

> Vendored from [greptileai/skills](https://github.com/greptileai/skills) (MIT — license included in the folder). Requires Greptile installed on the repo and an authenticated `gh`/`glab`/`p4` CLI.

### [greploop-apps](greploop-apps/SKILL.md)

Identical loop to greploop, but triggers reviews by tagging `@greptile-apps`, which bypasses Greptile's file-count limit on huge PRs that the plain `@greptile` mention refuses to review — including a fallback that polls Greptile's edited summary comment when no check run appears.

Use it when greploop's trigger gets "Too many files changed for review".

> Local variant derived from greptileai's greploop (MIT — license included in the folder); no separate upstream.

### [new-feature](new-feature/SKILL.md)

Starts every new task in an isolated Git worktree branched from `origin/main` — unique task naming, a scope check against open PRs, fresh dependency installs, and cleanup after merge — so multiple agents can work on the same repo in parallel without conflicts.

Use it when:

- Starting any new feature, fix, or task, before writing code
- Multiple agents (or sessions) work the same repository concurrently
- You need a consistent branch-per-task convention with safe cleanup

Includes harness deltas for Claude Code and Cursor, which manage worktrees themselves.

## Workflow

[`AGENTS.md`](AGENTS.md) ties the skills together into a four-beat workflow — isolate (`new-feature`) → build (`code-structure`) → prove (`evidence-driven-testing`) → ship (`before-and-after` + `greploop`). Drop it into a repo alongside the skills and fill in the repo-specific callouts (checks, invariants, environment).

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
