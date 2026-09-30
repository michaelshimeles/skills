# Agent-assisted delivery workflow

Sille's personal fork of [michaelshimeles/skills](https://github.com/michaelshimeles/skills), adapted from experiments with the Helios Lite firmware project.

The goal is repeatable delivery with clear human involvement. The workflow is independent of model and coding-agent harness. OpenAI, Anthropic and other model choices follow the same delivery rules. Harness-specific instructions belong in separate sections, starting with Pi.

For firmware work, the name is **Agent-Assisted Firmware Delivery Workflow**, or **Helios Delivery Workflow** for short. "Software-factory experiment" describes the broader ambition, not a claim that delivery is fully autonomous.

Each skill is a folder containing `SKILL.md` with frontmatter and instructions, using the [Agent Skills format](https://agentskills.io/specification). Discovery, automatic loading and command syntax depend on the harness.

## Scope of this fork

The first adaptation separates a generic workflow core from Pi-specific usage and preserves upstream attribution. The component skills still contain inherited assumptions, including Claude Code and Cursor worktree instructions in `new-feature`. A model-neutral README does not make every bundled skill harness-neutral yet.

The web screenshot-comparison skill and its upload scripts have been removed. Evidence should fit the change: test output, serial logs, protocol traces, terminal captures or hardware observations. A screenshot comparison table is not a required delivery artifact.

Branch and dependency policy, overlap checks, the broader verification skill and review gates remain topics for later discussion. The consuming project's architecture, permissions and test-execution policy take precedence over this collection's generic guidance.

## Available skills

### [code-structure](code-structure/SKILL.md)

Service layer architecture guidance. Enforces a two-layer separation where **actions** orchestrate domain rules (the "why/when") and a **service layer** centralizes reusable operational mechanics (the "how").

Use it when:

- Multiple workflows duplicate the same operational logic
- You're deciding what belongs in actions vs. shared services
- A bug fix in one flow doesn't propagate to others doing the same thing
- Adding a feature that shares mechanics with existing ones

Includes a migration checklist for extracting shared logic safely and a table of anti-patterns to avoid (god services, leaky services, over-abstraction).

### [evidence-driven-testing](evidence-driven-testing/SKILL.md)

Records visual proof while testing UI behavior. The agent drives the app live via computer use (or [cua-driver](https://github.com/trycua/cua) when the harness has no computer-use tools) while the bundled recorder captures the session, then posts the video and a results summary to the PR and tracker issue. The recorder (`scripts/evidence.py`, Python 3 + FFmpeg) runs on Linux, macOS, and Windows and has `doctor`, `start`, `annotate`, and `stop` commands. It timestamps each annotation as the agent tests, burns them into `evidence.mp4` on stop, and summarizes them in a generated `report.md` and `manifest.json`. Headless environments swap the recorder for scripted screenshots and Playwright captures; non-UI changes still get evidence (measured numbers, output pairs, transcript excerpts).

Use it whenever a change needs verifiable evidence that it works, instead of prose claims.

> The recorder needs `ffmpeg`/`ffprobe` built with `libx264` and the `ass` filter, plus a screen-capture source: X11 (`DISPLAY`) or wlroots Wayland (`wf-recorder`; GNOME/KDE are not supported) on Linux, Screen Recording permission on macOS, any standard ffmpeg on Windows. `python3 scripts/evidence.py doctor` reports both. The raw capture is MPEG-TS, so a crashed or hard-killed recorder still yields usable evidence. The headless path needs only a running app and a scriptable browser (Playwright via npx). Posting evidence requires the `gh` CLI (or equivalent). `tests/test_evidence.py` smoke-tests the recorder end to end with a synthetic video source (`python3 -m pytest tests/ -q`).

### [greploop](greploop/SKILL.md)

Iteratively fixes a PR (GitHub), MR (GitLab), or shelved changelist (Perforce) until Greptile gives a perfect review: 5/5 confidence with zero unresolved comments. Triggers the review, fixes actionable comments, resolves threads, pushes, and repeats, up to `--max-iterations` cycles (default 10).

Use it to get a PR to a clean Greptile review before merge.

> Vendored from [greptileai/skills](https://github.com/greptileai/skills) (MIT, license included in the folder). Requires Greptile installed on the repo and an authenticated `gh`/`glab`/`p4` CLI.

### [greploop-apps](greploop-apps/SKILL.md)

The same loop as greploop, but it triggers reviews by tagging `@greptile-apps`, which bypasses Greptile's file-count limit on huge PRs that the plain `@greptile` mention refuses to review. When no check run appears, it falls back to polling Greptile's edited summary comment.

Use it when greploop's trigger gets "Too many files changed for review".

> Local variant derived from greptileai's greploop (MIT, license included in the folder); no separate upstream.

### [new-feature](new-feature/SKILL.md)

Starts every new task in an isolated Git worktree branched from `origin/main` so multiple agents can work on the same repo in parallel without conflicts. It covers unique task naming, a scope check against open PRs, fresh dependency installs, and cleanup after merge.

Use it when:

- Starting any new feature, fix, or task, before writing code
- Multiple agents (or sessions) work the same repository concurrently
- You need a consistent branch-per-task convention with safe cleanup

The current skill includes inherited worktree instructions for Claude Code and Cursor. For other harnesses, inspect the assigned workspace before creating a worktree. Isolated edits do not eliminate integration conflicts between branches.

### [unslop](unslop/SKILL.md)

Edits prose to remove AI tells and put a human voice back in. It names 31 patterns to catch (puffery, filler, hedging, chatbot phrases, em dashes, colons as connectors, bold and emoji overuse, abstract metaphor nouns, passive voice) and a short checklist for adding opinion and rhythm, applied as a four-step loop: scan, rewrite, add soul, self-audit.

Use it when:

- Writing anything a person will read: commit messages, PR titles and bodies, docs, README edits, code comments, chat replies
- Cleaning up existing text that reads machine-made

> Vendored from [cursor/plugins (pstack)](https://github.com/cursor/plugins/tree/main/pstack/skills/unslop) (MIT, license included in the folder). The body matches upstream; the frontmatter has two edits so agents apply the skill on their own instead of waiting for a typed `/unslop`. We dropped the `disable-model-invocation: true` line, and the description now names the trigger (text you write or edit for a human reader) in place of upstream's "any writing. Must always apply.", so auto-invocation matches the scope `AGENTS.md` gives it. Restore the flag if you want slash-command-only behavior.

## Workflow

[`AGENTS.md`](AGENTS.md) is the authoritative workflow for this collection. It connects isolate (`new-feature`), build (`code-structure`), prove (`evidence-driven-testing`) and ship (`greploop`), with `unslop` for human-facing text.

To use it in another project, reference or adapt it alongside that project's existing instructions. Keep project architecture and safety rules authoritative rather than replacing them with this file. Read the workflow and relevant skills instead of pasting an older upstream prompt into each task.

## Installation

Use `npx skills` to install from this fork, selecting the target agent and scope supported by the installer:

```bash
npx skills add sillevl/skills-software-factory
```

Installing skills does not activate the entire delivery workflow. Discovery and automatic invocation depend on the harness and each skill's frontmatter. Review the instructions before enabling them, especially rules that run commands or publish evidence. Installation from upstream remains available through `npx skills add michaelshimeles/skills`.

### Pi-specific usage

Pi can discover user-level skills under `~/.agents/skills/` and project skills under `.agents/skills/`. Project discovery stops at the Git repository root, so a sibling clone is not automatically an installed skill collection. Keep personal skills at user level if they must also be available in new worktrees.

Invoke a discovered skill explicitly with Pi's command syntax:

```text
/skill:new-feature <task>
/skill:code-structure <design question>
```

Run `/reload` after changing installed skills. Set `disable-model-invocation: true` in a skill's frontmatter if you want it available only by explicit invocation; this fork has not changed the bundled frontmatter to impose that choice.

For the full workflow, ask Pi to follow this repository's `AGENTS.md` and supply the task requirements. This fork does not yet provide a `software-factory` wrapper skill. If a skill is not installed, the agent can read its `SKILL.md` from this checkout directly. File-reading instructions are portable; slash commands are not.

See the [Pi instructions in AGENTS.md](AGENTS.md#pi-specific-instructions) and [Pi skill documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md). Editing this clone does not update existing copies in `~/.agents/skills/`.

## Adding a new skill

1. Create a folder named after the skill (kebab-case).
2. Add a `SKILL.md` with `name` and `description` frontmatter. Make the description trigger-focused ("Use when...") so a supporting harness can advertise when the skill applies.
3. Keep instructions concise and actionable; link out to reference files in the folder if they get long.
