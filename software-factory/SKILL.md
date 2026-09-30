---
name: software-factory
description: Explicitly start the agent-assisted delivery workflow for a supplied task, from isolated implementation through verification and PR handoff.
disable-model-invocation: true
---

# Software factory

Use only when the user explicitly invokes this skill or requests this workflow
by name. It is independent of model provider and coding-agent harness.

1. Read `WORKFLOW.md` in this directory completely. It is the authoritative
   workflow; follow it rather than reconstructing stages from an older prompt.
2. Read the target project's agent instructions and the architecture, branching
   and testing guidance they reference. Resolve task requirements and approval
   conflicts before performing affected operations. Invocation does not override
   project permissions or authorize physical-device access.
3. Follow the workflow for the supplied task. Read the applicable component
   `SKILL.md` files at their stages using paths relative to this directory.
   Components are `../new-feature/`, `../code-structure/`,
   `../evidence-driven-testing/` and `../unslop/`. Install these from the same
   workflow version. If a required component cannot be located, report what is
   missing and ask for direction rather than substituting unrelated instructions.

This entry point routes to the existing rules; it does not duplicate them or
start background sessions. Report verification and outstanding work as required
by the workflow. Merge only with explicit user authorization.
