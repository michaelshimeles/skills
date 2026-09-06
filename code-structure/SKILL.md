---
name: code-structure
description: Use when multiple workflows duplicate the same operational logic, when deciding what belongs in actions vs shared services, or when refactoring repeated operational blocks across domain flows. Use when adding new features that share mechanics with existing ones.
---

# Service Layer Architecture

## Overview

This collection prefers a two-layer separation: actions orchestrate domain
rules, while services implement reusable operations. Use it where the project
has no established convention. Preserve existing domain services, repositories,
transaction boundaries, and framework patterns when they already fit the task.

This prevents duplicated code, inconsistent behavior, and bugs fixed in one path but not others.

## When to Use

- Multiple callers need the same low-level operation (sandbox creation, email sending, payment processing)
- You're copy-pasting operational logic between action files
- A bug fix in one workflow doesn't propagate to others doing the same thing
- Adding a new feature that shares mechanics with existing flows

Avoid extraction that adds indirection without a concrete benefit. Repetition
is a useful signal, but a single caller can justify a boundary for testing,
provider isolation, transactions, or complex logic.

## Core Pattern

```
Orchestration Layer (Actions)          Service Layer (Shared Mechanics)
├── owns business rules                ├── owns reusable operations
├── owns state transitions             ├── owns provider/SDK interactions
├── owns auth/ownership checks         ├── owns command execution details
├── owns failure classification        ├── owns health checks / readiness
├── owns retries / user-facing errors  └── returns structured results
└── calls service functions
```

**Rule of thumb:**
- "What this product flow means" → keep in actions
- "How to do this operation reliably" → move to service layer

## Quick Reference

| Design Principle | Do | Don't |
|---|---|---|
| API shape | Composable capability blocks | One giant "do everything" method |
| Inputs/outputs | Explicit dependencies and meaningful results | Hidden global state or undocumented side effects |
| Migration | Extract one block, replace one caller, verify, then migrate rest | Refactor everything at once |
| Domain logic | Put policy and transactions in the project's established owner | Scatter the same policy across callers |
| Extraction trigger | Repeated mechanics or a concrete boundary benefit | Speculative abstractions with no current benefit |

## Designing Service Functions

Design as **capability blocks**, not monoliths:

```ts
// Good: composable, each caller chooses what to use
createManagedSandbox(...)
prepareRepo(...)
detectPackageManager(...)
installDependencies(...)
runBuildCommand(...)
startSandboxRuntime(...)
```

Each function should:
- Accept all required data as **explicit parameters**
- Return **structured outputs** (e.g., `{ ready, previewUrl, proxyPort }`)
- Inject database or repository access when the service owns persistence under
  the project's architecture. State writes and transaction boundaries explicitly.
- Make failure explicit through typed results or documented exceptions

This lets callers choose strict vs relaxed behavior per flow.

## Migration Checklist

When extracting shared logic:

1. Identify the existing owners of policy, persistence, and transactions
2. Mark repeated operations or boundaries with a concrete current benefit
3. Extract a cohesive operation consistent with those owners
4. Replace one caller → verify → replace remaining callers
5. Preserve auth, status transitions, error handling, and transaction behavior
6. Run verification: typecheck, lint, confirm all flows still work

## Anti-Patterns

| Anti-Pattern | Problem |
|---|---|
| **God service** | One huge function hides all control flow |
| **Leaky service** | Hidden state changes or unclear transaction ownership |
| **Inconsistent API** | Each function uses different argument styles and error semantics |
| **Over-abstraction** | Indirection with no reuse, testability, or boundary benefit |

## Example: Email Service (Simple)

```ts
// emailService.ts — shared mechanics
export async function sendWelcomeEmail(params: { to: string; name: string }) {
  const html = `<h1>Welcome ${params.name}</h1>`;
  await emailProvider.send(params.to, "Welcome", html);
}

// userSignup.ts — orchestration (owns WHEN to send)
if (user.marketingOptIn) {
  await sendWelcomeEmail({ to: user.email, name: user.name });
}

// adminInvite.ts — orchestration (different business rule, same mechanic)
await sendWelcomeEmail({ to: invitee.email, name: invitee.name });
```

## Mental Model

```
Existing architecture? → Follow its boundaries
No convention? → Prefer actions for orchestration and services for operations
Extraction? → Name its concrete benefit before adding another layer
```

Keep responsibilities clear, dependencies explicit, and side effects visible.
