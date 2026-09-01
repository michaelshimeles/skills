---
name: evidence-driven-testing
description: >
  Records visual proof while testing UI behavior — the agent tests the app
  hands-on via computer use while a screen recording with structured
  test/assertion annotations captures the session — then posts the video and a
  results summary to the PR and tracker issue. Use whenever a change needs
  verifiable evidence that it works, instead of prose claims — including
  headless environments (scripted screenshots and probes) and non-UI changes
  (measured numbers, output pairs).
compatibility: Screen-recording path requires a GUI environment the agent can drive — built-in computer use, or the cua-driver CLI (trycua/cua) when the harness has no computer-use tools — plus an authenticated browser session for the app under test. The bundled recorder (scripts/evidence.py) needs Linux with an X11/XWayland display and ffmpeg + ffprobe built with libx264 and the ass filter; macOS/Windows use cua-driver's recorder or the OS recorder instead. The headless path requires only a running app and a scriptable browser (e.g. Playwright via npx). Posting evidence requires gh (GitHub CLI) or equivalent.
metadata:
  version: "1.1"
---

# Evidence-Driven Testing

Record annotated proof of behavior, then attach it to the PR and tracker issue.

The recording is the capture of you testing the app via computer use: start the
recorder, then drive the app yourself — click, type, navigate — through each
test target. Every action in the video is the test being performed live; the
recording has no value as evidence unless it shows that interactive session.
If the harness has no computer-use tools but a GUI exists, drive the app with
`cua-driver` instead (see below) — it is still your live session.

The bundled recorder, `scripts/evidence.py`, captures the display with FFmpeg,
timestamps each annotation you add while testing, burns them into the video on
stop, and verifies the result with ffprobe. It writes `evidence.mp4`,
`report.md`, and `manifest.json` into the session folder.

## Inputs

- **Test targets** (required): The behaviors/flows to verify, phrased as testable statements.
- **PR / issue** (optional): Where to post the evidence. If omitted, deliver to the requester only.

## The recorder

`EVIDENCE` below means the path to `scripts/evidence.py` inside this skill's
folder (wherever the skill is installed, e.g.
`~/.claude/skills/evidence-driven-testing/scripts/evidence.py`). It needs only
Python 3 and FFmpeg.

- **Check first**: `python3 $EVIDENCE doctor` — verifies `ffmpeg`, `ffprobe`,
  `libx264`, and the `ass` filter, and exits non-zero if anything is missing.
- **Platform**: Linux with an X11 or XWayland display (`--source x11`, uses
  `x11grab`). Pure Wayland denies X11 capture; point `--display` at an
  XWayland display or use a fallback recorder.
- **Fallback recorders** when the bundled one cannot run (macOS, Windows,
  Wayland-only): `cua-driver recording start <dir>` / `stop` (see the
  cua-driver section), or the OS recorder (macOS: `screencapture -v out.mov`).
  On these paths there is no annotation overlay, so keep the annotation
  protocol as files — an `assertions.md` listing each `setup` / `test_start` /
  `assertion` with its result and the approximate video timestamp, exactly as
  in the headless path.
- **Never** present `--source test` (the synthetic pattern generator) as UI
  evidence. It exists to smoke-test the toolchain; the repo's
  `tests/test_evidence.py` exercises it.

## Instructions

### 1. Prepare the screen

- Maximize the browser/app window; close popups, notifications, and extra panels.
- Navigate to the starting state (logged in, correct page) BEFORE recording, unless setup itself is under test.
- Note the exact revision under test: `git rev-parse HEAD` and
  `git branch --show-current` (or the deployment URL) — the recorder stamps
  them into the report.

### 2. Start recording

- Begin the screen recording before the first meaningful action:

  ```bash
  python3 $EVIDENCE start \
    --output .artifacts/<task-name> \
    --source x11 --display "$DISPLAY" --geometry 1920x1080 \
    --title "<what is being verified>" \
    --commit "$(git rev-parse HEAD)" --branch "$(git branch --show-current)" \
    --environment "<browser / display / deployment>"
  ```

  It prints JSON with a `session` path; keep it (`SESSION=...`) for every
  later command. Match `--geometry` to the display size (`xdpyinfo | grep
  dimensions`); add `--xauthority` if the display needs it.
