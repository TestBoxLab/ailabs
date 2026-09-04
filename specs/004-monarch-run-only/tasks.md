# Tasks: Monarch in Run-Only Mode

**Input**: Design documents from `/specs/004-monarch-run-only/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md.
Feature 002 must be implemented and green: this feature branches its arm and
reuses its attempt, its fakes and its cost reader.

**Tests**: Required. Constitution §II mandates red → green → refactor; every task
that adds logic starts with a failing test in the named test file. All tests
offline; no key in the environment; no `wb run` and no `wb monarch recipes`
during implementation.

**Organization**: Grouped by user story in spec priority order. US3 (drift and
exclusion) and US2 (run the pilot) come before US1 (make the recipes) in build
order even though all three are P1: the loader, the hash and the exclusion are
what US2 needs, and US1's command is the only paid one, so it is written last and
run last.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 from spec.md

## Path Conventions

All code paths are under `monarch-benchmark/workflowbench/` (written as `wb/`
below). Tests run with
`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.
The Monarch checkout is `C:\Users\cgmat\Desktop\TestBox\monarch`.

---

## Phase 1: Setup

- [ ] T001 [P] Add `run-only` to `modes` in `wb/config/harnesses/monarch.yaml` per `contracts/config-files.md`; confirm `wb/config/products/simulated-apps.yaml` already lists it and needs no edit
- [ ] T002 [P] Write `wb/config/plans/pilot-monarch-run-only.yaml` per `contracts/config-files.md` (`mode: run-only`, the seven competitors of the create + run pilot, `approved_by: null`)
- [ ] T003 [P] Write `wb/tests/fixtures/monarch-recipes-sample.yaml`: a recipes file for the 10 pilot tasks with 9 recipes and 1 missing row, used by the loader, hash and exclusion tests before the live file exists

---

## Phase 2: Foundational (blocking)

**Purpose**: the fake routes and the config loading every story depends on.

- [ ] T004 Write failing tests in `wb/tests/test_fakes.py` for the three new fake routes: `GET /api/workflows/<id>` returns `{recipeVersion}` for an id in `Scenario.workflows` and 404 otherwise; a workflow listed in `Scenario.active_run_for` refuses the first N run requests with `409 RUN_ALREADY_ACTIVE` and accepts the next; `Scenario.active_run_never_clears` keeps its run polling as `running`
- [ ] T005 Add those routes and the three `Scenario` fields to `wb/tests/fake_monarch.py` per `data-model.md` §7. T004 green
- [ ] T006 Write failing tests in `wb/tests/test_config.py`: `load_monarch_recipes(path, product, tasks)` returns the rows of the fixture; a task in both `recipes` and `missing` fails naming it; a task key outside the task set fails; a `product` or `tasks` mismatch fails; a bad `reason` value fails; `load_harness` accepts `modes: [create-run, run-only]`
- [ ] T007 Implement `MonarchRecipes`, `RecipeRow`, `MissingRow` and `load_monarch_recipes` in `wb/wb_orchestrator/config.py` per `data-model.md` §1. T006 green
- [ ] T008 Write failing tests in `wb/tests/test_run_config.py`: `resolve()` on a run-only plan with a Monarch competitor loads the recipes file into `RunConfig.monarch_recipes`; a missing file → `ConfigError` naming `wb monarch recipes`; `RunConfig.hash` changes when a `workflow_id`, a `recipe_version`, `kb_hash_file_sha` or a `missing` key changes, and does **not** change when `generated_at` or a missing row's `detail` changes; the hash of `pilot-monarch-create-run` is unchanged versus its recorded value (create + run must not move)
- [ ] T009 Implement in `wb/wb_orchestrator/config.py`: `RunConfig.monarch_recipes`, `RunConfig.excluded_tasks`, the recipes load in `resolve()` gated on `plan.mode == "run-only"`, and `_hashed()` per `data-model.md` §1. T008 green

**Checkpoint**: config loads and hashes the recipes; the fakes can play every run-only situation.

---

## Phase 3: User Story 3 — Refuse on drift, exclude what is missing (P1)

**Goal**: a run-only run either uses exactly the frozen recipes or refuses, and every competitor runs the same task set.

**Independent test**: `wb/tests/test_run_config.py` against `fake_monarch`.

