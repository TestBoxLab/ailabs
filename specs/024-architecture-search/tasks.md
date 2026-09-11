---

description: "Task list for feature 024 — the search loop"
---

# Tasks: The search loop — measurement foundations for architecture search

**Input**: Design documents from `/specs/024-architecture-search/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Constitution II requires failing-test-first implementation and runnable
evidence. Every task below names the test that must fail before the change and pass
after. No task is complete without it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: US1–US5, matching the spec's prioritised stories
- All paths are relative to the repository root

## Path conventions

Source under `monarch-benchmark/workflowbench/`, abbreviated **`wb/`** below.
Tests under `wb/tests/`. Always `uv run`; never bare Python.

**Run tests per file during development** — a whole-suite run deadlocks on
`fake_monarch.stop()`. The full suite runs detached at the end.

---

## Phase 1: Setup

**Purpose**: Establish the baseline this feature is measured against.

- [x] T001 Record the pre-change baseline by running the full suite detached and capturing pass/fail/duration into `.tmp/024-baseline.txt` from `wb/` with `uv run python -m pytest tests -q`
- [ ] T002 [P] Confirm the stored ten-task run `6022e89fbb974c7483716f85a5e3c4fe` is present under `wb/out/studio/` and record its current headline number and setup labels into `.tmp/024-baseline-report.txt` — this is the evidence every US2 task reproduces against

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Shared fixtures the story phases depend on. Nothing here changes behaviour.

- [x] T003 Add a `stored_run` fixture in `wb/tests/conftest.py` that loads job `6022e89fbb974c7483716f85a5e3c4fe` from `wb/out/studio/`, skipping with a clear reason when the directory is absent
- [x] T004 [P] Add a `not_applicable` sentinel distinct from `unknown` and from zero in `wb/wb_studio/measures.py`, with a unit test in `wb/tests/test_studio_measures.py` asserting the three are mutually distinguishable

**Checkpoint**: fixtures available; no production behaviour changed.

---

## Phase 3: User Story 1 — The gates hold (Priority: P1)

**Goal**: The hosted workspace can be left running unattended without anything outside
the lab reaching a running attempt, and without the researcher spending past its bounds.

**Independent test**: Enable the researcher on a fresh workspace with provider keys,
attempt each reach in [quickstart.md](./quickstart.md) Story 1, and confirm every one is
refused and recorded.

**Two of these are live on a public URL. T005–T010 lead.**

### The front door (FR-001) — R1

- [x] T005 [US1] Write a failing test in `wb/tests/test_front_door_relay.py` asserting `DELETE /front-door/airtable/v0/app1/Tasks/rec1` with no secret is refused and never relayed
- [x] T006 [US1] Add per-run front-door secret generation and storage on the run record in `wb/wb_studio/app.py`, never logged and never rendered
- [x] T007 [US1] Gate `front_door()` on the current run's secret path segment in `wb/wb_studio/app.py`, making T005 pass
- [x] T008 [US1] Move the `is_front_door()` check after `authorised()` for `do_GET` (`app.py:901`) and `do_POST` (`app.py:1171`) in `wb/wb_studio/app.py`, with tests for both methods in `wb/tests/test_front_door_relay.py`
- [x] T009 [US1] Add the same gate to `do_PUT`, `do_PATCH` and `do_DELETE` in `wb/wb_studio/app.py` (`app.py:882-889`), which today never call `authorised()` at all
- [x] T010 [US1] Carry the secret segment into the seed URL via `public_front_door_url` in `wb/wb_orchestrator/monarch_setup.py` and assert in `wb/tests/test_monarch_setup.py` that Monarch's request shape is unchanged

### Autonomy defaults off (FR-002)

- [x] T011 [US1] Write a failing test in `wb/tests/test_studio_autonomy.py` asserting that with no `autonomy.json` on disk, `cards` and `runs` both read `off`
- [x] T012 [US1] Invert `DEFAULTS` to `{'cards': 'off', 'runs': 'off', 'initiative': 'off', 'paused': False}` in `wb/wb_studio/genesis_autonomy.py:25`, making T011 pass
- [x] T013 [US1] Gate the unconditional `scheduler.start()` and `genesis.watcher.start()` at `wb/wb_studio/app.py:1316` on the researcher being enabled, with a test in `wb/tests/test_studio_scheduler.py`

### Pause is a kill switch (FR-003)

- [x] T014 [P] [US1] Write a failing test in `wb/tests/test_studio_pause.py` asserting a paused researcher sends no paid request from `genesis.chat`
- [x] T015 [US1] Read the pause dial in `Genesis.chat` at `wb/wb_studio/genesis.py:528`, the single funnel every paid turn passes through, making T014 pass
- [x] T016 [US1] Record each skipped scheduled job with its reason to `genesis/activity.jsonl` in `wb/wb_studio/scheduler.py`, asserted in `wb/tests/test_studio_scheduler.py`

### Daily allowance counts launched runs (FR-004)

- [x] T017 [P] [US1] Write a failing test in `wb/tests/test_studio_watcher.py` asserting a run launched by the researcher appears in `today_usd()` at its reserved maximum
- [x] T018 [US1] Include launched runs' reserved maxima in `today_usd()` at `wb/wb_studio/genesis_watcher.py:91`, making T017 pass

### Envelope accounting (FR-005) — R12, blocks T043

- [x] T019 [P] [US1] Write a failing test in `wb/tests/test_genesis_access.py` asserting a person-initiated Genesis turn counts toward the envelope
- [x] T020 [US1] Attribute Genesis turns by the agent that ran them, not by who asked, at `wb/wb_studio/genesis.py:548`, making T019 pass
- [x] T021 [US1] Count an unsettled reservation at its reserved maximum rather than its settled-so-far amount at `wb/wb_studio/usage.py:34`, with a test in `wb/tests/test_studio_usage.py`
- [x] T022 [US1] Count every activity attributable to the researcher regardless of author string at `wb/wb_studio/genesis_access.py:146`, with a test in `wb/tests/test_genesis_access.py`
- [x] T023 [US1] **Verify FR-005** end to end: a test in `wb/tests/test_genesis_access.py` asserting envelope totals equal reserved-plus-settled across a chat turn, a watcher turn and a launched run, within one cent

### Overrun recovery (FR-006)

- [x] T024 [P] [US1] Write a failing test in `wb/tests/test_budget.py` asserting an overrun in a past week does not block a paid path in the current week
- [x] T025 [US1] Scope the overrun query to its own week at `wb/wb_orchestrator/budget.py:269`, making T024 pass
- [x] T026 [US1] Add a recorded human clear path for an overrun in `wb/wb_orchestrator/budget.py` and expose it as `wb budget clear-overrun --id ID --by NAME`, with a test in `wb/tests/test_budget.py`

### Operator and approval (FR-007) — R9

- [x] T027 [P] [US1] Write a failing test in `wb/tests/test_approvals.py` asserting a Studio launch above smoke scale without an approval record is refused
- [x] T028 [US1] Invert the `wb_studio.enterprise` import at `wb/wb_orchestrator/approvals.py:77` so the benchmark no longer depends on the UI package, with the existing approvals tests still green
- [x] T029 [US1] Add `operator` to the settings dict at `wb/wb_studio/app.py:433` and carry it onto the reservation
- [x] T030 [US1] Call `approvals.admit_launch` from `Studio.create` at `wb/wb_studio/app.py:348`, making T027 pass
- [x] T031 [US1] Add a test in `wb/tests/test_approvals.py` asserting an agent-initiated launch can never name itself as approver

### Per-attempt cap (FR-008)

- [x] T032 [P] [US1] Write a failing test in `wb/tests/test_studio_app.py` asserting a Studio-launched run sets `attempt_cap_usd` strictly below the run ceiling
- [x] T033 [US1] Pass a run config carrying the attempt cap from `Studio._execute` at `wb/wb_studio/app.py:617` into the orchestrator, making T032 pass
- [x] T034 [US1] Replace `scope_limit_usd=self.maximum` with the attempt cap in `wb/wb_studio/app.py` (LiveArm), `enterprise.py:527`, `native.py:158` and `execution.py:224`, with a test per arm

### Fetch refuses private addresses (FR-009)

- [x] T035 [P] [US1] Write a failing test in `wb/tests/test_genesis_ingest.py` asserting `169.254.169.254`, `127.0.0.1` and `10.0.0.1` are each refused with nothing fetched or stored
- [x] T036 [US1] Refuse private, loopback and link-local destinations after DNS resolution, and bound redirects, at `wb/wb_studio/genesis_ingest.py:121`, making T035 pass

**Checkpoint**: the workspace can be left running. US1 is independently shippable and is
the suggested MVP.

---

## Phase 4: User Story 2 — Numbers a scientist can act on (Priority: P2)

**Goal**: Every statement a round makes is supported by the evidence it cites.

**Independent test**: Render run `6022e89fbb974c7483716f85a5e3c4fe` and check each row of
the [quickstart.md](./quickstart.md) Story 2 table.

**Every task here begins with a test that reproduces the defect against that stored run.**

### Service naming (FR-010)

- [x] T037 [P] [US2] Write a failing test in `wb/tests/test_studio_reports.py` using `stored_run` asserting a `googleads.googleapis.com` write does not render as "Gmail"
- [x] T038 [US2] Resolve the service from the full host rather than a substring at `wb/wb_studio/reports.py:52`, distinguishing googleads, sheets, drive, calendar and gmail, making T037 pass

### False completion (FR-011)

- [x] T039 [P] [US2] Write a failing test in `wb/tests/test_studio_measures.py` using `stored_run` asserting the four `agent_error` turn-limit attempts produce no completion claim
- [x] T040 [US2] Restrict `false_completion` at `wb/wb_studio/measures.py:103` to competitor-produced output, excluding request text echoed back, making T039 pass
- [x] T041 [US2] Label the signal as inferred from wording wherever it is displayed — `wb/wb_studio/report_data.py:212` and `wb/wb_studio/static/reports.js` — with a test in `wb/tests/test_studio_reports.py`
- [x] T042 [P] [US2] Apply the same restriction to the reuse at `wb/wb_studio/genesis_hypotheses.py:372`, with a test in `wb/tests/test_genesis_hypotheses.py`

### Liveness of stored attempts (FR-012)

- [ ] T043 [P] [US2] Write a failing test in `wb/tests/test_studio_report_baseline.py` using `stored_run` asserting the four attempts on moved hashes are marked non-comparable
- [ ] T044 [US2] Compare each stored attempt's recorded hash against the live corpus in `wb/wb_studio/report_data.py`, emitting `live` / `superseded` / `absent` per [contracts/measures.md](./contracts/measures.md), making T043 pass
- [ ] T045 [US2] Exclude superseded attempts from every headline number and figure, stating the denominator actually scored, in `wb/wb_studio/report_data.py`, with a test asserting the headline changes
- [ ] T046 [US2] Promote `leaderboard.exclusion_reason()` from unused to the source of the exclusion text in `wb/wb_studio/report_data.py`, with a test in `wb/tests/test_studio_leaderboard.py`

### One failure classification (FR-013) — R7

- [ ] T047 [P] [US2] Write a failing test in `wb/tests/test_studio_failure_analysis.py` using `stored_run` asserting the bar chart and the per-attempt folds agree on all eight failed attempts
- [ ] T048 [US2] Derive `failure_analysis` buckets from `narrative.MODES` at `wb/wb_studio/failure_analysis.py:36`, or remove the second classifier, making T047 pass
- [ ] T049 [US2] Point `report_data.code_findings` at the single classification in `wb/wb_studio/report_data.py:221`, with a test asserting no finding cites a bucket the narrative contradicts

### Labels and titles (FR-014, FR-015)

- [ ] T050 [P] [US2] Write a failing test in `wb/tests/test_display_names.py` using `stored_run` asserting the hero bar names model and version, not "low reasoning"
- [ ] T051 [US2] Rewrite `short_name()` at `wb/wb_studio/report_data.py:242` to keep the identifying segments, making T050 pass
- [ ] T052 [P] [US2] Write a failing test in `wb/tests/test_studio_reports.py` asserting a trend over a cohort with no Monarch is not titled "Monarch pass rate by run"
- [ ] T053 [US2] Derive the trend title and colour family from the data at `wb/wb_studio/static/reports.js:329`, making T052 pass

### One cohort key and one interval (FR-016) — R5, R6

- [ ] T054 [P] [US2] Write a failing test in `wb/tests/test_studio_report_baseline.py` asserting runs with no pinned judge are not pooled with pinned ones
- [ ] T055 [US2] Replace `report_data.cohorts`' key at `wb/wb_studio/report_data.py:408` with `leaderboard.py:50`'s key and delete the weaker one, making T054 pass
- [ ] T056 [US2] Surface the existing provisional sentence from `wb/wb_studio/leaderboard.py:57` in the rendered round, with a test in `wb/tests/test_studio_reports.py`
- [ ] T057 [P] [US2] Write a failing test in `wb/tests/test_studio_measures.py` asserting no displayed 95% interval is ever zero-width
- [ ] T058 [US2] Fill the displayed interval at `wb/wb_studio/report_data.py:462` from `measures.pass_rate`'s Wilson bounds, the same source as the rank at `:452`, making T057 pass
- [ ] T059 [P] [US2] Delete the inlined Wilson in `wb/wb_studio/difficulty.py` in favour of `measures.wilson`, with the existing difficulty tests still green

**Checkpoint**: the round report's statements are defensible. Independently shippable.

---

## Phase 5: User Story 3 — An experiment that can return a verdict (Priority: P3)

**Goal**: An experiment either runs with enough power to conclude, or is refused before
any money is reserved.

**Independent test**: [quickstart.md](./quickstart.md) Story 3 — draw the split, propose
against ten tasks and see the refusal, propose against the development slate and see it
admitted, confirm on held-out and see the lineage refused thereafter.

### The stratified split (FR-017, FR-018, FR-033) — R4

- [ ] T060 [P] [US3] Write a failing test in `wb/tests/test_slate.py` asserting a stratified draw leaves the two slates differing by at most one task per tier and per domain
- [ ] T061 [US3] Extract the structural difficulty measure used by `wb corpus tiers` into a reusable function in `wb/wb_orchestrator/corpus.py`, with a unit test asserting it scores an arbitrary corpus task
- [ ] T062 [US3] Implement the stratified draw in `wb/wb_orchestrator/slate.py`, making T060 pass
- [ ] T063 [US3] Write the manifest per [contracts/config-files.md](./contracts/config-files.md) — measure, `measure_kind`, `measure_version`, cuts, seed, per-slate tier and domain counts, per-task rows — in `wb/wb_orchestrator/slate.py`, with a test asserting every field is present
- [ ] T064 [US3] Add `wb corpus split` to `wb/wb_orchestrator/cli.py` per [contracts/cli.md](./contracts/cli.md), with a CLI test in `wb/tests/test_corpus.py`
- [ ] T065 [US3] Refuse redrawing a frozen held-out slate in `wb/wb_orchestrator/slate.py`, with the exact refusal text from the contract, tested in `wb/tests/test_slate.py`

### Repetitions on a run (FR-019, FR-020)

- [ ] T066 [P] [US3] Write a failing test in `wb/tests/test_studio_app.py` asserting a launch carries an explicit repetitions count into the settings dict
- [ ] T067 [US3] Add `repetitions` to the settings dict at `wb/wb_studio/app.py:433` and into the config hash, making T066 pass
- [ ] T068 [US3] Add `--repetitions N` to `wb run` in `wb/wb_orchestrator/cli.py`, defaulting to 1, with a test in `wb/tests/test_foundation_cli.py`
- [ ] T069 [US3] Default a variant test to the development slate in `wb/wb_studio/genesis_hypotheses.py`, with a test in `wb/tests/test_genesis_hypotheses.py`

### Sizing matched to the settling test (FR-021) — R11

- [ ] T070 [P] [US3] Write a failing test in `wb/tests/test_genesis_hypotheses.py` asserting `smallest_plan` refuses a size whose paired sign test cannot reach p < 0.05 at any win count
- [ ] T071 [US3] Add a `minimum_discordant_pairs()` helper to `wb/wb_studio/measures.py` derived from `sign_test`, returning 6, with a unit test covering 2–20 pairs against the table in [research.md](./research.md) R11
- [ ] T072 [US3] Replace the two-proportion sizing at `wb/wb_studio/genesis_hypotheses.py:517` with sizing against the paired sign test, removing the floor of 10, making T070 pass
- [ ] T073 [US3] Carry the assumed flip rate, expected discordant pairs and minimum needed onto the record's `power` field, with the refusal text from [contracts/cli.md](./contracts/cli.md), tested in `wb/tests/test_genesis_hypotheses_record.py`
- [ ] T074 [US3] Re-size the seven already-queued hypotheses under the corrected rule and record which were under-powered as written, into `monarch-benchmark/docs/rounds/2026-09-11-resized-hypotheses.md`

### The research envelope (FR-035) — depends on T023

- [ ] T075 [US3] Write a failing test in `wb/tests/test_budget.py` asserting an absent `genesis/envelope.json` means zero, not unlimited
- [ ] T076 [US3] Implement the envelope record per [contracts/config-files.md](./contracts/config-files.md) in `wb/wb_studio/genesis_access.py`, making T075 pass
- [ ] T077 [US3] Refuse an experiment exceeding the envelope remainder or the per-experiment ceiling before any reservation, naming the shortfall, in `wb/wb_studio/genesis_hypotheses.py`, tested in `wb/tests/test_genesis_hypotheses.py`
- [ ] T078 [US3] Stop the loop on an exhausted envelope without drawing on the weekly ceiling, in `wb/wb_studio/genesis_autonomy.py`, with a test asserting a full scheduled day spends zero
- [ ] T079 [US3] Add `wb budget envelope --set/--per-experiment/--by` and `wb budget envelope status` to `wb/wb_orchestrator/cli.py`, with a test in `wb/tests/test_budget.py`

### Lineage and the record (FR-022, FR-023) — R13

- [ ] T080 [P] [US3] Write a failing test in `wb/tests/test_genesis_hypotheses_record.py` asserting a descendant of a lineage that reached held-out is refused
- [ ] T081 [US3] Add `slate`, `lineage` and `repetitions` to `check_hypothesis` at `wb/wb_studio/genesis_hypotheses.py:41`, extending the existing record rather than adding a store
- [ ] T082 [US3] Enforce held-out once per lineage, and require a prior `supported` development verdict, in `wb/wb_studio/genesis_hypotheses.py`, making T080 pass
- [ ] T083 [US3] Add `wb experiment propose` and `wb experiment confirm` to `wb/wb_orchestrator/cli.py` as a surface over the existing record, with tests in `wb/tests/test_foundation_cli.py`

**Checkpoint**: an experiment can conclude, or is refused with a reason. Independently
shippable.

---

## Phase 6: User Story 4 — The fitness function (Priority: P4)

**Goal**: Configure cost and execute cost, and the two durations, recorded separately and
reconciling to the totals.

**Independent test**: [quickstart.md](./quickstart.md) Story 4 — one paid Monarch attempt,
then inspect the stored row.

### Cost by phase (FR-024) — R2, wiring only

- [ ] T084 [P] [US4] Write a failing test in `wb/tests/test_studio_measures.py` asserting a Monarch result row exposes `cost_by_phase` with `authoring` and `execution`
- [ ] T085 [US4] Carry `cost.by_phase` from `wb/wb_arms/monarch.py:453` onto the result row rather than only into the turn log, making T084 pass
- [ ] T086 [US4] Teach `measures.cost` at `wb/wb_studio/measures.py:127` to read the phase breakdown, asserting parts reconcile with the total within one cent
- [ ] T087 [US4] Record `authoring` as `n/a` for a competitor with no authoring phase, distinct from unknown and zero, in `wb/wb_arms/api_loop.py`, with a test in `wb/tests/test_arms_m2.py`

### Time by phase (FR-025) — R3, the one new recorded value

- [ ] T088 [P] [US4] Write a failing test in `wb/tests/test_arms_m2.py` asserting a Monarch attempt records `authoring_ended_at`
- [ ] T089 [US4] Record the authoring-end timestamp between `_author` (`wb/wb_arms/monarch.py:660`) and `_start_run` (`:773`), making T088 pass
- [ ] T090 [US4] Derive `configure_s` and `execute_s` in `wb/wb_studio/measures.py`, asserting they reconcile with `duration_s` within one second

### Unknown stays unknown (FR-026)

- [ ] T091 [P] [US4] Write a failing test in `wb/tests/test_langfuse_cost.py` asserting an unreadable phase records `unknown` and holds its reservation, never zero
- [ ] T092 [US4] Extend the existing `cost_missing` discipline to the per-phase split in `wb/wb_arms/monarch.py:411`, making T091 pass

### Repeated execution and per-pass cost (FR-027, FR-028) — R10

- [ ] T093 [US4] Generate recipe data with the already-built `wb monarch recipes` for `tasks/dev-50` and record the command, cost and outcome in `monarch-benchmark/docs/rounds/2026-09-11-recipes.md` **(paid — state attempts and a cost band first)**
- [ ] T094 [P] [US4] Write a failing test in `wb/tests/test_monarch_recipes.py` asserting a run-only run produces per-execution cost and time per task
- [ ] T095 [US4] Surface per-execution cost and time from run-only results in `wb/wb_studio/measures.py`, making T094 pass
- [ ] T096 [P] [US4] Add `cost_per_pass` to `wb/wb_studio/measures.py` returning "no passes" when nothing passed, with a test in `wb/tests/test_studio_measures.py`

**Checkpoint**: the fitness function is measurable. Independently shippable.

---

## Phase 7: User Story 5 — The curve and the gap list (Priority: P5)

**Goal**: A round opens with one argument, rendered three ways from one evidence base.

**Independent test**: [quickstart.md](./quickstart.md) Story 5 — open a round as each
audience and confirm no fact is asserted in one and contradicted in another.

### The curve (FR-029, FR-030)

- [ ] T097 [P] [US5] Write a failing test in `wb/tests/test_studio_measures.py` asserting the crossing point is the least n where cumulative cost falls below the comparator, or `none-in-range`
- [ ] T098 [US5] Add the curve computation to `wb/wb_studio/measures.py` per [contracts/measures.md](./contracts/measures.md), making T097 pass
- [ ] T099 [US5] Draw the curve in `wb/wb_studio/static/charts.js` with a downloadable data table and a source line, matching the existing figure conventions
- [ ] T100 [US5] Open a round with the curve, the accuracy comparison with its uncertainty and sample count, and the gap list, in `wb/wb_studio/report_data.py` and `static/reports.js`, with a test in `wb/tests/test_studio_reports.py`
- [ ] T101 [US5] Assert in `wb/tests/test_studio_measures.py` that the curve never extrapolates beyond the observed range of n

### The gap list (FR-031, FR-032, FR-034)

- [ ] T102 [P] [US5] Write a failing test in `wb/tests/test_studio_reports.py` asserting a `code-reading` gap item is never rendered as a peer of a `confirmed-result`
- [ ] T103 [US5] Add the gap item record per [data-model.md](./data-model.md) in `wb/wb_studio/report_data.py`, making T102 pass
- [ ] T104 [US5] Render the gap list for the engine-team, lab and executive audiences from one base in `wb/wb_studio/report_data.py`, with a test asserting no rendering contradicts another
- [ ] T105 [US5] Add `--audience engine-team` to `wb report` in `wb/wb_orchestrator/cli.py`, and keep `code-reading` items internal-only, with a test in `wb/tests/test_html_report.py`
- [ ] T106 [US5] Produce the written proposal from a held-out confirmation per [data-model.md](./data-model.md) in `wb/wb_studio/genesis_hypotheses.py`, with a test in `wb/tests/test_genesis_hypotheses.py`

**Checkpoint**: the deliverable exists. Feature complete.

---

## Phase 8: Polish & cross-cutting

- [ ] T107 Run the full suite detached from `wb/` with `uv run python -m pytest tests -q` and compare against the T001 baseline; no previously-passing test may fail
- [ ] T108 [P] Run `node tests/browser/suite.cjs` from `wb/` and review the snapshots for the US2 and US5 frontend changes
- [ ] T109 [P] Correct `monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md` §3, which lists feature 004 as "specified, not built" when `wb_orchestrator/monarch_recipes.py` is complete
- [ ] T110 [P] Add the slate manifest, the research envelope and the front-door secret to the file map in `CLAUDE.md`
- [ ] T111 [P] Record in `monarch-benchmark/PLAN.md` that decision D10's phase telemetry is satisfied by `langfuse_cost.by_phase` and now reaches the report
- [ ] T112 Refresh the Graphify knowledge graph through the installed Graphify skill, per constitution V

---

## Dependencies

### Story order

```text
US1 (gates)        → shippable alone; the suggested MVP
US2 (instrument)   → independent of US1; may run in parallel
US3 (experiments)  → needs US1's T023 for the envelope (T075–T079)
US4 (fitness)      → independent; may run in parallel with US2 and US3
US5 (curve)        → needs US4 for cost and time by phase, and US2 for trustworthy numbers
```

### Hard dependencies

| Blocked | Blocked by | Why |
|---|---|---|
| T075–T079 (research envelope, FR-035) | **T023** (envelope accounting verified, FR-005) | R12 — a standing envelope on broken accounting authorises unattended spending against a gate that never refuses |
| T007, T008, T009 | T006 | The secret must exist before it can gate |
| T010 | T007 | The seed URL carries what the gate checks |
| T030 | T028, T029 | Approval needs the inverted import and the operator |
| T044–T046 | T003 | The stored-run fixture |
| T072 | T071 | Sizing needs the minimum-pairs helper |
| T082 | T081 | Lineage must exist on the record |
| T085–T087 | T004 | The `n/a` sentinel |
| T095 | T093 | Per-execution measures need recipe data |
| T098–T101 | T086, T090 | The curve needs cost and time by phase |
| T103–T106 | T044 | Gap items cite attempts whose liveness is known |

### Within-story parallel opportunities

- **US1**: T014, T017, T019, T024, T027, T032, T035 are independent failing tests in seven different files — write them all first, then fix in sequence.
- **US2**: T037, T039, T043, T047, T050, T052, T054, T057 likewise — eight reproductions against the same stored run, eight different test files.
- **US3**: T060, T066, T070, T080 are independent.
- **US4**: T084, T088, T091, T094, T096 are independent.
- **Polish**: T108–T111 are four different files.

---

## Implementation strategy

**MVP = User Story 1.** Two of its defects are live on a public URL and one of them can
silently invalidate an otherwise-correct round. Ship US1 alone and the workspace becomes
safe to leave running, which nothing else in this feature depends on.

**Second increment: US2.** It is independent of US1 and makes the existing round report
defensible. Together US1 and US2 are the whole of "the instrument is calibrated and the
workspace is safe", which is the precondition the design names for letting the search run
at all.

**Third: US3 and US4 in parallel.** They touch different packages — `genesis_hypotheses`
and `slate` on one side, `monarch.py` and `measures.py` on the other. The only crossing
is T075's dependency on T023.

**Last: US5.** It is a rendering of evidence produced by the other four and is worthless
before them.

**Paid steps**: T093 is the only task that spends money. State the attempt count and a
cost band before running it, and reserve against the weekly ledger, per constitution IV.

**Note on coverage**: the browser suite resolves Playwright from a hard-coded path on one
machine and does not run in CI, so the frontend changes in T041, T053, T099 and T100 have
no automated guard. T108 is a manual review step, not a test. Say so in the code review
rather than implying coverage.


---

## Progress, 11 September 2026

**Done and green: 29 of 112.** All of User Story 1 (the gates) except the approvals
wiring. Verified per file; the full suite was re-run after the last change.

| Requirement | Tasks | State |
|---|---|---|
| FR-001 front door | T005–T010 | done — `tests/test_front_door_relay.py` (12), `test_studio_app.py` updated |
| FR-002 autonomy off | T011–T013 | done — `tests/test_studio_autonomy.py` |
| FR-003 pause | T014–T016 | done — `tests/test_genesis_pause.py` (5) |
| FR-004 daily allowance | T017–T018 | done — `tests/test_genesis_allowance.py` |
| FR-005 envelope | T019–T023 | done, incl. the T023 end-to-end check |
| FR-006 overrun | T024–T026 | done — `tests/test_budget_overrun.py` (9), `wb budget acknowledge` |
| FR-007 operator | T029, T031 | done — `tests/test_studio_launch_gates.py` |
| FR-008 attempt cap | T032–T034 | done — same file |
| FR-009 fetch guard | T035–T036 | done — `tests/test_genesis_fetch_guard.py` (16) |

**User Story 1 is complete.** T027, T028 and T030 — the approvals wiring I had stopped
short of — were finished by other sessions working the same checkout on 11 September:
`wb_studio/app.py:554` now calls `admit_launch(self.store, rc, env, request_id=...)`, and
`wb_orchestrator/approvals.py` no longer imports `wb_studio.enterprise` (the probe record
moved to `wb_orchestrator/monarch_probe.py`), so the benchmark's paid-round gate no
longer sits behind the view package. Recorded against their work, not claimed as mine.

**Not done: T002, T003, T004** — the stored-run fixture and the `not applicable` sentinel
are foundational for User Story 2, which has not started.

**Deviations from the plan, each deliberate:**

1. **The front-door secret is per deployment, not per run** (`STUDIO_FRONT_DOOR_SECRET`),
   rotated by changing the variable before `wb monarch setup` writes the seeds. A per-run
   secret needs the Studio and a CLI round on another machine to agree on a value neither
   generates; the contract in `contracts/config-files.md` says per run and is now ahead of
   the code. It fails closed: with no secret set, the door serves nothing.
2. **FR-006 does not make an overrun stop blocking.** `budget.py`'s own docstring called
   the permanent block deliberate. Weakening a money gate is not this feature's business,
   so an overrun still blocks until a named person acknowledges it with a reason. What
   changed is that the recovery is auditable instead of a hand-edit of the sqlite file.
3. **The attempt cap does not always sit below the run ceiling.** A round of two or three
   attempts sized for two or three expensive requests cannot bound one of them below what
   it costs; capping there refuses every attempt instead of limiting it. The cap is four
   times an even split, clamped to the ceiling and never below what one request reserves.
   `test_studio_launch_gates.py` states both halves.
4. **`--audience engine-team` became `--for engine-team|lab|executive`** in
   `contracts/cli.md`, so a framing can never be confused with a competitor allowlist.

**Carried for the user:**

- `tests/conftest.py` now sets `WB_OPERATOR=test-operator` for every test. Thirty-five
  existing tests create paid jobs with no operator; the requirement is the product's, not
  the suite's. `test_studio_launch_gates.py` deletes it to test the refusal.
- The baseline suite is **2237 tests**, not the 1091 in `STATE-OF-THE-PROGRAM.md`, with
  one pre-existing failure (`test_run_page.py::test_index_has_evidence_tabs_and_runs_table_counts`).
- A second session is editing this checkout. `wb_report/`, `report_data.py`, `caveats.py`,
  `narrative.py`, `figures.py`, `reports.js`, `report.css` and the audience gate are theirs.
