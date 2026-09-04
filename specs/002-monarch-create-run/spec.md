# Feature Specification: Monarch as a Competitor in Create + Run Mode

**Feature Branch**: `002-monarch-create-run`

**Created**: 2026-09-03

**Status**: Draft

**Input**: User description: "Feature 002: Monarch as a competitor in create + run mode. Single source: docs/superpowers/specs/2026-09-03-monarch-create-run-design.md (already read, approved; do not relitigate the §2 decisions). Must respect monarch-benchmark/PLAN.md §1 fixed rules unchanged; include contracts/monarch-telemetry.md (x-bench-episode-id header, phase spans, Langfuse generations with tokens; implemented as a separate PR in the Monarch repo); open questions: bedrock:InvokeModel for Carlos's AWS roles, mechanism granting the 47 products to the org, whether auth_scheme none actions need a credential binding; docs scope includes PLAN.md changes (B4/B7/B8 + C1–C3 → feature 002, D7 and D10 merged, new decisions-table rows). English, plain names (competitor, task set, attempt, approval rule)."

**Design of record**: `docs/superpowers/specs/2026-09-03-monarch-create-run-design.md`
(approved 3 Sep 2026 by Carlos and the spec reviewer). This spec restates that
design as requirements; it does not reopen the decisions in its §2.

## Why

The benchmark exists to compare Monarch, TestBox's product, with raw language
models and coding agents on the same tasks. Today the Monarch competitor is a
placeholder: every result so far compares raw models with each other. This
feature makes Monarch a real competitor in the **create + run** test mode: Monarch
receives a pre-built knowledge base of the 47 simulated apps, then, on the clock,
turns the task request into a workflow and executes it. The result is graded by
the same checker, from the same stored snapshot, as every other competitor.

The first deliverable is a paired pilot on the simulated product: 10 tasks, 2
repetitions, three competitors (answer key, Claude Opus 4.8 raw, Monarch), internal
report. It is deliverable D7 in `monarch-benchmark/PLAN.md`, with D10 (phase
telemetry) merged into it.

None of the fixed rules in `PLAN.md` §1 change. The feature adds inputs (a
runnable Monarch harness, a plan, a price table, a knowledge-base hash file), one
setup command, and one contract that the Monarch side must meet.

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
| knowledge base | the description of the 47 apps that Monarch is given before the clock starts |
| front door | the bench's HTTP server that exposes a fresh copy of the simulated apps to Monarch for one attempt |
| authoring | Monarch turning the request into a workflow |
| execution | Monarch's engine running that workflow against the front door |
| phase | one of discovery, authoring, execution; only authoring and execution are measured here |
| Langfuse | the tracing service Monarch already ships with; the source of Monarch's cost and phase data |
| infrastructure failure | a failure the bench or its environment caused, not the competitor; retried and excluded from the denominator |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Monarch as a competitor in a paired pilot (Priority: P1)

Carlos runs `wb run --product simulated-apps --plan pilot-monarch-create-run`. The
plan lists three competitors: the answer key, Claude Opus 4.8 raw, and Monarch.
For every attempt, Monarch is given the same request text as the other
competitors, authors a workflow, runs it against a fresh copy of the simulated
apps, and the bench stores the resulting snapshot. Later, `wb grade` and `wb report`
produce a paired internal report with Monarch beside the raw model, with error
bars, source lines, cost split by phase and by model, and questions asked.

**Why this priority**: This is the feature. Deliverable D7 is exactly this pilot.

**Independent Test**: With a fake Monarch that authors a fixed workflow and calls
back into the front door, run the plan offline and confirm that every Monarch
attempt ends with a stored snapshot the checker grades, and that the report shows
`monarch@<version>` beside `claude-opus-4-8/api` on identical attempt sets.

**Acceptance Scenarios**:

1. **Given** a plan whose competitors include Monarch and whose mode is
   `create-run`, **When** the run starts, **Then** the run lists the number of
   attempts and the cost ceiling, refuses if `approved_by` is missing above the
   smoke threshold (as feature 001 already does), and treats Monarch as one more
   competitor.
2. **Given** one Monarch attempt, **When** it runs, **Then** the request text Monarch
   receives is byte-identical to the text every other competitor receives for
   that task, and the result row records it.
