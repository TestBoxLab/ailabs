# Feature Specification: Monarch in Run-Only Mode

**Feature Branch**: `004-monarch-run-only`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Feature 004: Monarch in run-only mode. Single source: docs/superpowers/specs/2026-09-04-monarch-run-only-design.md (approved 4 Sep; do not relitigate its §2 decisions). Run-only is defined in monarch-benchmark/PLAN.md §1.4 as 'a known-correct workflow, engine measured alone'. Known-correct = a workflow Monarch authored once, off the clock, that passed the bench's checker. New paid setup command `wb monarch recipes`; a recipes file per product; the competitor skips authoring and runs the fixed workflow without deleting it; drift and missing recipes refuse or exclude; new plan pilot-monarch-run-only. English, plain names (competitor, task set, attempt, approval rule, answer key, product under test)."

**Design of record**: `docs/superpowers/specs/2026-09-04-monarch-run-only-design.md`
(approved 4 Sep 2026 by Carlos). This spec restates that design as requirements;
it does not reopen the decisions in its §2.

## Why

Feature 002 made Monarch a competitor in **create + run** mode: it turns the
request into a workflow and runs it, both on the clock. When such an attempt
fails, the row cannot say whether the workflow was wrong or the engine was.

**Run-only** separates the two. `monarch-benchmark/PLAN.md` §1.4 defines it as
"a known-correct workflow, engine measured alone": the workflow is handed to
Monarch already built, off the clock, and only the execution is timed, priced
and graded. It answers the narrower question underneath create + run — given a
workflow that is already correct, does the engine execute it correctly, how
fast, and at what cost — and it is the mode a Monarch release-over-release
comparison will use.

**Known-correct** has one meaning here, and it is not "a person said so": a
workflow Monarch itself authored once, off the clock, whose run **passed the
bench's checker** against a fresh copy of the product under test. The task's
approval rules decide; nothing grades itself (rule 3).

The deliverable is a paired pilot on the simulated product: 10 tasks, 2
repetitions, seven competitors, internal report. It is deliverable D9 in
`PLAN.md`.

None of the fixed rules in `PLAN.md` §1 change. The feature adds inputs (a
recipes file, a plan, one mode on the product and the harness) and one setup
command. Create + run is untouched.

### What is being compared, plainly

Rule 2 says "same knowledge **within a test mode**". In run-only the two sides
are deliberately not doing the same work, and the report must not read as if
they were:

- **Monarch** is given a workflow that is already known to be correct. Only its
  engine runs.
- **The raw models** get the same request text and the same three tools they
  always get, and do the whole task themselves. There is no fixed workflow to
  hand them.

So a run-only figure is "Monarch's engine alone against models doing the whole
task", not a like-for-like race. That sentence belongs on the report's source
line, and this feature puts it there.

## Vocabulary

Plain names are used throughout, in files and in this spec:

| Plain name | Meaning |
|---|---|
| competitor | one model + harness pair, or a harness alone; here `monarch@<version>` |
| task set | a folder of task requests with their approval rules; here the 10 pilot tasks |
| attempt | one task, one competitor, one repetition |
| approval rule | what must change and what must not, checked after the attempt |
| answer key | the scripted competitor that always does the task right |
| product under test | the platform the competitors operate; here the 47 simulated apps |
| test mode | how much of Monarch is under test: full flow, create + run, or run only |
| knowledge base | the description of the 47 apps that Monarch is given before the clock starts |
| recipe | the workflow Monarch keeps for one task: what run-only executes |
| known-correct recipe | a recipe whose run passed the checker when it was made |
| front door | the bench's HTTP server that exposes a fresh copy of the apps to Monarch for one attempt |
| execution | Monarch's engine running the recipe against the front door |
| drift | Monarch no longer holds what the run was frozen with |
| infrastructure failure | a failure the bench or its environment caused, not the competitor; retried and excluded from the denominator |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Prepare one known-correct recipe per task (Priority: P1)