- [ ] T010 [US3] Write failing tests in `wb/tests/test_run_config.py`: `resolve()` on a run-only plan drops the tasks in `missing` from `RunConfig.tasks` and records them in `RunConfig.excluded_tasks` with their reasons; every competitor's attempt count reflects the reduced set; a recipes file whose `missing` covers the whole task set → `ConfigError` refusing an empty comparison; a task in neither map is treated as missing and excluded with reason `not_attempted`
- [ ] T011 [US3] Implement the exclusion in `wb/wb_orchestrator/config.py::resolve` (one place, before competitors are built; `# ponytail: exclusion at the top — per-competitor filtering is what rule 7 forbids`). T010 green
- [ ] T012 [US3] Write failing tests in `wb/tests/test_run_config.py::test_recipe_drift_refuses`: with `Orchestrator.from_config` on a run-only plan, `arm.prepare()` reads every recorded workflow; a different `recipeVersion` → non-retryable `InfraError` naming the task, both versions, and the recipes file, raised before any run request reaches the fake; a 404 for one workflow → the same, saying to rerun `wb monarch recipes`; a `kb_hash_file_sha` that does not match the knowledge-base file's bytes → refused with "the recipes must be remade"
- [ ] T013 [US3] Extend `MonarchArm.prepare()` in `wb/wb_arms/monarch.py`: keep the knowledge-base check of feature 002, and in run-only add the per-recipe `GET /api/workflows/<id>` version check and the knowledge-base fingerprint check. T012 green
- [ ] T014 [US3] Write failing test in `wb/tests/test_m4.py`: the internal report of a run-only run prints a source line carrying the number of excluded tasks with their reason and the sentence "Monarch executed a fixed known-correct workflow; the other competitors did the whole task from the request text."; make it green in `wb/wb_report/report.py` (reads `config_json`'s excluded tasks and the plan's mode)
- [ ] T015 [US3] Add the run-only banner line to `wb/wb_orchestrator/cli.py::_banner` per `contracts/cli.md` (`monarch: <name>, mode run-only, N recipes, M tasks excluded (<reasons>)`); assert it in `wb/tests/test_run_config.py`

---

## Phase 4: User Story 2 — Run the run-only pilot (P1) 🎯 MVP

**Goal**: a Monarch attempt executes the recorded recipe, is snapshotted by the bench, deletes nothing, and the plan runs offline end to end.

**Independent test**: `wb/tests/test_monarch_run_only.py::test_pilot_plan_offline` (SC-003).