3. **Given** one Monarch attempt, **When** Monarch finishes normally, **Then** the
   stored snapshot is the state of the fresh copy of the apps after Monarch's
   execution, and the checker grades it later from that snapshot alone (nothing
   grades itself).
4. **Given** a completed pilot, **When** `wb report` runs for the internal audience,
   **Then** Monarch and Claude Opus 4.8 raw are compared pairwise on identical
   attempt sets, with error bars, and every figure carries its source line.
5. **Given** a completed pilot, **When** the report is read, **Then** each Monarch
   row shows wall-clock per phase (authoring, execution), cost per phase and per
   model in Monarch's team, the number of questions Monarch asked, and the
   competitor name with the Monarch version.
6. **Given** the plan's concurrency is greater than one, **When** the run executes,
   **Then** at most one Monarch attempt is in flight at any moment while other
   competitors keep their concurrency.

---

### User Story 2 - Prepare Monarch once per product (Priority: P1)

Before the first run, Carlos runs `wb monarch setup`. The command turns the bench's
description of the 47 simulated apps into 47 knowledge-base entries in the shape
Monarch expects, tells Carlos exactly what to add to Monarch's local configuration
so those entries are visible, registers one Monarch product per app, imports each
knowledge base, and writes the 47 resulting knowledge-base hashes to a file that
the run's configuration hash covers. Running it twice changes nothing. It spends no
model money.

**Why this priority**: Without the knowledge base there is no create + run mode.
The setup must be reproducible so that "same knowledge within a test mode" (rule 2)
is enforced, not assumed.

**Independent Test**: With a fake Monarch discovery service, run `wb monarch setup`
twice; confirm 47 entries in the expected shape, 47 registered products, 47 hashes
in the file, identical output both times, and zero model calls.

**Acceptance Scenarios**:

1. **Given** the bench's description of the 47 apps, **When** setup runs, **Then**
   it writes 47 knowledge-base entries, one per app, each meeting the acceptance
   bar of Monarch's seeds runbook (no credential required, a response shape with
   extraction rules, created entities with identifier paths so actions can chain).
2. **Given** the entries are not yet visible to Monarch, **When** setup runs,
   **Then** it prints the exact configuration snippet Carlos must add on the
   Monarch side and stops with a clear message; it does not proceed to
   registration.
3. **Given** the entries are visible, **When** setup runs, **Then** it registers the
   47 products and imports the 47 knowledge bases, recording one hash per app.
4. **Given** the import succeeded, **When** setup checks product access, **Then** it
   reports which of the 47 products the bench user's organisation cannot use, and
   says that granting access is a manual step until Monarch names the mechanism.
5. **Given** setup completed, **When** it runs again, **Then** the hash file is
   byte-identical and no error is raised.
6. **Given** the hash file exists, **When** `wb run` reaches its first Monarch
   attempt, **Then** it re-reads the hashes from Monarch and refuses to continue
   if any differs from the file, naming the app.

---

### User Story 3 - Charge Monarch only for its own failures (Priority: P2)

A Monarch attempt can end in many ways: normal finish, an authoring error, a
refused run, a run that fails midway, a deadline, or a failure of the bench's own
environment (Monarch down, model provider not reachable, tracing service down).
Carlos needs each outcome mapped to the right termination so that infrastructure
failures are retried and leave the denominator, while Monarch's own failures count
against it.

**Why this priority**: Rule 7 (infrastructure failures excluded and reported
separately) is what makes the comparison fair. Without a correct mapping the
pilot's pass rate is meaningless.

**Independent Test**: With a fake Monarch scripted to produce each outcome in
turn, run one attempt per outcome and confirm the termination and recorded detail
match the table below.

**Acceptance Scenarios**:

1. **Given** authoring finishes and the run ends normally, **When** the attempt
   closes, **Then** termination is `completed` and the row records the workflow
   identifier, run identifier, recipe version and number of questions asked.
2. **Given** authoring fails because the model provider is unavailable or
   unauthorised (the message names the provider, the cloud account, credentials,
   or "not configured"), **When** the attempt closes, **Then** termination is
   `infra:monarch_llm`, the attempt is retried per rule 11, and it leaves the
   denominator.
3. **Given** authoring fails for any other reason, **When** the attempt closes,
   **Then** termination is `agent_error` with the authoring message recorded.