Before the first run-only pilot, Carlos runs `wb monarch recipes`. The command
states how many tasks it will work on and a cost band, and refuses to start
without an explicit yes. For each task it lets Monarch author a workflow and run
it against a fresh copy of the apps, up to three times; the **bench's checker**
grades each result, and the first workflow that passes is kept inside Monarch
and recorded. Workflows that failed are deleted. A task that never passes is
recorded as missing, with the reason. Running the command again works only on
the tasks that still have no recipe.

**Why this priority**: Without recipes there is no run-only mode. The command is
the only thing in this feature that spends model money, so its gate and its
idempotence come first.

**Independent Test**: With a fake Monarch scripted to fail twice and pass on the
third authoring, run the command on three tasks (one passes first, one passes
third, one never passes) and confirm the recipes file, the deletions, the
missing row, and that a second run makes no authoring request at all.

**Acceptance Scenarios**:

1. **Given** a task set and a knowledge base, **When** the command runs, **Then**
   it first prints the number of tasks it will work on, the maximum number of
   authoring attempts and a cost band, and stops without starting unless an
   explicit yes was given on the command line or the named plan carries an
   approval.
2. **Given** an approved command, **When** it works on one task, **Then** Monarch
   authors a workflow from that task's request text, runs it against a fresh copy
   of the apps, and the bench's checker grades the resulting snapshot against the
   task's approval rules.
3. **Given** the checker passes, **When** the task is recorded, **Then** the
   workflow is left in place inside Monarch and the recipes file gains a row with
   the task, the workflow, its recipe version, the fingerprint of the
   knowledge-base file it was made against, when it was authored, and how many
   attempts it took.
4. **Given** the checker fails, or authoring fails, or the run fails, **When** the
   attempt closes, **Then** the workflow created by that attempt is deleted and
   another attempt starts, up to the limit.
5. **Given** the limit is reached with no pass, **When** the task is recorded,
   **Then** it is marked missing with the reason of the last attempt, and no
   workflow is left behind for it.
6. **Given** a recipes file that already covers some tasks for the current
   knowledge base, **When** the command runs again, **Then** those tasks are
   skipped with no model call, and only the missing ones are attempted.
7. **Given** the knowledge base has changed since the file was written, **When**
   the command runs, **Then** every recipe is treated as out of date and remade,
   because a recipe built against a different knowledge base is a different
   recipe.

---

### User Story 2 - Run the run-only pilot (Priority: P1)

Carlos runs the run-only plan. Every competitor receives the same request text
for each task. Monarch does no authoring: it runs the task's known-correct
recipe against a fresh copy of the apps, the bench snapshots the result, and the
checker grades it later. The recipe is not deleted; it is reused by every
repetition. The report shows Monarch beside the raw models, paired on identical
task sets, with error bars and source lines, and states plainly what run-only
compares.

**Why this priority**: This is the feature. Deliverable D9 is exactly this pilot.

**Independent Test**: With a fake Monarch holding a fixed workflow whose engine
calls satisfy each task, run the plan offline and confirm every Monarch attempt
sent no authoring request, produced a stored snapshot the checker grades, left
the workflow in place, and recorded an execution phase but no authoring phase.

**Acceptance Scenarios**:

1. **Given** a plan whose mode is run-only and whose competitors include Monarch,
   **When** the run starts, **Then** it states the number of attempts and the cost
   ceiling and refuses without approval above smoke scale, exactly as any other
   plan does.
2. **Given** one Monarch attempt in run-only, **When** it runs, **Then** no
   authoring request is made, the task's recorded recipe is executed, and the row
   records the workflow, the run and the recipe version.
3. **Given** one Monarch attempt, **When** it finishes normally, **Then** the
   stored snapshot is the state of that fresh copy of the apps after the engine
   ran, taken by the bench, and the checker grades it later from that snapshot
   alone.
4. **Given** any Monarch attempt in run-only, **When** it closes, **Then** the
   recipe is still in Monarch: nothing in this mode deletes a workflow.
