# Implementation plan: Genesis research missions

Use existing Genesis cards, watcher, typed plugins, turn stream and experiment gates.
No new dependencies or scheduler. Work in the shared checkout because the necessary
voice/build/report implementations are uncommitted and active; isolate ownership by
file and preserve all unrelated edits. No commit or publication in this task.

## Design

A mission is a research card with server-owned `mission` metadata. The plugin owns
start/status/checkpoint/control operations, current-turn ownership checks, revision
checks, history, continuation and wait reconciliation. Ordinary save_research must
preserve this metadata, never accept model-written replacements. Each experiment is
a distinct card with parent=mission id. Start is idempotent within its originating
conversation turn. The mission pins the initiating model and owner; continuation
must refuse unavailable routes rather than silently selecting a cheap replacement.

Use existing watcher admission and chat reservations. Limit a mission to an explicit
bounded number of worker turns (default 8, maximum 24), also subject to all existing
allowances. No self-extension of that limit. Checkpoint records summary, next action,
status, and optional experiment card; the completion callback queues only explicit
continuation. Waiting on a run invokes no model until its durable state changes.
Recovery blocks uncertain worker actions with inspectable receipts. Stop/steer
invalidate stale worker checkpoints before cooperative cancellation.

Mission tools append protocol explaining the actual available path: inspect evidence,
form falsifiable hypothesis, save/publish experimental architecture, propose/review a
child experiment, wait, read outcomes and author the report. Frozen tasks and held-out
separation remain mandatory. No success claim from a completed conversation alone.

The root integrates card preservation, work routing, proposal parent linkage, watcher
reconciliation, model schemas and protocol. A task-scoped agent implements the isolated
mission module and tests. A separate scoped agent handles receipt-based voice progress
without touching browser controls. Independent final review inspects the combined diff.

## Validation

Test first with existing pytest fixtures and fake provider adapters. Assert persisted
state and refusal behavior rather than implementation presence. Run the narrow mission,
loop, watcher/autonomy, plugin/schema and voice suites; browser checks only for changed
browser behavior. Live microphone/paid benchmark acceptance is separately pending billing
and launch readiness. Never interpret offline fixtures as a real improved architecture.

## Constitution

Settled user brief supplies discovery; unavailable Superpowers uses shared procedures.
Spec and tasks precede code. Tests must fail before implementation. No upstream data,
grading rules, deployment, paid requests, prices or stored results change. Graphify is
absent, so the source audit is the architecture evidence.