- Add a `setup` annotation describing the starting context:

  ```bash
  python3 $EVIDENCE annotate "$SESSION" --type setup \
    --message "Logged in, navigating to connectors page"
  ```

### 3. Test via computer use, annotating as you go

- Perform every interaction through computer use on the live app — the
  recording captures your session, so the testing and the evidence are the
  same act. Work at a watchable pace: let the UI settle after each action so
  state changes are visible on video.
- At each named test's start, add a `test_start` annotation in Jest style:

  ```bash
  python3 $EVIDENCE annotate "$SESSION" --type test_start \
    --message "It should execute the tool directly when permission is 'always'"
  ```

- After each check, add an `assertion` annotation with `--result passed`,
  `failed`, or `untested`:

  ```bash
  python3 $EVIDENCE annotate "$SESSION" --type assertion --result passed \
    --message "Tool ran without a permission prompt"
  ```

- Rules for assertions:
  - One assertion per meaningful state change — consolidate, don't annotate per UI label.
  - Use "Precondition: ..." assertions to establish starting state.
  - Keep under 80 characters, high-signal (the recorder rejects longer messages).
  - If a test cannot run (missing prerequisite, expired auth window), mark it `untested` with the reason — never skip silently.
  - The timestamp records when you asserted, not whether it was true — look at
    the screen before choosing `passed`.

### 4. Stop and review

- Stop recording after the final assertion:

  ```bash
  python3 $EVIDENCE stop "$SESSION"
  ```

  This ends the FFmpeg capture, burns the annotations into `evidence.mp4`,
  probes the result, and writes `report.md` and `manifest.json` next to it.
  It prints `"verified": true` on success; if rendering fails the session is
  marked `finalization_failed` — fix the reported cause and run `stop` again
  (a retry does not signal the recorder twice). If the recorder process can no
  longer be signalled safely (it died, or its PID now belongs to another
  process), the session is marked `recorder_lost`. Running `stop` again
  finalizes whatever video was captured, but only once that recorder process
  is confirmed gone — if it is still alive, stop it first, or the video would
  be rendered while still being written.
- Confirm the recording captured the key moments before sharing: extract a
  frame at each assertion timestamp (`ffmpeg -ss <t> -i evidence.mp4
  -frames:v 1 frame.png`) and check the state and the label are visible.
- Fill in the Caveats section of `report.md`; never leave the placeholder.

### 5. Post the evidence

- `report.md` is the report: what was tested, environment + exact commit,
  pass/fail per test, caveats. Extend it rather than rewriting from scratch.