4. **Given** Monarch refuses to run the workflow because of a setup fault on the
   bench side (host blocked, engine unavailable, another run already active),
   **When** the attempt closes, **Then** termination is `infra:monarch_setup`.
5. **Given** Monarch refuses to run the workflow because of the workflow's own
   fault (invalid input, product not granted, unacknowledged loop, legacy recipe),
   **When** the attempt closes, **Then** termination is `agent_error` with the
   refusal code recorded.
6. **Given** the run finishes with an error, **When** the attempt closes, **Then**
   termination is `agent_error` with the error code and the failing step recorded.
7. **Given** the deadline passes during authoring or execution, **When** the
   attempt closes, **Then** termination is `timeout`, the in-flight authoring or
   workflow is cancelled or deleted, and the front door is stopped.
8. **Given** Monarch asks for an account choice during authoring, **When** the
   attempt closes, **Then** termination is `agent_error` with detail
   `account_requested`.
9. **Given** Monarch is down, login is refused, Monarch returns a server error,
   or the tracing service fails its health check, **When** the attempt closes,
   **Then** termination is an infrastructure failure and the attempt is retried.
10. **Given** any outcome, **When** the attempt closes, **Then** the workflow
    Monarch created is deleted, the front door is stopped, and the Monarch lock is
    released, so the next attempt starts clean.

---

### User Story 4 - Answer Monarch's questions without leaking (Priority: P2)

During authoring Monarch may ask a clarifying question. The bench answers every
question with one fixed sentence, identical for every attempt and every task:
"No further information is available. Proceed with your best judgment." The bench
counts the questions in the result row. The sentence is not editable through
configuration.

**Why this priority**: Rule 1 (same request text) and rule 3 (nothing grades
itself) forbid any answer that depends on the task or the answer key. Raw models
get no clarification either, so a fixed non-answer keeps the comparison fair.

**Independent Test**: With a fake Monarch that asks two questions before finishing,
run one attempt and confirm both questions received the fixed sentence and the row
counts two questions.

**Acceptance Scenarios**:

1. **Given** Monarch pauses authoring with one or more questions, **When** the bench
   replies, **Then** every question in that pause receives the fixed sentence and
   authoring continues.
2. **Given** a completed attempt, **When** the row is read, **Then** the number of
   questions asked is recorded, zero when none were asked.
3. **Given** a person edits the harness or plan file, **When** they look for the
   reply text, **Then** it is not there; it lives only in the code.

---

### User Story 5 - Complete cost from Monarch's own traces (Priority: P2)

After each Monarch attempt, the bench reads from Monarch's tracing service every
model call that belongs to that attempt: model name, input tokens, output tokens,
cache tokens, and the phase it ran in. It prices them with a versioned price table
for Monarch's model team (Claude Opus 4.8, Opus 5, Sonnet 5, Sonnet 4.6, Haiku 4.5
at the cloud provider's prices in the region Monarch uses) and stores cost per
phase and per model. The tracing service's own cost figure is ignored. Wall-clock
per phase comes from the bench's own clocks.

**Why this priority**: Rule 9 (cost is complete; for Monarch, the sum over its
whole model team) cannot be met from the bench side alone. This is deliverable D10
merged into D7.

**Independent Test**: With a fake tracing service serving traces in the contract's
shape, run one attempt and confirm the cost per phase and per model equals tokens
times the table's prices, and that a trace with no model calls yields zero cost and
the `cost_missing` flag.

**Acceptance Scenarios**:

1. **Given** traces exist for the attempt, **When** the attempt closes, **Then** the
   row's cost is the sum over all model calls of tokens times the price-table
   entry for that model, split by phase (authoring, execution) and by model, with
   cached and non-cached tokens separated.
2. **Given** no trace or no model call is found for the attempt, **When** the
   attempt closes, **Then** cost is zero, the row carries `cost_missing`, and the
   verdict stands; this is not an infrastructure failure.
3. **Given** a report is produced, **When** any Monarch cost figure is printed,
   **Then** its source line states the price-table version and the share of Monarch
   attempts with missing cost.
4. **Given** a model appears in a trace that the price table does not list,
   **When** the attempt closes, **Then** the run stops with an error naming the
   model and the price-table file, before any further spend.

---