5. **Given** a completed attempt, **When** the row is read, **Then** it carries an
   execution phase with wall-clock and cost, and carries **no authoring phase at
   all** — an absent phase, not a zero one.
6. **Given** the plan's concurrency is greater than one, **When** the run
   executes, **Then** at most one Monarch attempt is in flight at any moment,
   while the other competitors keep their concurrency.
7. **Given** a completed pilot, **When** the internal report is produced, **Then**
   Monarch and the baseline raw model are compared pairwise on identical task
   sets with error bars, and every figure carries its source line.
8. **Given** any run-only report, **When** it is read, **Then** its source line
   states that Monarch executed a fixed known-correct workflow while the raw
   models did the whole task, so the figures are not a like-for-like race.

---

### User Story 3 - Refuse on drift, exclude what is missing (Priority: P1)

A run-only run is only meaningful if Monarch still holds exactly the recipes the
run was frozen with, made against exactly the knowledge base it was frozen with.
Before the first Monarch attempt the bench checks both. Any difference refuses
the run and names what changed. Tasks with no recipe are removed from the task
set of **every** competitor, and the report says how many were removed and why.

**Why this priority**: Rule 11 (config hash; a changed input is a different run)
and rule 7 (paired comparisons only on identical sets). Without this the pilot's
numbers can be wrong in a way nobody would notice.

**Independent Test**: With a fake Monarch that reports a different recipe version
for one task, and a second scenario where the workflow is gone, confirm the run
stops before any run request and names the task; then with a recipes file
carrying two missing tasks, confirm every competitor runs eight tasks and the
report says two were excluded.

**Acceptance Scenarios**:

1. **Given** a plan with Monarch in run-only, **When** the recipes file is
   missing, **Then** the run refuses before any attempt and tells Carlos to run
   the recipes command.
2. **Given** a recipes file, **When** the run starts, **Then** before the first
   Monarch attempt the bench asks Monarch about each recorded workflow and
   refuses if any is gone or reports a different recipe version, naming the task
   and both versions.
3. **Given** a recipes file, **When** the run starts, **Then** it also refuses if
   the knowledge-base file's fingerprint differs from the one the recipes were
   made against, saying that the recipes must be remade.
4. **Given** a recipes file with tasks marked missing, **When** the run starts,
   **Then** those tasks are excluded from the task set of every competitor, not
   only Monarch's, and the run states how many were excluded before it begins.
5. **Given** such a run, **When** the report is produced, **Then** its source line
   states the number of tasks excluded and the reason each was excluded.
6. **Given** the recipes file changes in any recorded field, **When** a run is
   started, **Then** the run's configuration fingerprint differs from a run
   started with the previous file, so resuming across the change refuses.
7. **Given** every task in the task set is missing a recipe, **When** the run
   starts, **Then** it refuses rather than run an empty comparison.

---

### User Story 4 - Read the updated plan and configuration (Priority: P3)

Carlos opens `monarch-benchmark/PLAN.md` and sees work item B6 pointing to
feature 004, D9's definition of done written out, the new decisions recorded and
this feature's open questions listed. He opens the project instructions and the
configuration README and finds the recipes file, the new plan and the new
command explained in plain words.

**Why this priority**: PLAN.md is the single tracking surface. Docs that lag the
code make the next handoff wrong.

**Independent Test**: Read the four documents and tick the items below.

**Acceptance Scenarios**:

1. **Given** PLAN.md, **When** read, **Then** B6 references feature 004, D9's
   definition of done names the recipes command, the excluded-task rule and the
   engine-only phases, the decisions log carries the two decisions of this
   feature, and the open questions carry the three below.
2. **Given** the configuration README and the config-file contract, **When**
   read, **Then** the recipes file, the run-only plan and the new mode on the
   product and the harness are documented with an example.
3. **Given** the project instructions, **When** read, **Then** the "What lives
   where" table names this feature's folder and the status paragraph says where
   feature 004 stands.

---

### Edge Cases