- Post the video + summary as a PR comment (embed in the PR description if
  it's your PR). `gh pr comment` cannot attach a local video — upload
  `evidence.mp4` through the PR's comment box in an authenticated browser, or
  upload it to a host and link it (for example the `before-and-after` upload
  adapters). Reopen the comment and confirm the video plays before claiming it
  is posted.
- Attach the same video to the tracker issue (Linear/Jira) with a one-line result.
- Send the report + recording to the requester.

## Guardrails

- The video must show the actual test session being driven live. Never present
  scripted playback, stitched clips, or synthetic footage as a recording; if
  the harness lacks computer-use tools but a GUI exists, drive via
  `cua-driver`; with no GUI at all, use the headless path instead.
- Never record a half-covered or tiled window — maximize first.
- Never record a screen showing secrets, tokens, customer data, or payment
  details; if a flow requires them, mark it `untested` and say why.
- When verifying a fix, show or reference the old failure alongside the new success.
- Always state the exact commit/branch/deployment tested against.

## No computer-use tools? Drive with cua-driver (GUI available)

When a display exists but the agent has no built-in computer-use capability,
use [cua-driver](https://github.com/trycua/cua) (macOS / Windows / Linux) as
the actuator. It is still you testing the app live — the recording rule holds
unchanged; only the input mechanism differs.

- Verify the setup with `cua-driver doctor` before recording. If a
  `cua-driver` skill is installed, read it and follow its protocol — the
  snapshot-before-action invariant is mandatory.
- Loop per interaction: `launch_app` → `get_window_state` (accessibility tree
  + screenshot) → act via `element_token` (`click`, `type_text`, `press_key`)
  → `verify_state` for the expected postcondition. Each `verify_state` check
  maps 1:1 onto an `assertion` annotation.
- On Linux/X11, keep using the bundled recorder above for the video and the
  annotations; cua-driver only supplies the input.
- Elsewhere, `cua-driver recording start <output-dir>` / `cua-driver recording
  stop` is the recorder (the output directory is required, and the daemon
  must be running: `cua-driver serve`). Video capture is on by default and is
  finalized to `<output-dir>/recording.mp4` on stop — but on Windows/Linux it
  shells out to ffmpeg, so a missing ffmpeg or display yields only the
  per-turn trajectory folders (before/after screenshots, `action.json`,
  `click.png`), no video. After stopping, verify `recording.mp4` exists
  before citing it; if it is absent, fix the recorder or present the
  per-turn before/after screenshots as numbered captures per the headless
  protocol.
- If no annotation overlay is available on this path, keep the protocol as
  files: an `assertions.md` listing each `test_start` / `assertion` with its
  result, exactly as in the headless path.

## Headless path (no GUI available)

When the agent has no desktop to record, keep the same assertion discipline;
swap the recorder for scripted capture:

- Save everything to `.artifacts/<task-name>/` (gitignore it — evidence gets
  uploaded, never committed). Keep the capture script beside the captures so
  the run is repeatable.
- **Screenshots**: the `before-and-after` CLI (`@vercel/before-and-after`)
  captures URLs or elements and its pairs feed PR embeds directly. In
  containers/VMs where Chrome fails with "No usable sandbox", set
  `AGENT_BROWSER_ARGS="--no-sandbox"`.
- **Video / multi-step flows**: a one-off Playwright script, run without
  adding playwright to the project's dependencies:

  ```bash
  npx --yes --package=playwright node record.mjs
  ```

  (Plain `npx playwright node record.mjs` fails — `node` is not a Playwright
  CLI command; `--package=playwright` is what puts the module on the path.)
  Minimal `record.mjs`:

  ```js
  import { chromium } from "playwright";
  const browser = await chromium.launch();
  const context = await browser.newContext({
    recordVideo: { dir: ".artifacts/<task-name>/" },
  });
  const page = await context.newPage();
  await page.goto("http://localhost:3000/path-under-test");
  // ...drive the flow, one meaningful state change per step...
  await context.close(); // finalizes the .webm
  await browser.close();
  ```

  Trim or compress with ffmpeg if the file is large.
- **The annotation protocol becomes files**: number captures in test order
  with the assertion in the name — `01-precondition-signed-in.png`,
  `02-it-saves-on-blur-passed.png` — and keep an `assertions.md` in the
  artifacts folder listing each `test_start` / `assertion` with its result
  (`passed` / `failed` / `untested` + reason).

## Non-UI changes still need evidence

- **API / performance**: a scripted probe with measured numbers — request
  counts per phase, latency before/after — captured to `probe-output.txt`.
- **Rendering / canvas / shader**: rendered frames plus pixel assertions
  (diff values), reviewed by eye and saved as PNGs.
- **Agent behavior**: the relevant transcript excerpt showing the tool call
  and response.
- **Bug fixes**: reproduce and capture the failure **before** writing the
  fix — that capture is the "before" half of a before/after pair.

## Capture hygiene

- Confirm the server you're probing is running *your* code (right port,
  right process), especially when multiple agents share a machine:
  `lsof -i :<port>` — or where `lsof` isn't installed,
  `ss -ltnp "sport = :<port>"` to find the listener's PID, then
  `ps -p <pid> -o args=` to confirm it's yours.
- Evidence complements the repo's checks (typecheck/build/tests); it never
  replaces them.
- Hand before/after media pairs to a before/after tool for the PR embed
  (e.g. `before-and-after before.png after.png --markdown`).