### User Story 6 - Check the Monarch environment before spending (Priority: P3)

Carlos runs `wb doctor` before a pilot. It checks that Monarch answers, that the
bench user can log in, that Monarch's discovery service answers, and that the
tracing service answers. A check that costs model money (a one-request authoring
probe) runs only when explicitly requested.

**Why this priority**: Rule 7 depends on separating environment faults from
competitor faults; a doctor check finds them before money is spent.

**Independent Test**: With fakes for each service, run `wb doctor` and confirm each
check reports pass or fail with the service named; confirm the paid probe is
skipped unless asked for.

**Acceptance Scenarios**:

1. **Given** all Monarch services answer, **When** `wb doctor` runs, **Then** it
   reports four passing checks (Monarch liveness, Monarch health with session,
   discovery service, tracing service).
2. **Given** one service is down, **When** `wb doctor` runs, **Then** it names that
   service and the address it tried.
3. **Given** the paid probe is not requested, **When** `wb doctor` runs, **Then** no
   model call is made.

---

### User Story 7 - Read the updated plan and configuration (Priority: P3)

Carlos opens `monarch-benchmark/PLAN.md` and sees work items B4, B7, B8 and C1–C3
pointing to feature 002, deliverables D7 and D10 merged, two new rows in the
decisions log, and the open questions of this feature listed. He opens the
configuration README and the config-file contract and finds the new harness
fields explained in plain words.

**Why this priority**: PLAN.md is the single tracking surface. Docs that lag the
code make the next handoff wrong.

**Independent Test**: Read the four documents and tick the items below.

**Acceptance Scenarios**:

1. **Given** PLAN.md, **When** read, **Then** B4, B7, B8, C1, C2 and C3 reference
   feature 002; D7's definition of done absorbs D10's; the decisions log has rows
   for "Monarch cost comes from Langfuse, not Postgres" and "a question during
   authoring gets one fixed reply"; the open questions include the three listed in
   this spec.
2. **Given** the config README and the config-file contract, **When** read,
   **Then** every new harness field, the new plan file, the new price table and the
   knowledge-base hash file are documented with an example.
3. **Given** the handoff of 3 Sep and the project `CLAUDE.md`, **When** read,
   **Then** their status lines say feature 002 is specified and where its
   artifacts are.

---

### Edge Cases

- Monarch's version cannot be read from the checkout (path missing, not a git
  repository): the run refuses to start, naming the harness field to fix. A
  competitor without a version breaks provenance (constitution: provenance over
  convenience).
- The Monarch checkout is on a branch other than `main`: the competitor name
  carries the branch as well as the version.
- The front door's fixed port is already in use: the attempt ends as an
  infrastructure failure naming the port; it is retried.
- Monarch's authoring stream closes without a terminal status: `agent_error`
  with detail `stream_closed`, unless the deadline passed first (`timeout`).
- Two Monarch attempts are scheduled at once: the second waits for the lock; the
  deadline of the second attempt starts only when it acquires the lock.
- The knowledge-base hash file is missing when a plan with Monarch starts: the
  run refuses and tells Carlos to run `wb monarch setup`.
- The tracing service is reachable but returns traces for a different attempt
  identifier: they are ignored; cost is zero with `cost_missing`.
- Traces contain a phase name outside the contract: its tokens are counted under
  `other` and the row carries a flag naming the phase, so the contract drift is
  visible in the report.
- The workflow deletion fails after a completed attempt: the row keeps its
  verdict; the failure is logged and the next attempt's setup deletes any
  workflow left behind before starting.
- Setup finds fewer than 47 apps in the bench's description: it stops and names
  the missing ones; it never writes a partial hash file.

## Requirements *(mandatory)*

### Functional Requirements

**Competitor behaviour (one attempt)**

- **FR-001**: The bench MUST run Monarch as a competitor in create + run mode:
  knowledge base loaded before the clock, then authoring and execution on the clock.
- **FR-002**: The request text given to Monarch MUST be identical to the text
  given to every other competitor for the same task (rule 1); the row MUST record
  that the request was used as Monarch's goal.
- **FR-003**: Each Monarch attempt MUST operate on a fresh copy of the simulated
  apps, exposed to Monarch through the bench's front door on a fixed address that
  Monarch's containers can reach.
