# Feature specification: Live workflows and performance metrics

Date: 2026-09-11. Requested by Lucas. Status: implementation.

## User scenarios and testing

### US1: Watch the work as it happens (P1)
Compare the same task across models in persistent node lanes. Read streamed node
outputs, see a signal travel when an event arrives, and inspect inputs/results.
The Activity tab presents this directly. A task selector changes the comparison.

Acceptance: delivered model/tool/workflow events update the corresponding node
without replacing focused elements or restarting all animations. Pending,
running, completed, failed, skipped and interrupted states remain distinguishable.
Observed event order is explicitly labeled; it never invents data dependencies.
Recorded recipes use their supplied dependencies where available.

### US2: Compare useful outcomes live and in reports (P1)
See task completion time per model beside correctness and spend. As attempts
finish, charts and exact values update from stored results. Expand the metrics
to understand failures, errors, phase time and coverage, then inspect evidence.

Acceptance: show successful-attempt median and p90 with sample counts, failed
attempt time separately, all-attempt operational completion, known spend and cost
per successful task, model turns, tool calls/errors, and unintended changes.
Unavailable values remain unavailable. Live counters never invent progress or
success before grading. Descriptive partial results do not claim a winner.

### US3: Inspect comfortably at any stage (P2)
Pause visual motion without pausing a benchmark, return to current activity,
inspect structured outputs, and use the finished view without replaying old
events as if they were live. Keyboard and phone users retain the same evidence.

Acceptance: reduced motion, hidden tabs, reconnects, empty runs and terminal
errors behave predictably. Tables provide exact alternatives to charts. Updates
do not steal focus or force scroll when the reader is inspecting earlier work.

## Functional requirements

- FR-001: Reuse durable Studio SSE events and original result rows.
- FR-002: Render keyed nodes, bounded output previews, observed-event connectors,
  per-node elapsed timing where supported, and evidence drilldowns.
- FR-003: Animate fresh deliveries only, with a reduced-motion alternative and
  an explicit animation control. Stop loops on hidden/non-Activity surfaces.
- FR-004: Compute report metrics on the server once, shared by live and report
  surfaces; no missing duration or cost may silently become zero.
- FR-005: Separate successful, failed, infrastructure, pending and unrecorded
  attempts; show timing coverage and uncertainty/sample limitations.
- FR-006: Cost per success includes failed/infrastructure spend. If billing is
  unknown, show the known subtotal explicitly and leave total/ratio unavailable.
- FR-007: Show live progress charts with shared scales, exact labels, sample
  counts, and evidence links. Freeze final figures when the run ends.
- FR-008: Add per-model completion time and diagnostics to the persistent report.
- FR-009: Preserve frozen tasks, assertions, configurations, historical results,
  grader semantics, billing gates, and native harness behavior.
- FR-010: Validate entirely offline with recorded/scripted/fake stream evidence;
  no paid benchmark launch or deployment is part of this change.

## Edge cases

Missing/invalid timestamps; zero-duration scripted checks; repeated SSE delivery;
out-of-order terminal data; missing node start; multiple simultaneous tools;
large traces; no successful tasks; unknown billing; running job without recent
events; stale historical task hashes; unsupported recipe dependencies.

## Success criteria

Delivered changes appear within one animation frame after the existing event
batch. Nodes remain stable during deltas. Desktop 1440px and phone 390px have no
page overflow, runtime errors or inaccessible controls. Runnable offline checks
prove exact metrics, no duplicate counts and no invented success or time.

## Assumptions and decisions

The existing Swiss technical manual design is retained. The brief explicitly
requests node animation; this supersedes the older audit suggestion to replace
all node lanes with a list. Side-by-side comparison is the working default;
Lucas was offered the choice while independent investigation proceeded.
Superpowers is not installed on this host; use the shared harness procedure for
brainstorm/spec/plan/tasks, failing tests, task-scoped delegation and review.
The knowledge graph is absent as documented in CLAUDE.md; ground work in code.
