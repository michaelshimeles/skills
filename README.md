# Skills

A collection of [agent skills](https://code.claude.com/docs/en/skills) for Claude Code. Each skill is a folder containing a `SKILL.md` with frontmatter (name, description) and instructions that Claude loads on demand when the task matches.

## Available skills

### [before-and-after](before-and-after/SKILL.md)

Captures before/after screenshots of web pages or elements and outputs a PR-ready markdown comparison table. It drives the `@vercel/before-and-after` CLI.

Use it when:

- A PR needs visual proof that a UI change does what it claims
- You want a `| Before | After |` table generated and uploaded in one step
- Comparing two URLs, two existing images, or a mix of both

> Vendored from [vercel-labs/before-and-after](https://github.com/vercel-labs/before-and-after) (PolyForm Shield 1.0.0, license included in the folder). Install the CLI with `npm i -g @vercel/before-and-after agent-browser`.

### [code-structure](code-structure/SKILL.md)

Service layer architecture guidance. Prefers actions for orchestration and
services for reusable operations when a project has no established convention.
Preserves existing persistence and transaction boundaries, and permits a
single-caller abstraction when it provides a concrete benefit.

Use it when:

- Multiple workflows duplicate the same operational logic
- You're deciding what belongs in actions vs. shared services
- A bug fix in one flow doesn't propagate to others doing the same thing
- Adding a feature that shares mechanics with existing ones

Includes a migration checklist for extracting shared logic without changing policy or transaction behavior.

### [evidence-driven-testing](evidence-driven-testing/SKILL.md)

Records visual proof while testing UI behavior. The agent drives the app live via computer use (or [cua-driver](https://github.com/trycua/cua) when the harness has no computer-use tools) while the bundled recorder captures the session, then posts the video and a results summary to the PR and tracker issue. The recorder (`scripts/evidence.py`, Python 3 + FFmpeg) runs on Linux, macOS, and Windows and has `doctor`, `start`, `annotate`, and `stop` commands. It timestamps each annotation as the agent tests, burns them into `evidence.mp4` on stop, and summarizes them in a generated `report.md` and `manifest.json`. Headless environments swap the recorder for scripted screenshots and Playwright captures; non-UI changes still get evidence (measured numbers, output pairs, transcript excerpts).

Use it when changed runtime behavior needs observable verification. Documentation-only work needs content checks and verification of runnable examples.

> The recorder needs `ffmpeg`/`ffprobe` with `libx264` and the `ass` filter, plus a supported desktop capture source. Run `python3 scripts/evidence.py doctor` from the skill directory to check availability. The headless helper, `scripts/run-playwright.sh`, uses Node and npm to install Playwright beside a self-contained capture script in a temporary directory. It keeps dependencies out of the target project. Posting evidence requires an authorized destination and the relevant upload tool.

### [greploop](greploop/SKILL.md)

Addresses Greptile feedback on a PR, MR, or shelved changelist. Targets a fresh
5/5 review of the current revision with no unresolved actionable findings,
within `--max-iterations` cycles, default 10. Stops and reports partial results
at the cap, on timeout, or when the integration cannot verify the revision.
The GitHub helper records each trigger and rejects stale checks and summaries.

Use it to get a PR to a clean Greptile review before merge.

> Vendored from [greptileai/skills](https://github.com/greptileai/skills) (MIT, license included in the folder). Requires Greptile installed on the repo and an authenticated `gh`/`glab`/`p4` CLI.

### [greploop-apps](greploop-apps/SKILL.md)

A compatibility entrypoint for `greploop --trigger @greptile-apps`. It uses
the same workflow and tested GitHub helper, including summaries that update
without a new check run. Install it together with `greploop`.

Use it when greploop's trigger gets "Too many files changed for review".

> Local entrypoint derived from greptileai's greploop. MIT license included.

### [new-feature](new-feature/SKILL.md)

Isolates repository edits in a Git worktree based on `origin/main`, while
preserving a worktree already assigned to the task. It checks whether overlapping
PRs conflict in behavior, allows independent edits, and leaves other tasks'
work untouched. Read-only reviews and investigations need no new worktree.

Use it when:

- Starting a feature, fix, or documentation edit
- Multiple agents (or sessions) work the same repository concurrently
- You need a consistent branch-per-task convention with safe cleanup

Checks actual worktree ownership instead of assuming the editor created one.

### [unslop](unslop/SKILL.md)

Edits prose to remove AI tells and put a human voice back in. It names 31 patterns to catch (puffery, filler, hedging, chatbot phrases, em dashes, colons as connectors, bold and emoji overuse, abstract metaphor nouns, passive voice) and a short checklist for adding opinion and rhythm, applied as a four-step loop: scan, rewrite, add soul, self-audit.

Use it when:

- Writing anything a person will read: commit messages, PR titles and bodies, docs, README edits, code comments, chat replies
- Cleaning up existing text that reads machine-made

> Vendored from [cursor/plugins (pstack)](https://github.com/cursor/plugins/tree/main/pstack/skills/unslop) (MIT, license included in the folder). The body matches upstream; the frontmatter has two edits so agents apply the skill on their own instead of waiting for a typed `/unslop`. We dropped the `disable-model-invocation: true` line, and the description now names the trigger (text you write or edit for a human reader) in place of upstream's "any writing. Must always apply.", so auto-invocation matches the scope `AGENTS.md` gives it. Restore the flag if you want slash-command-only behavior.

## Workflow

[`AGENTS.md`](AGENTS.md) selects the applicable steps for each task: isolate
edits, follow the project's architecture, verify the changed behavior, and ship
when the task calls for it. Read-only work skips shipping; small documentation
edits use content checks. Code and executable workflow changes use a bounded
Greptile review loop. Apply `unslop` to prose you write or edit along the way.

## Installation

Clone the repo and copy (or symlink) a skill folder into your skills directory:

```bash
# Available in all projects
cp -r code-structure ~/.claude/skills/

# Or scoped to a single project
cp -r code-structure /path/to/project/.claude/skills/
```

Claude Code picks up the skill automatically and invokes it when a task matches the skill's description. You can also invoke one explicitly with `/code-structure` or `/evidence-driven-testing`.

The alternate Greptile entrypoint requires both folders:

```bash
cp -r greploop greploop-apps ~/.claude/skills/
```

## Checks

Run `python3 -m pytest tests/ -q` and `git diff --check`. The recorder tests
require Python 3.10+, pytest, ffmpeg, and ffprobe with libx264 and the ass filter.
Workflow tests cover review freshness, polling, and isolated Playwright module
resolution. The Playwright runner tests require Node and Bash and stub npm
downloads. For changes to that helper, also run a real Chromium capture using
the documented command. These local tests do not exercise live upload hosts
or every native desktop capture backend.

## Adding a new skill

1. Create a folder named after the skill (kebab-case).
2. Add a `SKILL.md` with `name` and `description` frontmatter. The description is what Claude uses to decide when the skill applies, so make it trigger-focused ("Use when...").
3. Keep instructions concise and actionable; link out to reference files in the folder if they get long.
