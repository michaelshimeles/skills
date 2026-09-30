---
name: evidence-driven-testing
description: Plan, add and report software tests for changed behavior. Use when implementing features, fixing bugs, refactoring or preparing verification for review. Follow the project's test-execution policy and distinguish observed results from reported or unexecuted checks.
metadata:
  version: "2.0"
---

# Software-test verification

Use software tests to check acceptance criteria and prevent regressions. This
skill does not require screenshots, recordings, a browser or public uploads.
Use the project's test frameworks and maintained commands rather than imposing
a new stack.

## 1. Establish scope and execution policy

Read the target project's `AGENTS.md`, testing documentation and relevant
acceptance criteria. Inspect existing suites, fixtures and test boundaries.
Resolve missing acceptance criteria that would change the assertions before
inventing product behavior.

Identify who may execute checks, which commands have standing project permission,
which require per-run approval, and any constraints on hardware, credentials,
network services, cost or shared resources. Use documented standing permission
without asking again for each permitted run, unless task instructions narrow it.
Invoking this skill alone is not authorization. Ask about missing or ambiguous
permission before executing the affected checks. Restrictions also apply to
commands that invoke tests or device operations indirectly.

Keep permission rules in the target project's agent instructions and commands,
prerequisites and suite-selection guidance in its maintained testing documents.
This generic skill does not prescribe project-specific suite names or declare
that all hardware-free checks are automatically permitted.

Completion: identify the behavior to verify, the relevant suites and the allowed
execution path. Disclose prerequisites that are missing or not yet authorized.

## 2. Select meaningful tests

Map each changed acceptance criterion to an existing test or a test to add.
Include normal behavior, relevant boundaries, failure paths and recovery where
they are part of the contract. For refactors, preserve intentional behavior and
account for affected callers.

Use the smallest test boundary that proves the requirement:

- Unit or module tests for deterministic policy, parsing and state transitions.
- Integration tests for real module contracts, persistence and transport behavior.
- End-to-end tests for critical cross-system paths that smaller tests cannot prove.

These are choices, not a requirement to add every test level to every change.
Follow project ownership rules and keep tests with the capability they exercise.
Use controllable dependencies where appropriate without adding production hooks
that violate architectural boundaries.

For firmware, host and emulated tests can verify software without proving physical
signals or radio behavior. For a TUI, state-transition, input-handling, terminal
output and snapshot assertions can verify behavior without a screen recording.
State the limits of fakes, snapshots and emulation; do not treat them as proof of
a physical property or all visual usability.

Completion: every changed criterion has a test or an explicit verification gap.
Choose expected outcomes from the contract, not merely from current output.

## 3. Add or update tests

Use existing naming, fixtures, assertion style and runner conventions. Assert
observable behavior and failure semantics rather than incidental implementation
details. Keep fixtures deterministic and redact sensitive values.

For a bug fix, add a focused regression test. When execution is authorized,
confirm it demonstrates the old failure before verifying the fix where practical.
If that run was not performed, say so; a newly written test is not proof that it
failed on the old code or passed on the new code.

Avoid broad suite rewrites, unrelated dependency changes and speculative cases.
Do not weaken assertions or change expected outcomes merely to obtain a pass.

Completion: the relevant test changes are ready, and any excluded behavior or
needed manual validation is identified.

## 4. Execute or hand off

Use commands from maintained project documentation or build configuration.
Select builds as well as tests when changed code, dependencies or composition
need compilation checks. A host test build may not compile production-only code.
Follow project guidance for the production build and other applicable checks;
software testing does not replace compilation, lint or static analysis. Report
these check types separately.

- When permitted by standing project policy or explicit authorization, run the
  selected checks against the intended workspace and revision. Record exact
  commands, working directory, environment, results and relevant output or
  artifact locations. Choose checks for changed behavior and integration risk
  rather than automatically running every suite for every edit.
- When execution is reserved for the user or approval is missing, provide the
  selected commands, prerequisites and what each verifies. Mark them unexecuted
  and wait for results where delivery depends on them.
- If a command cannot start, mark it blocked and explain the prerequisite. If it
  runs and fails, report the failure even when the cause appears environmental.
  An attempted run that produces no reliable result is incomplete, not passed.
- Investigate failures within task scope and rerun only within authorization.
  Preserve evidence of failures and retries; disclose intermittent behavior.
- Investigate introduced compilation errors and new warnings before handoff.
  Distinguish existing diagnostics from newly introduced ones. Report unresolved
  diagnostics; do not suppress them merely to obtain a clean result.

Confirm results apply to the tested state. Record the commit and whether relevant
changes were uncommitted, using a diff or artifact identifier when needed. A result
from an earlier revision is historical evidence, not verification of later edits.
Integration or rebasing may require renewed checks under the same project policy.

Completion: each selected check has a result or a stated reason it remains
unexecuted, blocked or incomplete.

## 5. Report verification honestly

Include a concise verification summary in the task handoff or PR. Publishing is
subject to task permissions; this skill does not authorize posting or uploading.
Use existing project artifact conventions. Do not add a new report system or
commit generated logs unless the project calls for it.

Record for each check:

| Field | What to record |
| --- | --- |
| Criterion / check | Behavior covered and suite or test selection |
| Tested state | Commit, relevant uncommitted changes and working directory |
| Command / environment | Exact invocation and relevant tools, emulation, services or target |
| Result | Passed, failed, unexecuted, blocked or incomplete; counts only when observed |
| Source | Agent-observed, user-reported or CI-observed |
| Evidence / limits | Relevant output or artifact reference, skipped cases and what the check cannot prove |

Keep provenance separate from outcome. If the user reports a pass, label it
user-reported; do not claim the agent observed it. Preserve the reported scope.
If the user says "all tests" without commands or suite details, record that
ambiguity or ask for clarification rather than silently translating it to one
suite. For CI, identify the relevant run and revision, and check whether suites
were skipped before making coverage claims.

A successful build is not a passing test suite. A passing suite does not prove
unexecuted hardware checks. Do not invent test counts, coverage percentages or
before/after results. Redact secrets from logs and reports before sharing them.

Completion: a reviewer can tell what was tested, on which state, by whom, with
what outcome, and what remains unverified. Report unresolved gaps; do not silently
change acceptance criteria or declare them satisfied.