- [ ] T016 [US2] Write failing test in `wb/tests/test_monarch_run_only.py::test_run_only_attempt`: with the arm built in run-only mode and a recipes file naming `wf-1`, after `arm.run(ep, deadline)` the fake recorded **zero** requests to `/api/workflows/recipe/runs`, one `POST /api/workflows/wf-1/run` carrying `x-bench-episode-id`, **zero** `DELETE`s, the `Episode` world carries the engine's changes, `result.termination == "completed"`, `result.phases` has `execution` and `"authoring" not in result.phases`, and `turn_log[0]["monarch"]` carries `workflowId`, `recipeVersion` and `runId` but no `recipeRunId`
- [ ] T017 [US2] Implement the mode branch in `wb/wb_arms/monarch.py`: `mode` on the constructor; `_attempt` skips `_author` and the deleting `finally` when the mode is `run-only`, taking the workflow id from the recipe row; `_execute` reused unchanged. T016 green
- [ ] T018 [US2] Pass the mode and the recipes to the arm in `wb/wb_orchestrator/orchestrator.py::build_arm_for` (from `run_config.plan.mode` and `run_config.monarch_recipes`); test in `wb/tests/test_monarch_run_only.py` that a run-only plan without recipes fails at build time, naming the file
- [ ] T019 [US2] Write failing tests in `wb/tests/test_monarch_run_only.py`: `test_timeout_leaves_the_recipe` (the engine never finishes → `EpisodeTimeout`, the fake recorded no `DELETE`, the workflow still exists) and `test_no_delete_on_any_outcome` (parametrised over a refused run, a failed run and a succeeded run: never a `DELETE`)
- [ ] T020 [US2] Make T019 green in `wb/wb_arms/monarch.py` (the timeout path must not fall through to feature 002's delete)
- [ ] T021 [US2] Write failing test `wb/tests/test_monarch_run_only.py::test_cost_from_execution_trace`: with fake tracing traces tagged with the attempt id and no authoring generations, `result.cost_usd` and `result.phases["execution"].cost_usd` are the engine's cost, `phases` still has no `authoring`, and the trace-id shortcut was not used (the reader received no trace ids). Make it green if anything in `_add_cost` assumes an authoring phase exists
- [ ] T022 [US2] Write failing test `wb/tests/test_monarch_run_only.py::test_pilot_plan_offline` per `quickstart.md`: fakes on free ports, temporary harness and recipes files, the run-only plan with `{oracle, monarch}` on the 10 pilot tasks × 2 minus the excluded one; assert the answer key's passes, the Monarch rows with snapshots and `test_mode == "run-only"`, zero authoring requests, zero deletes, and a report listing both names with the run-only source line
- [ ] T023 [US2] Make T022 green (scenario engine calls per task, as feature 002's offline pilot test already builds them)

**Checkpoint**: run-only works offline end to end against a recipes file written by hand.

---

## Phase 5: User Story 3b — Wait out a run already in flight (P1)

**Goal**: the leftover of a timed-out attempt does not fail the next one.

**Independent test**: `wb/tests/test_monarch_run_only.py`, `Scenario.active_run_for`.

- [ ] T024 [US3] Write failing tests in `wb/tests/test_monarch_run_only.py`: `test_active_run_is_waited_out` (`active_run_for={"wf-1": 2}` → the arm polls the workflow's run to a terminal state and then runs, ending `completed`) and `test_active_run_never_clears` (`active_run_never_clears` → `InfraError("infra:monarch_setup", retryable=True)` after the bound, naming how long it waited, and the front door is stopped)
- [ ] T025 [US3] Implement the bounded wait in `wb/wb_arms/monarch.py` per research R4 (60 s bound, the existing 2 s poll interval, `# ponytail: fixed bound; a harness field is the upgrade`). T024 green
- [ ] T026 [US3] Write failing test `test_workflow_gone_is_infra`: the run request 404s → `InfraError("infra:harness_crash", retryable=False)` naming the task and the recipes file; make it green in `wb/wb_arms/monarch.py`

---

## Phase 6: User Story 1 — Prepare one known-correct recipe per task (P1)

**Goal**: `wb monarch recipes` produces the file; gated, idempotent, honest about what it kept and what it deleted.

**Independent test**: `wb/tests/test_monarch_recipes.py` against the fakes.

- [ ] T027 [US1] Write failing tests in `wb/tests/test_monarch_recipes.py` for the gate: without `--yes` and without an approved plan, the command prints the task count, the attempt limit and a cost band, makes **zero** requests to the fakes and exits 5; with `--yes` it proceeds; with a plan whose `approved_by` is set it proceeds; a missing knowledge-base file exits 6 naming `wb monarch setup`
- [ ] T028 [US1] Create `wb/wb_orchestrator/monarch_recipes.py` with the gate, the cost-band print and the exit codes of `contracts/cli.md`. T027 green
- [ ] T029 [US1] Write failing tests in `wb/tests/test_monarch_recipes.py` for one task: a scenario whose first authoring passes the checker → one attempt, the workflow kept (no `DELETE` for it), a recipe row with `workflow_id`, `recipe_version`, `authored_at`, `attempts_used: 1`; a scenario whose first two runs fail the checker and whose third passes → three attempts, two `DELETE`s of the failed workflows, `attempts_used: 3`; a scenario that never passes → three `DELETE`s, no recipe row, a `missing` row with reason `checker_failed` and the detail of the last attempt
- [ ] T030 [US1] Implement the per-task loop in `wb/wb_orchestrator/monarch_recipes.py` per `data-model.md` §9: a fresh `Episode`, `MonarchArm` in create + run mode, the bench's snapshot, the checker, keep or delete (`# ponytail: drives the create + run arm as-is; a change to that lifecycle is felt here on purpose`). T029 green
- [ ] T031 [US1] Write failing tests in `wb/tests/test_monarch_recipes.py`: reasons other than the checker's — an authoring error → `authoring_error`, a failed run → `run_error`, a deadline → `timeout`, an infrastructure failure → `infra` (and the infrastructure one does not consume an attempt); make them green
- [ ] T032 [US1] Write failing tests in `wb/tests/test_monarch_recipes.py` for the file and idempotence: the written file matches `contracts/config-files.md` (sorted keys, `kb_hash_file_sha` equal to the sha256 of the knowledge-base file's bytes, `monarch` equal to the competitor name); a second run over a complete file makes zero authoring requests and writes identical bytes; a run after the knowledge-base file changed remakes every recipe; an interrupted run's rows survive and a rerun continues from them
- [ ] T033 [US1] Implement the file writer and the skip logic in `wb/wb_orchestrator/monarch_recipes.py`. T032 green
- [ ] T034 [US1] Add the `recipes` subcommand to the `monarch` group in `wb/wb_orchestrator/cli.py` (`--product`, `--harness`, `--plan`/`--tasks`, `--attempts`, `--yes`) reusing `resolve_name_or_path`; test in `wb/tests/test_monarch_recipes.py` that `main(["monarch","recipes",…])` returns the step's exit code and that `--plan` and `--tasks` together are refused
- [ ] T035 [US1] Print the `bench:<task_id>` name per kept recipe with the note that Monarch has no rename route today (research R5), and assert the note in `wb/tests/test_monarch_recipes.py`

---

## Phase 7: User Story 4 — Read the updated plan and configuration (P3)

**Goal**: PLAN.md, the project instructions and the configuration docs reflect the feature.

**Independent test**: read the files against FR-034 and FR-035.

- [ ] T036 [P] [US4] Update `monarch-benchmark/PLAN.md`: B6 gains "→ feature 004 (`specs/004-monarch-run-only/`)"; D9's definition of done is written out (a known-correct recipe per task made by `wb monarch recipes` and graded by the checker; the engine-only pilot with an execution phase and no authoring phase; tasks without a recipe excluded for every competitor and stated on the source line); decisions log rows dated 4 Sep 2026: "Known-correct means a workflow Monarch authored that passed the bench's checker; nothing else counts" and "Run-only reuses one kept recipe per task; tasks without one leave the task set of every competitor" (by Carlos); the three open questions of this feature with owners
- [ ] T037 [P] [US4] Update the project `CLAUDE.md`: add `specs/004-monarch-run-only/` and the recipes file to the "What lives where" table, and update the status paragraph
- [ ] T038 [P] [US4] Update `wb/config/README.md`: the recipes file, the run-only plan, the new mode value and `wb monarch recipes` with its gate

---

## Phase 8: Polish and gates

- [ ] T039 Run the full suite `cd wb && uv run python -m pytest tests -q`; paste the summary line below this task; fix any regression before continuing
- [ ] T040 Refresh the knowledge graph from the repo root: `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`; confirm `graphify-out/GRAPH_REPORT.md` lists `monarch_recipes` and `MonarchRecipes`
- [ ] T041 **Live gate 1 (no money)**: with Monarch up, run `uv run wb doctor` and paste the `monarch` block; then confirm the two routes this feature reads — `GET /api/workflows/<an existing id>` returning `recipeVersion`, and a second `POST /api/workflows/<id>/run` while one is active answering `409 RUN_ALREADY_ACTIVE`. Paste both. If either differs from `research.md` R3/R4, stop and revise the research before continuing
- [ ] T042 **Live gate 2 (PAID; requires Carlos's explicit yes with a cost band)**: `uv run wb monarch recipes --plan pilot-monarch-run-only --attempts 3 --yes`. Up to 30 create + run attempts. Paste the per-task lines and the totals; commit `wb/config/products/simulated-apps.monarch-recipes.yaml`; record how many tasks ended missing and why
- [ ] T043 **Live gate 3 (cents)**: one run-only attempt on one task with a temporary plan copy (1 task × 1 repetition, `{oracle, monarch}`); paste the row's `termination`, `phases` (there must be no `authoring`) and `cost_usd`, and confirm in Monarch that the workflow still exists afterwards
- [ ] T044 **Live gate 4 (the pilot, 140 attempts; requires Carlos's approval of that specific run and `approved_by` set)**: `uv run wb run --product simulated-apps --plan pilot-monarch-run-only`, then `wb grade` and `wb report`; paste the paired table and the source lines; file the report under `wb/out/report-pilot-monarch-run-only-001-internal.md`
- [ ] T045 Ask Deyton the three open questions of `spec.md` (a `name` field on the workflow patch route; confirmation that a recipe cannot change without an explicit save; a run-cancel route) and record the answers in `research.md` and `PLAN.md`. Separate repository; not part of this branch's tests

---

## Dependencies

```
Phase 1 → Phase 2 → US3 (Phase 3) → US2 (Phase 4) → US3b (Phase 5) → US1 (Phase 6)
US4 (Phase 7) any time after Phase 2; Phase 8 last; T041 → T042 → T043 → T044 in order.
```

- US2 needs the loader, the hash and the exclusion of US3.
- US3b and US1 both edit `wb/wb_arms/monarch.py` or drive it: run them after US2, one at a time.
- US1 is last because it is the only paid path, and it drives the arm US2 finished.

## Parallel execution examples

- Phase 1: T001, T002, T003 together.
- Phase 7: T036, T037, T038 together.

## Implementation strategy

1. **MVP** = Phases 1–4: the run-only plan runs offline end to end against a
   hand-written recipes file, with drift refused and missing tasks excluded. That
   alone proves rules 3, 7 and 11 for this mode.
2. Phase 5 hardens the one situation this mode creates that create + run does not:
   a run left in flight because nothing can cancel it.
3. Phase 6 automates making the recipes; until it exists, a recipes file can be
   written by hand from one manual authoring session, which is what the offline
   tests use.
4. Phase 7 and the graph refresh close the offline work; the branch is reviewable
   and mergeable there. The live gates run later, in order, each pasted into this
   file, with T042 the one that needs money and a decision.