- **A run is already in flight on the recipe** when an attempt starts (a leftover
  from a previous attempt that hit its deadline; there is no way to cancel a run).
  The bench waits for that run to reach a terminal state, up to a bound; if it is
  still going, the attempt ends as an infrastructure failure and is retried.
- **The deadline passes during a run-only attempt.** The attempt ends as a
  timeout and the run is left in flight — the workflow must not be deleted,
  because it is the recipe every later attempt needs. The next attempt's wait
  (above) is what clears it.
- **The recorded workflow is gone from Monarch** when an attempt starts: an
  infrastructure failure that is not worth retrying, naming the task and telling
  Carlos to remake the recipes.
- **The recipes command is interrupted** partway: the tasks already recorded keep
  their rows, and a rerun continues from there. It never writes a partial row.
- **A recipe passes the checker when made but fails on every later attempt.** That
  is a result, not an error: the row is a normal failure and the report shows it.
  The engine being unreliable on a workflow that once worked is exactly what
  run-only exists to detect.
- **Two Monarch attempts are scheduled at once**: the second waits for the lock,
  and its own deadline starts when it acquires it, as in create + run.
- **A task's request text changes** after its recipe was made: the task's own
  fingerprint changes, which already makes old rows non-regradable (rule 5); the
  recipe is remade with the task.
- **Cost cannot be read for a run-only attempt**: cost is zero and the row is
  flagged, the verdict stands, and the share of attempts with missing cost is on
  the report's source line — as in create + run.

## Requirements *(mandatory)*

### Functional Requirements

**Making the recipes (`wb monarch recipes`)**

- **FR-001**: The bench MUST provide a command that produces at most one
  known-correct recipe per task of a task set, for one product under test and one
  knowledge base.
- **FR-002**: A recipe is known-correct only if Monarch authored it and the run of
  that workflow, graded by the bench's checker from the bench's own snapshot
  against the task's approval rules, **passed**. No other definition may be used.
- **FR-003**: The command MUST make each authoring attempt through the same
  create + run flow the create + run competitor uses, on a fresh copy of the
  product under test, so the recipe is the product's own work.
- **FR-004**: The command MUST try up to a configurable number of attempts per
  task, three by default, and MUST keep the first workflow that passes.
- **FR-005**: The command MUST delete every workflow that did not pass, and MUST
  leave the kept workflow in place inside Monarch.
- **FR-006**: The command MUST record, per kept recipe: the task, the workflow,
  its recipe version, a fingerprint of the knowledge-base file it was made
  against, when it was authored, and how many attempts it took.
- **FR-007**: The command MUST record a task with no passing recipe as missing,
  with the reason of the last attempt.
- **FR-008**: Because the command spends model money, it MUST print the number of
  tasks, the attempt limit and a cost band, and MUST NOT start without an explicit
  yes on the command line or an approval on the plan it was given.
- **FR-009**: The command MUST be idempotent: a task that already has a recipe for
  the current knowledge base is skipped with no model call.
- **FR-010**: When the knowledge base differs from the one recorded in the file,
  the command MUST treat every recipe as out of date and remake it.
- **FR-011**: The command SHOULD give each kept workflow a name that identifies
  its task inside Monarch. Monarch offers no route to rename a workflow today (see
  Open Questions), so the name is recorded on the bench side and the command MUST
  say so rather than claim a rename it did not perform.

**The competitor in run-only mode**

- **FR-012**: In run-only mode the Monarch competitor MUST NOT author anything: it
  executes the task's recorded recipe and nothing else.
- **FR-013**: The request text MUST still be identical for every competitor for a
  given task (rule 1); in run-only it is what the recipe was authored from, and
  the raw models receive it directly.
- **FR-014**: Each run-only attempt MUST operate on a fresh copy of the product
  under test, exposed to Monarch through the bench's front door, as in create +
  run.
- **FR-015**: The stored snapshot MUST be the state of that fresh copy after the
  engine ran, taken by the bench, never reported by Monarch (rule 3).
