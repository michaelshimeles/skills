---
name: code-structure
description: Use when multiple workflows duplicate the same operational logic, when deciding what belongs in actions vs shared services, or when refactoring repeated operational blocks across domain flows. Use when adding new features that share mechanics with existing ones.
---

# Service Layer Architecture

## Overview

**Two-layer separation:** Actions orchestrate domain rules (the "why/when"), while a service layer centralizes reusable operational mechanics (the "how").

This prevents duplicated code, inconsistent behavior, and bugs fixed in one path but not others.

## When to Use

- Multiple callers need the same low-level operation (sandbox creation, email sending, payment processing)
- You're copy-pasting operational logic between action files
- A bug fix in one workflow doesn't propagate to others doing the same thing
- Adding a new feature that shares mechanics with existing flows

**Don't use when:** Logic is truly domain-specific and used by only one caller.

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
| Inputs/outputs | Explicit params, structured returns | Hidden global state, reaching into DB |
| Migration | Extract one block, replace one caller, verify, then migrate rest | Refactor everything at once |
| Domain logic | Keep auth, policy, error classification in actions | Let service mutate domain state directly |
| Extraction trigger | Logic repeated across 2+ callers | Logic used once (over-abstraction) |

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
- Never reach into database/state directly
- Make failure explicit (structured results, not swallowed errors)

This lets callers choose strict vs relaxed behavior per flow.

## Migration Checklist

When extracting shared logic:

1. Write the flow in action code first (clear behavior)
2. Mark repeated operational chunks across callers
3. Extract **only** repeated, non-domain chunks to service
4. Replace one caller → verify → replace remaining callers
5. Keep domain policy in actions (auth, status transitions, error classification)
6. Run verification: typecheck, lint, confirm all flows still work

## Anti-Patterns

| Anti-Pattern | Problem |
|---|---|
| **God service** | One huge function hides all control flow |
| **Leaky service** | Service mutates database tables directly |
| **Inconsistent API** | Each function uses different argument styles and error semantics |
| **Over-abstraction** | Extracting logic used by only one caller |

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
New feature? → Write in action first → See repeated ops? → Extract to service
                                      → No repetition?  → Keep in action
```

Your architecture in one sentence: **Actions orchestrate domain rules, while the service layer centralizes reusable operational mechanics with a composable, explicit-input API.**