- **FR-004**: The stored snapshot for a Monarch attempt MUST be the state of that
  fresh copy after Monarch's execution, taken by the bench, not reported by
  Monarch (rule 3).
- **FR-005**: The bench MUST measure wall-clock for authoring and execution
  separately with its own clocks and store both per attempt.
- **FR-006**: At most one Monarch attempt MUST be in flight at a time, regardless
  of the plan's concurrency; other competitors are unaffected.
- **FR-007**: After every attempt, whatever its outcome, the bench MUST delete the
  workflow Monarch created, stop the front door, and release the Monarch lock.
- **FR-008**: The bench MUST answer every clarifying question Monarch asks during
  authoring with the fixed sentence "No further information is available. Proceed
  with your best judgment.", identical for every attempt, and MUST record the
  number of questions in the row. The sentence MUST NOT be configurable.
- **FR-009**: If Monarch asks for an account choice during authoring, the attempt
  MUST end as `agent_error` with detail `account_requested`.
- **FR-010**: The bench MUST map each attempt outcome to a termination exactly as
  in the table below, and record the detail named.

| Outcome | Termination | Detail recorded |
|---|---|---|
| Authoring done, run ended normally | `completed` | workflow id, run id, recipe version, questions asked |
| Authoring error caused by the model provider (message names the provider, the cloud account, credentials, or "not configured") | `infra:monarch_llm` | the provider message |
| Authoring error, any other | `agent_error` | `authoring_error: <message>` |
| Authoring done without a workflow (Monarch declined) | `agent_error` | `no_workflow: <message>` |
| Run refused for a bench setup fault (host blocked, engine unavailable, run already active) | `infra:monarch_setup` | the refusal code |
| Run refused for the workflow's own fault (invalid input, product not granted, unacknowledged loop, legacy recipe) | `agent_error` | `run_refused:<code>` |
| Run finished with an error | `agent_error` | `run_error:<code> node=<id>` |
| Deadline passed | `timeout` | phase in which it passed |
| Monarch down, login refused, server error, tracing service health check failed | `infra:*` | the service and address |

- **FR-011**: Terminations of the `infra:*` family MUST be retried by the run and
  excluded from the pass-rate denominator (rules 7 and 11); no other termination
  is retried.
- **FR-012**: On `timeout` the bench MUST cancel in-flight authoring, or delete a
  workflow whose run is in flight, before closing the attempt.
- **FR-013**: The competitor name in every result row MUST be `monarch@<version>`,
  where the version is read from the Monarch checkout at run time, with the branch
  appended when it is not the main branch. If the version cannot be read the run
  MUST refuse to start.

**Setup, once per product (`wb monarch setup`)**

- **FR-014**: The bench MUST provide a command that prepares Monarch for the
  simulated product without any model call, and that can be run repeatedly with
  the same result.
- **FR-015**: Setup MUST generate one knowledge-base entry per simulated app (47)
  from the bench's own description of the apps, in the shape Monarch's discovery
  service imports, meeting the acceptance bar of Monarch's seeds runbook: no
  credential required; a response shape with extraction rules; created entities
  with identifier paths so that actions can chain.
- **FR-016**: Setup MUST verify that Monarch's discovery service can see all 47
  entries before registering anything. If it cannot, setup MUST print the exact
  configuration Carlos must add on the Monarch side and stop.
- **FR-017**: Setup MUST register one Monarch product per app, named
  `bench-<service>`, and import its knowledge base, recording the hash Monarch
  returns for each.
- **FR-018**: Setup MUST check which of the 47 products the bench user's
  organisation can use and print the ones it cannot; granting access is a manual
  step until Monarch names the mechanism (see Open Questions).
- **FR-019**: Setup MUST write the 47 hashes to a file next to the product
  definition, and that file MUST be covered by the run's configuration hash (rule
  11): a different knowledge base is a different run.
- **FR-020**: Before its first Monarch attempt, a run MUST re-read the hashes from
  Monarch and refuse to continue if any differs from the file or the file is
  missing, naming the app or the missing file.

**Cost and phases**

- **FR-021**: After each attempt the bench MUST read from Monarch's tracing
  service every model call tagged with that attempt's identifier, taking model
  name, input tokens, output tokens, cache tokens, and the phase name of the
  enclosing span.
