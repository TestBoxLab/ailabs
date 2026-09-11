# Genesis research missions

Created: 2026-09-11. Owner: Lucas. Status: implementation.

## Settled brief

Lucas asks Genesis by voice or text to diagnose Monarch, build an experimental
architecture, prepare a fifty-task comparison, execute within existing gates,
and analyze results while remaining available for conversation and steering.
This implements the durable coordination missing between features 022, 025,
and 027. It does not promise that a candidate wins or that offline fixtures prove
live audio, provider availability, or scientific improvement.

## User scenarios and acceptance

### US1 — Carry the objective across turns (P1)

One request creates a mission on the existing research board. Its original
request, owner, conversation, objective, acceptance criteria, next action,
checkpoints, model route and bounded turn count survive process reconstruction.
An explicit checkpoint can queue another worker turn; an ordinary answer cannot
silently terminate or endlessly continue the mission. Read-only status remains
available while the worker runs.

### US2 — Build, wait for experiments, and analyze (P1)

The worker uses existing code-reading, architecture edit/save/publish, proposal,
review, evidence and report tools. Experiment cards belong to the mission and
retain independent frozen proposals. Waiting does not consume repeated model
turns. Completion of linked jobs queues analysis once. An approval or missing
record remains visible; an unfinished run cannot be claimed as mission completion.
No new path bypasses allowance, pause, billing, reviewer or human approval gates.

### US3 — Talk, steer, stop and recover (P1)

The conversation can read the current mission and record a correction without
losing its original objective. Stop persists before cancellation; no completion
callback can restart a stopped mission. A restart retains evidence and marks
uncertain in-flight work for reconciliation instead of repeating side effects.
Continuation retains the initiating owner and model identity. Voice emits
bounded progress from actual tool and mission state, with duplicate suppression.

## Requirements

- FR-001: Store missions with existing cards and revision/history mechanisms.
- FR-002: Typed start/status/checkpoint/control tools and authoritative prompt context.
- FR-003: Reuse watcher scheduling; bound continuations and require explicit next work.
- FR-004: Link independent experiment cards; resume from terminal state exactly once.
- FR-005: Enforce stop, pause, ownership, stale revision and recovery boundaries.
- FR-006: Distinguish queued, working, waiting, blocked, stopped and completed work.
- FR-007: Speak progress from receipts, never an invented result or presumed win.
- FR-008: Preserve frozen tasks, grading isolation, native/control identities and budget gates.
- FR-009: Keep the existing UI/editor and avoid unrelated concurrent edits.

## Success criteria

Offline scripted provider integration demonstrates start → checkpoint → worker →
wait → terminal run → analysis, plus steering/stop/restart/error cases. Existing
Genesis focused tests remain green. Live acceptance uses the same spoken scenario
after billing verification, concrete scope/cost disclosure, and applicable approval.

## Scope and assumptions

No provider calls, fifty-task run, deployment, repository push, dataset replacement,
or Monarch merge is authorized implicitly by implementing this capability.
The current brief settles requirements; the shared harness procedures replace
unavailable Superpowers skills. Graphify is absent as documented in CLAUDE.md.