- **FR-016**: A run-only attempt MUST NOT delete the workflow, whatever its
  outcome.
- **FR-017**: A run-only row MUST carry an execution phase with its own wall-clock
  and its cost, and MUST NOT carry an authoring phase at all.
- **FR-018**: Before starting a run, if a run is already in flight on that
  workflow the bench MUST wait for it to reach a terminal state up to a bounded
  time, and only then treat the refusal as an infrastructure failure.
- **FR-019**: A refusal because a run is already active MUST be an infrastructure
  failure: retried, and out of the pass-rate denominator (rules 7 and 11).
- **FR-020**: When the recorded workflow is gone, the attempt MUST end as an
  infrastructure failure that is not retried, naming the task and the recipes
  file.
- **FR-021**: On a deadline the attempt MUST end as a timeout leaving the recipe
  in place; the run in flight is cleared by the wait of FR-018 on the next
  attempt.
- **FR-022**: Every other outcome MUST map to a termination exactly as create +
  run already maps it (a refused run, a run finished with an error, Monarch down,
  a login refused), with the authoring rows of that table not applicable here.
- **FR-023**: At most one Monarch attempt MUST be in flight at a time, as in
  create + run.
- **FR-024**: Cost for a run-only attempt MUST be read from Monarch's tracing
  service for the execution trace, priced by the same versioned price table, and
  MUST follow the same missing-cost rule; the execution trace is found by the
  attempt identifier the bench sends with the run request.

**Freezing, drift and exclusion**

- **FR-025**: The recipes file MUST be part of the run's configuration
  fingerprint, so a changed recipe is a different run (rule 11).
- **FR-026**: Before the first Monarch attempt of a run-only run, the bench MUST
  verify, per recorded recipe, that Monarch still holds that workflow with the
  same recipe version, and MUST refuse the run on any difference, naming the task.
- **FR-027**: The bench MUST also verify that the knowledge-base file is the one
  the recipes were made against, and MUST refuse the run if it is not.
- **FR-028**: A run-only run started without a recipes file MUST refuse before any
  attempt, naming the command that writes it.
- **FR-029**: Tasks recorded as missing MUST be excluded from the task set of
  **every** competitor in a run-only run, so all pairs stay on identical sets, and
  the run MUST state the number excluded before it starts.
- **FR-030**: The report MUST state, on the source line of every run-only figure,
  how many tasks were excluded and why, and MUST state that Monarch executed a
  fixed known-correct workflow while the other competitors did the whole task.
- **FR-031**: A run-only run whose task set would be empty after exclusion MUST
  refuse.

**Configuration**

- **FR-032**: The Monarch harness MUST declare run-only among the modes it
  supports, and the product under test MUST already list it; a plan naming a mode
  that either does not support MUST fail validation before any spend, as today.
- **FR-033**: A new plan MUST describe the pilot: run-only mode, the 10 pilot
  tasks, 2 repetitions, the same competitors as the create + run pilot with the
  same baseline, internal audience, a cost ceiling, and no approval until Carlos
  approves the specific run.

**Documents**

- **FR-034**: `monarch-benchmark/PLAN.md` MUST be updated: B6 points to feature
  004; D9's definition of done is written out; the decisions log gains this
  feature's decisions; the open questions gain this feature's three.
- **FR-035**: The project instructions and the configuration documentation MUST
  document this feature's folder, the recipes file, the new plan and the new
  command.

### Key Entities

- **Recipe row**: one task's known-correct workflow; attributes: task, workflow,
  recipe version, knowledge-base fingerprint, authored at, attempts used.
- **Missing row**: one task with no known-correct workflow; attributes: task,
  reason.
- **Recipes file**: all rows for one product and one task set; part of the run's
  configuration fingerprint.
- **Attempt (Monarch, run-only)**: as every attempt, plus workflow, run, recipe
  version, execution phase, cost; no authoring phase.
- **Run-only plan**: as described in FR-033.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Offline, with fakes, the recipes command produces a file in which a
  task that passes on the first attempt shows one attempt used, a task that passes
  on the third shows three, and a task that never passes is missing with a reason;
  the failed workflows were deleted and the kept ones were not.
