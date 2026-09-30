---
name: code-structure
description: Use when choosing code ownership, designing shared capabilities or refactoring duplicated behavior. Follow the project's architecture before proposing module boundaries or shared abstractions.
---

# Architecture-aware code structure

Improve ownership and reuse within the project's architecture. This skill does
not prescribe an actions/service-layer split, directory layout or language.

## 1. Establish the architectural context

Before designing a boundary, read the target project's `AGENTS.md`, architecture
guides, relevant ADRs and contribution documentation. Follow their links for the
rules affecting this change. Inspect the modules and callers involved.

Identify:

- Who owns the behavior and its product policy.
- Which dependency directions and public interfaces are allowed.
- Where concrete adapters, persistence and composition belong.
- Required lifetime, concurrency, failure and recovery semantics.
- Which contracts are implemented, planned or still undecided.

Project rules take precedence over patterns in this skill. If documentation is
missing, inspect existing code and describe the observed conventions without
calling them an agreed policy. Ask about ambiguity that affects the proposed
boundary. Flag a departure from established architecture before implementation;
get agreement and follow the project's decision-recording process.

Completion: explain the proposed owner, dependencies and public boundary in
project terminology, including any decision that still needs approval.

## 2. Decide whether sharing is justified

Compare callers' semantics, not just similar-looking code. Repeated syntax can
represent different policies and need different owners.

Consider extraction when independent consumers need the same coherent capability
or when a resource owner or test seam has a clear purpose. Multiple callers are
evidence, not an automatic instruction to create a shared service. A single
caller can justify a boundary for resource lifetime or testing; it does not
justify speculative reuse.

Keep behavior local when its meaning belongs to one module. Avoid creating a
shared layer merely because code is hardware-independent or duplicated. Do not
invent future consumers, schemas or requirements to justify an abstraction.

Completion: state why reuse or a new boundary is needed, or why local ownership
is preferable. Identify the real consumers and behavior that must remain stable.

## 3. Design a cohesive contract

- Expose a focused capability rather than a collection of unrelated utilities.
- Make inputs, outputs and dependencies explicit. Avoid hidden global lookup
  where constructor or function injection fits the project's conventions.
- Describe ownership, lifetime, concurrency and failure behavior at the public
  boundary. Include resource limits and partial-success semantics when relevant.
- Keep consumers on the owning module's public interface. Keep implementation
  details and vendor types private where the project requires that separation.
- Put policy with its documented owner. Shared services may own domain policy
  when the architecture assigns it there; they are not necessarily pure mechanics.
- Put storage and SDK access in the designated owner or adapter. Persistence is
  not inherently a design error; bypassing an agreed boundary is.
- Report failures using the project's error conventions. Preserve meaningful
  distinctions instead of swallowing errors or forcing a new result format.

Service-layer extraction is one possible pattern when the project already uses
it or approves it. In that pattern, actions can orchestrate a flow while services
own reusable operations. Do not impose that vocabulary or dependency structure
on a project with different boundaries.

For example, a capability-oriented firmware project may place product outcomes
in features, shared domain capabilities in services, and generic mechanisms in
platform modules, with ports and adapters inside each module. A generic reboot
mechanism can belong in platform while its operator command belongs in a feature.
Use the actual project's rules to decide; this example is not a required layout.

Completion: callers can use the contract without reaching into another module's
private implementation, and the proposal explains the relevant failure semantics.

## 4. Refactor incrementally and verify

1. Identify current behavior and the affected callers. Add or update relevant
   tests as part of the change, following the project's test conventions.
2. Extract one coherent capability into its approved owner.
3. Migrate one caller and review its behavior and dependency changes before
   migrating the rest. Preserve intentional caller-specific policy.
4. Update composition, documentation and decision records where required.
5. Verify under the project's execution and approval policy. This skill does
   not authorize tests. When execution is reserved for the user, provide the
   commands and mark checks unexecuted rather than claiming they passed.

Completion: account for every affected caller, any changed behavior or contract,
verification evidence and remaining unverified checks.

## Review checks

| Warning sign | Question to resolve |
| --- | --- |
| Unrelated operations grouped into one service | Does the module have one coherent owner and purpose? |
| Similar code extracted despite different semantics | Are callers sharing a capability or merely syntax? |
| Consumer reaches into private implementation | Is the public contract sufficient and at the right boundary? |
| Hidden state or unclear failure behavior | Are dependencies and observable outcomes explicit? |
| Abstraction created for hypothetical callers | What current requirement justifies it? |
| Broad refactor bundled with a feature | Can the change be smaller without losing the required behavior? |

Use these checks to review the design, not to override documented architectural
choices or require a wrapper around every function.
