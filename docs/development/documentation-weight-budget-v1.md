# Documentation weight budget v1

## Purpose

Project archives are part of the development loop: they are uploaded to ChatGPT, copied between workspaces and inspected by humans. Documentation is valuable only while it keeps that loop cheap. This document sets the rule for future documentation growth.

## Budget

Target for normal devctl post-archives: **stay comfortably below 1 MiB** while the project is still in active conversational development.

The budget is not a hard product limit. It is an operating constraint for this phase: small archives make patch review, upload, rollback and cross-machine diagnostics faster.

## Rules

1. **No duplicate manifestos.** A new strategic document may be long while the idea is being designed, but after the decision is accepted it should be compacted into: decision, scope, invariants, risks, exit criteria.
2. **One source of truth per topic.** Phase notes should point to the canonical plan instead of repeating the whole plan.
3. **Keep evidence out of source archives.** `.dev-bootstrap/`, run logs and diagnostic bundles are generated artifacts. They belong in per-run bundles, not in project snapshots.
4. **Prefer tables and checklists over prose loops.** Keep rationale, but remove repeated persuasion after the decision is locked.
5. **Do not compress executable contracts.** OpenAPI, migrations, source code and machine-readable schemas are not prose bloat.
6. **Keep removal reversible.** Historical detail can be recovered from Git history or old devctl archives; current docs should optimize for the next developer decision.

## Compact document template

Use this structure for long-lived docs:

```text
# Title

## Decision
## Scope
## Current implementation
## Commands / contracts
## Risks
## Exit criteria
## Pointers
```

## Current compaction milestone

This patch compacts the repeated stabilization/devbootstrap narrative and removes generated `.dev-bootstrap` run artifacts from source snapshots. Runtime code is not changed except for devctl archive exclusions.