- **FR-022**: The bench MUST price those tokens with a versioned price table for
  Monarch's model team (Claude Opus 4.8, Opus 5, Sonnet 5, Sonnet 4.6, Haiku 4.5;
  cloud-provider prices in Monarch's region) held as a model file like the other
  price files, and store cost per phase and per model in the row, with cached and
  non-cached tokens separated. The tracing service's own cost figure MUST be
  ignored.
- **FR-023**: When no model call is found for an attempt, cost MUST be zero, the
  row MUST carry the `cost_missing` flag, and the verdict MUST stand; the report's
  source line MUST show the share of Monarch attempts with missing cost.
- **FR-024**: A model call for a model absent from the price table MUST stop the
  run with an error naming the model and the file.
- **FR-025**: The discovery phase MUST be recorded as empty in this feature; it is
  measured by feature 003.

**Contract with the Monarch side**

- **FR-026**: The bench MUST publish the telemetry contract at
  `specs/002-monarch-create-run/contracts/monarch-telemetry.md`: the attempt
  identifier header, the phase span names, and the shape of a model call as
  recorded in the tracing service. The Monarch side implements it as a separate
  change in the Monarch repository, reviewed by its owner; that change is out of
  this feature's scope.
- **FR-027**: The bench MUST send the attempt identifier with every authoring and
  run request so that Monarch can tag its traces.
- **FR-028**: The bench's tests MUST exercise the contract against a fake tracing
  service that serves traces in the contract's shape.

**Configuration and health**

- **FR-029**: The Monarch harness file MUST become runnable and MUST carry: the
  Monarch address, the credential variable, the discovery-service address, the
  front door's fixed port, the tracing-service address and key variables, the
  price-table name, and the path of the Monarch checkout. The fixed release
  string MUST be removed. Missing or invalid fields MUST fail validation naming
  the file and the field, before any spend (as feature 001 does).
- **FR-030**: A new plan file `pilot-monarch-create-run` MUST describe the pilot:
  create + run mode, the 10 pilot tasks, 2 repetitions, competitors {answer key,
  Claude Opus 4.8 raw, Monarch}, baseline Claude Opus 4.8 raw, internal audience,
  a cost ceiling, and `approved_by` empty until Carlos approves the specific run.
- **FR-031**: `wb doctor` MUST check Monarch liveness, Monarch health with a
  session, the discovery service, and the tracing service, naming any that fail
  and the address tried. A paid authoring probe MUST run only on explicit request.
- **FR-032**: The bench MUST log in to Monarch once per run with the seeded bench
  user and reuse the session; a token supplied through the credential variable
  MUST skip the login.

**Documents**

- **FR-033**: `monarch-benchmark/PLAN.md` MUST be updated: B4, B7, B8 and C1–C3
  point to feature 002; D7 absorbs D10; decisions log gains "Monarch cost comes
  from Langfuse, not Postgres" and "a question during authoring gets one fixed
  reply, questions counted"; open questions gain the three in this spec.
- **FR-034**: The configuration README and the config-file contract MUST document
  the new harness fields, the new plan, the price table and the hash file, with
  examples.
- **FR-035**: The handoff of 3 Sep and the project `CLAUDE.md` MUST have their
  status lines updated to point at this feature's artifacts.

### Key Entities

- **Monarch competitor**: a harness-only competitor named `monarch@<version>`;
  attributes: address, credential, discovery-service address, front-door port,
  tracing-service address, price table, checkout path.
- **Knowledge-base entry**: one per simulated app; the description Monarch imports
  before the clock; attributes: product name `bench-<service>`, hash returned by
  Monarch.
- **Knowledge-base hash file**: 47 (app, hash) pairs next to the product
  definition; part of the run's configuration hash.
- **Attempt (Monarch)**: as every attempt, plus: workflow id, run id, recipe
  version, questions asked, phase wall-clocks, cost per phase and per model,
  `cost_missing` flag.
- **Model call**: one entry read from the tracing service; attributes: model,
  input tokens, output tokens, cache tokens, phase name, attempt identifier.
- **Price table for Monarch's team**: a versioned model file listing the five
  models with cloud-provider prices in Monarch's region.
