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
compatibility: Screen-recording path requires a GUI environment the agent can drive — built-in computer use, or the cua-driver CLI (trycua/cua) when the harness has no computer-use tools — plus an authenticated browser session for the app under test; the headless path requires only a running app and a scriptable browser (e.g. Playwright via npx). Posting evidence requires gh (GitHub CLI) or equivalent.
metadata:
  version: "1.0"
---

# Evidence-Driven Testing

Record annotated proof of behavior, then attach it to the PR and tracker issue.

The recording is the capture of you testing the app via computer use: start the
recorder, then drive the app yourself — click, type, navigate — through each
test target. Every action in the video is the test being performed live; the
recording has no value as evidence unless it shows that interactive session.
If the harness has no computer-use tools but a GUI exists, drive the app with
`cua-driver` instead (see below) — it is still your live session.

## Inputs

- **Test targets** (required): The behaviors/flows to verify, phrased as testable statements.
- **PR / issue** (optional): Where to post the evidence. If omitted, deliver to the requester only.

## Instructions

### 1. Prepare the screen

- Maximize the browser/app window; close popups, notifications, and extra panels.
- Navigate to the starting state (logged in, correct page) BEFORE recording, unless setup itself is under test.

### 2. Start recording

- Begin the screen recording before the first meaningful action.
- Add a `setup` annotation describing the starting context, e.g. "Logged in, navigating to connectors page".

### 3. Test via computer use, annotating as you go

- Perform every interaction through computer use on the live app — the
  recording captures your session, so the testing and the evidence are the
  same act. Work at a watchable pace: let the UI settle after each action so
  state changes are visible on video.
- At each named test's start, add a `test_start` annotation in Jest style: `It should execute the tool directly when permission is 'always'`.
- After each check, add an `assertion` annotation with result `passed`, `failed`, or `untested`.
- Rules for assertions:
  - One assertion per meaningful state change — consolidate, don't annotate per UI label.
  - Use "Precondition: ..." assertions to establish starting state.
  - Keep under ~80 characters, high-signal.
  - If a test cannot run (missing prerequisite, expired auth window), mark it `untested` with the reason — never skip silently.

### 4. Stop and review

- Stop recording after the final assertion.
- Confirm the recording captured the key moments before sharing.

### 5. Post the evidence

- Write a short report: what was tested, environment + exact commit, pass/fail per test, caveats.
- Post the video + summary as a PR comment (embed in the PR description if it's your PR).
- Attach the same video to the tracker issue (Linear/Jira) with a one-line result.
- Send the report + recording to the requester.

## Guardrails

- The video must show the actual test session being driven live. Never present
  scripted playback, stitched clips, or synthetic footage as a recording; if
  the harness lacks computer-use tools but a GUI exists, drive via
  `cua-driver`; with no GUI at all, use the headless path instead.
- Never record a half-covered or tiled window — maximize first.
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
- `cua-driver recording start <output-dir>` / `cua-driver recording stop` can
  double as the recorder (the output directory is required, and the daemon
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