- **SC-002**: The command started without an approval makes no model call and
  prints the task count and cost band; a second run over a complete file makes no
  model call at all.
- **SC-003**: Offline, the run-only plan runs to completion; every Monarch attempt
  made zero authoring requests, has a stored snapshot the checker grades, left its
  workflow in place, and has an execution phase and no authoring phase.
- **SC-004**: A changed recipe version, a deleted workflow, a changed
  knowledge-base fingerprint and a missing recipes file each stop the run before
  any run request, each with a message naming what changed.
- **SC-005**: With two tasks missing, every competitor in the run attempts exactly
  the remaining eight tasks, and the report's source line states that two were
  excluded and why.
- **SC-006**: Changing any recorded field of the recipes file changes the run's
  configuration fingerprint; resuming across that change refuses.
- **SC-007**: A run already in flight on a recipe is waited out and the attempt
  then proceeds; one that never ends yields an infrastructure failure that is
  retried and leaves the denominator.
- **SC-008**: The full test suite stays green, offline, with no key in the
  environment.
- **SC-009**: Live, in order, each step recorded with its output in `tasks.md`:
  the recipes command for the 10 pilot tasks (paid; only after Carlos approves it
  with a cost band), then the run-only pilot after Carlos approves that specific
  run, with an internal report showing Monarch beside the baseline with error bars
  and source lines.
- **SC-010**: `PLAN.md`, the project instructions and the configuration
  documentation reflect this feature as in FR-034 and FR-035.

## Assumptions

- Feature 002 is implemented: the create + run attempt, the front door, the
  knowledge-base hash file, the cost reader and the price table all exist and are
  reused unchanged.
- Monarch's only way to create a workflow is authoring; there is no route that
  accepts a recipe as data. Confirmed in Monarch's benchmark-access notes §5.
- A workflow's recipe does not change under an organisation without an explicit
  save, so verifying its recipe version is enough to detect drift (see Open
  Questions).
- Monarch allows one active run per workflow; the bench's own lock means the only
  way to meet that limit is a leftover from a timed-out attempt.
- The 10 pilot tasks and their approval rules are frozen; a task edit remakes its
  recipe.
- A recipe made against one knowledge base is not valid against another, so the
  knowledge-base fingerprint invalidates every recipe at once.
- All tests run offline; live steps happen only in the order and with the
  approvals of SC-009.

## Open Questions

Recorded here and mirrored in `PLAN.md` §5. None blocks the specification, the
plan or the offline implementation.

1. **Naming a workflow inside Monarch.** No rename route exists: the workflow
   patch route accepts status, trigger kind, schedule, overlap policy and approval
   only. The benchmark's name for a recipe therefore lives in the recipes file.
   Would Deyton accept a name field on that route, so a person opening Monarch can
   tell the benchmark's workflows apart? Owner: Deyton. Not blocking.
2. **Pinning a recipe version.** This feature deliberately does not use the route
   that saves a new version from raw recipe data — it is unverified, refuses old
   recipe shapes and rejects a stale base version — and verifies the recorded
   version instead. Confirmation that a recipe cannot change without an explicit
   save would close the question. Owner: Deyton.
3. **Cancelling a run in flight.** There is no route to cancel a run today, so a
   timed-out run-only attempt leaves the engine working and the next attempt waits
   it out. If such a route is added, the wait becomes a cancel. Owner: Deyton.

Carried from feature 002 and still open, blocking the live steps only: the model
provider permission for Monarch's authoring account (which the recipes command
needs), and the mechanism that grants the benchmark's products to the bench
user's organisation.

## Out of Scope

Full-flow mode (feature 003), a Monarch-versus-Monarch release comparison (this
mode makes it possible; choosing and running one is a later plan), a scripted
executor as a run-only competitor, the second product under test, and the
Monarch-side changes in the Open Questions (each its own change in the Monarch
repository).