- **Pilot plan**: `pilot-monarch-create-run`, as described in FR-030.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Offline, with fakes for Monarch, its discovery service and its
  tracing service, the pilot plan runs to completion and every Monarch attempt
  has a stored snapshot that the checker grades; the answer key passes all 20 of
  its attempts.
- **SC-002**: Every one of the outcomes in the FR-010 table is reproduced by a test
  and yields the stated termination and detail; the infrastructure ones are
  retried and excluded from the denominator.
- **SC-003**: `wb monarch setup` against a fake discovery service produces 47
  entries that pass the runbook's shape check, 47 hashes, and byte-identical
  output on a second run, with zero model calls.
- **SC-004**: Changing one knowledge-base hash changes the run's configuration
  hash; a run started with a stale hash file refuses before the first Monarch
  attempt.
- **SC-005**: For a trace with known tokens, the cost stored per phase and per
  model equals tokens times the price table to the cent; a trace with no model
  calls yields zero cost and `cost_missing`.
- **SC-006**: An attempt in which Monarch asks two questions records two questions
  and both replies are the fixed sentence.
- **SC-007**: The full test suite stays green (199 tests before this feature, plus
  the new ones), offline, without any key in the environment.
- **SC-008**: Live, in order and each step recorded with its output in `tasks.md`:
  `wb doctor` passes against the real Monarch; `wb monarch setup` imports 47
  knowledge bases; one single attempt on one task completes (cents; only after
  the model-provider permission is granted); the paired pilot of 60 attempts runs
  after Carlos approves it with a stated cost band, and its internal report shows
  Monarch beside Claude Opus 4.8 raw with error bars and source lines.
- **SC-009**: PLAN.md, the config README, the config-file contract, the 3 Sep
  handoff and the project `CLAUDE.md` reflect this feature as in FR-033 to FR-035.

## Assumptions

- Monarch runs in Docker on Carlos's machine with its tracing service enabled
  (the `dev-otel` profile), as verified live on 2–3 Sep. Hosting elsewhere is
  work item B10, out of scope.
- The bench's front door can bind to all interfaces on the fixed port and
  containers reach the host through the standard host alias; verified in the
  Monarch repo's benchmark-access notes.
- Monarch's knowledge-base import re-imports on demand and this doubles as the
  reset of the knowledge base. Workflow deletion cascades to versions, runs,
  checkpoints and bindings, so one call per attempt is enough.
- A read-only telemetry change in Monarch does not alter its behaviour, so the
  competitor remains "stock" for reporting purposes.
- Monarch's authoring is deterministic enough that create + run is a fair mode:
  the same knowledge base yields comparable workflows across repetitions. This is
  Lucas's original design and is not reopened here.
- The 10 pilot tasks and their approval rules are frozen (feature 001); the
  approval-rule gap in `simple.sf_opp_closed_won` stays as is pending Lucas.
- All tests run offline; live steps happen only in the order and with the
  approvals of SC-008.

## Open Questions

Recorded here and mirrored in `PLAN.md` §5. None blocks the specification, the
plan, or the offline implementation; the first three block the live pilot.

1. **Model-provider permission.** None of Carlos's AWS single-sign-on roles may
   call `bedrock:InvokeModel` in the region Monarch uses (tested 3 Sep, all
   denied). Monarch's authoring uses that provider only. Owner: Deyton or infra;
   procedure in the Monarch repo's account-bootstrap notes.
2. **Product access grant.** The mechanism that grants the 47 `bench-<service>`
   products to the bench user's organisation (a route or a seed script) is not
   named in Monarch's benchmark-access notes. Until it is, setup prints the
   missing products and the step is manual. Owner: Deyton.
3. **Credential binding for credential-free actions.** Whether products whose
   actions need no credential still require a credential binding, or a
   declaration in Monarch's discovery catalogue, for the engine to execute them.
   If yes, the binding becomes a setup step and the declaration joins the Monarch
   change's scope, and "no Monarch code change for the knowledge base" no longer
   holds. Owner: Carlos, verified live against the runbook before the first
   attempt.

## Out of Scope

Full-flow mode (feature 003), run-only mode (feature 004), the Slack post
(work front D), the Monarch-side change itself (its own spec in the Monarch
repository), the second product under test, Monarch hosting other than this
machine (B10), and per-run token totals on Monarch's run endpoint (C4, superseded
by reading the tracing service).
