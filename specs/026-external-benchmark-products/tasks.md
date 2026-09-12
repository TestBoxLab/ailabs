---

description: "Task list for feature 026 — external benchmarks as products under test"
---

# Tasks: External benchmarks as products under test

**Input**: Design documents from `/specs/026-external-benchmark-products/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Constitution §II is mandatory here. Every task that writes non-trivial logic
is preceded by a failing test, and no task is complete without runnable evidence. The
generic OPTIONAL labels in the template do not apply. Every test runs offline: no
containers, no downloads, no network, no provider keys.

**Money**: no task in this feature launches a paid round or calls a paid provider.

**Organization**: grouped by user story. Phases 1 and 2 block everything; after that each
story is an independently testable increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on incomplete work
- **[Story]**: US1…US4 from [spec.md](spec.md); setup, foundational and polish carry none

## Path conventions

Paths are repository-relative. The benchmark lives under
`monarch-benchmark/workflowbench/`, abbreviated **`wfb/`** below.

---

## Phase 1: Setup — the spikes and the ground

**Purpose**: settle the three honest unknowns before building on them, and put the legal
and licence guards in place before any source content can land.

The three spikes come first deliberately. **T001 can return a finding that makes
EnterpriseOps-Gym unsuitable**, and that is worth knowing on day one rather than in week
three.

- [x] T001 [P] Spike S1: pull one EnterpriseOps-Gym domain image, start it, and establish how its database is reached read-only for the snapshot and for the verifier SQL. Also establish **whether a reference solution or any oracle path exists** for a verifier set — the answer-key competitor is the ceiling line on every figure, and if this product cannot have one that must be recorded now, not discovered at reporting. Write findings into `specs/026-external-benchmark-products/research.md` under a new "Spike results" section. Time-box: one day. A negative result is a valid, valuable outcome.
- [x] T002 [P] Spike S2: install AppWorld into a root outside this repository and confirm which of `data/base_dbs/`, per-task `dbs/` and `experiments/outputs/.../dbs/*.jsonl` is the right snapshot source, and that two dumps of an untouched world are identical. Record in `research.md`.
- [x] T003 [P] Spike S3: read the installed `tau2` package and record the real library surface — constructing a domain environment, listing its tools, running its reward, configuring the simulated customer — in `research.md`. The source's README documents the command line; the library surface has to be read from the code.
- [x] T004 Create the package skeleton: `wfb/wb_worlds/__init__.py`, `wfb/wb_worlds/enterprise_ops/__init__.py`, `wfb/wb_worlds/appworld/__init__.py`, `wfb/wb_worlds/tau2/__init__.py`. No logic.
- [x] T005 [P] Write `wfb/wb_worlds/enterprise_ops/LEGAL.md`: Apache-2.0, ServiceNow AI Research / Mila / Université de Montréal, arXiv 2603.13594, what we use and what we never modify.
- [x] T006 [P] Write `wfb/wb_worlds/appworld/LEGAL.md`: the dual licence, and the explicit statement that task, interface and answer-key content is depended on and **never** redistributed in plain form from this public repository.
- [x] T007 [P] Write `wfb/wb_worlds/tau2/LEGAL.md`: MIT, Copyright (c) 2025 Sierra Research; note that results below source version 1.0.1 are not comparable with later ones.
- [x] T008 Add the AppWorld content guard to `.gitignore`: the conventional `APPWORLD_ROOT` location and any `appworld` data directory, with a comment naming the licence requirement. Add the three sources' local data directories too.
- [x] T009 Add `appworld` and `tau2` as **optional extras** in `wfb/pyproject.toml`, not base dependencies, with the reasons from [research.md](research.md) R9 as comments. EnterpriseOps-Gym adds nothing.
- [x] T010 [P] Add the third-party entries for all three sources to `THIRD_PARTY_LICENSES.md` at the repository root.

**Checkpoint**: the spikes have answers ([research.md](research.md) "Spike results"),
the licence guards are in place, and nothing has been built on a guess.

**What the spikes changed**, recorded here because the plan assumed otherwise:

- EnterpriseOps-Gym already publishes an OpenAPI 3.1 document (79 paths, 108
  operations) and reaches its world over HTTP with an `x-database-id` header. **No
  MCP-to-OpenAPI wrapping is needed for it**, which removes work from T031 and adds
  none.
- Its administrative operations sit on the same surface as its real ones, so
  withholding them from the competitor is now FR-034 and FR-035 and a new task, T031a.
- `tau2` on PyPI is a **different project** (magnetic relaxation rates). τ²-bench is
  installed from its git repository; T054 and the quickstart say so.
- τ²'s `reward_basis` is per task, so the "is the positive half end-state only"
  disclosure is computed from the frozen set rather than declared once per product.
- None of the three can be a dependency of this project: AppWorld pins pydantic below
  2.0 (research.md R10). All three run out of process behind HTTP. T009 records that
  instead of adding extras.

---

## Phase 2: Foundational — the seam

**Purpose**: name the interface the orchestrator already demands, make the product choose
its implementation, and make the positive half a per-product path.

**Blocking**: no user story starts until this phase is done and the whole existing suite
still passes unchanged. A seam that breaks the working product is worse than three
missing products.

- [x] T011 Write the failing contract test in `wfb/tests/test_world_adapter.py`: the adapter protocol from [contracts/world-adapter.md](contracts/world-adapter.md), asserted against every registered world. It fails because the protocol does not exist.
- [x] T012 Create `wfb/wb_world/adapter.py`: the protocol — construction, `attach_journal`, `artifacts_dir`, the three tools, `snapshot`, `finish`, `close`, `tool_calls`, `events`, `record_agent_event`, plus the two class methods `prerequisites()` and `positive_check(task, snapshot0, snapshot1, artifacts)` returning `PositiveResult(passed, detail, source, side_effects)`.
- [x] T013 Make `wfb/wb_world/episode.py` satisfy the protocol: add `close()` (idempotent), `prerequisites()` and `positive_check()` that runs the vendor's assertion registry exactly as `wfb/grader/grade.py` does today. **No behavioural change** — the existing tests are the proof.
- [x] T014 Write the failing test in `wfb/tests/test_world_adapter.py`: an unknown world name refuses the product by name, and no source package is imported at start-up.
- [x] T015 Create `wfb/wb_world/registry.py`: product `world` name to adapter, lazy import, named refusal. A dictionary — three implementations do not need a plugin system.
- [x] T016 Write the failing tests in `wfb/tests/test_external_grading.py`: (a) a product whose positive check is not AutomationBench grades through its own path; (b) a task with no reachable positive check does not pass; (c) a checker that raises leaves the attempt `ungraded` with the error kept; (d) the right result plus one stray change is a failure with the stray change listed.
- [x] T017 Rework `wfb/grader/grade.py`: the positive half becomes the product's `positive_check`; the collateral half keeps calling `grader/invariant.py` unchanged. Preserve deliberately the rule that no positive check means no pass. Add `ungraded`, `positive_source`, `source_collateral` and `disagreement` to the verdict per [data-model.md](data-model.md).
- [x] T018 Write the failing test in `wfb/tests/test_world_adapter.py`: the front door serves any adapter, not only an `Episode`.
- [x] T019 Change `wfb/wb_arms/http_shim.py` to take the adapter protocol instead of `Episode`. Request handling, size limits and the access log are untouched.
- [x] T020 Write the failing test in `wfb/tests/test_external_grading.py`: the orchestrator builds the attempt's world from the product, not from a hard-wired `Episode`.
- [x] T021 Change `wfb/wb_orchestrator/orchestrator.py:559` to resolve the adapter through the registry. The retry loop, the journal, `snapshot0.json`, the deadline and the evidence writer stay exactly as they are.
- [x] T022 Write the failing tests in `wfb/tests/test_config.py` for the five validation rules in [contracts/config-files.md](contracts/config-files.md), including rule 4: declared `services` must match what the adapter actually dumps.
- [x] T023 Extend the product schema in `wfb/wb_orchestrator/config.py`: `world`, `source` (the source pin), `participants`. `config/products/simulated-apps.yaml` must stay valid byte for byte.
- [ ] T024 Write the failing test, then generalize the manifest world block in `wfb/wb_orchestrator/corpus.py` from "which AutomationBench revision" to "which source pin", with AutomationBench as one case.
- [x] T025 Write the failing test in `wfb/tests/test_world_adapter.py`, then create `wfb/wb_world/tools_openapi.py`: publish a tool list as operations — `POST /{service}/{tool_name}`, the tool's own input schema as the request body, its real name as the operation id. No guessed resource paths.
- [ ] T026 Run the whole suite (`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`, detached on Windows, about 27 minutes). **Gate**: every pre-existing test passes unchanged. Record the count.

**Checkpoint**: the seam exists, AutomationBench runs through it unchanged, and the suite is green. Only now does an adapter get written.

---

## Phase 3: User Story 1 — A foreign world runs and grades under our rules (P1) 🎯 MVP

**Goal**: EnterpriseOps-Gym is a product under test, end to end: import, freeze, run offline with the scripted checks, grade, report.

**Independent test**: import its tasks, freeze a ten-task set, run the answer key and the null check offline with no provider keys, grade. The answer key passes, the null check fails every task, the report renders.

- [x] T027 [US1] Record offline fixtures in `wfb/tests/fixtures/external/enterprise_ops/`: a handful of real dataset rows, a seeded database, and a recorded before/after pair. Recorded from the spike, never fabricated.
- [ ] T028 [P] [US1] Write the failing importer tests in `wfb/tests/test_external_import.py`: a row becomes a task file carrying request text, source pin, `source_ref` (task id, verifiers, seed reference), approval rule and `contract_sha256`; a re-import of unchanged content writes nothing; a task that cannot be snapshotted or checked is refused with a recorded reason and never half-written.
- [ ] T029 [US1] Implement `wfb/wb_worlds/enterprise_ops/importer.py` and wire `wb corpus import-eog` into `wfb/wb_orchestrator/cli.py` per [contracts/cli.md](contracts/cli.md).
- [x] T030 [P] [US1] Write the failing adapter tests in `wfb/tests/test_worlds_enterprise_ops.py`: fresh private world per attempt; deterministic snapshot (two dumps of an untouched world identical, rows sorted by primary key); the three tools dispatch into this attempt's world; `close()` is idempotent; `prerequisites()` names a missing container runtime without starting anything.
- [x] T031 [US1] Implement `wfb/wb_worlds/enterprise_ops/adapter.py`: seed from the task's `seed_database_file`, serve behind the three tools, dump a service-keyed snapshot, and implement `positive_check` by executing each verifier's SQL against the post-attempt database and comparing with its `expected_value`. Their SQL and their expected values are used exactly as shipped.
- [x] T031a [US1] Write the failing test, then withhold the world's administrative operations from the competitor (FR-034, FR-035): `ADMIN_PATHS` on the adapter, removed from the published interface document and refused at the front door in `wfb/wb_arms/http_shim.py`. A competitor that reaches `/api/sql-runner` can write the expected result in one query.
- [ ] T032 [US1] Write `wfb/config/side-effects.enterprise-ops-gym.yaml`: the reviewed per-service side-effect list, in the shape `wfb/config/side-effects.yaml` already uses.
- [ ] T033 [US1] Write `wfb/config/products/enterprise-ops-gym.yaml` per [contracts/config-files.md](contracts/config-files.md), with `services` set to what the adapter actually dumps.
- [ ] T034 [US1] Write `wfb/config/plans/eog-smoke.yaml`: the frozen set, `create-run`, the answer key and the null check as competitors, one repetition, a cost ceiling. Smoke scale, so no approval record is needed.
- [ ] T035 [US1] Extend `wb world serve` and `wb doctor --product` in `wfb/wb_orchestrator/cli.py` to cover this product: publish its interface documents through `wb_world/tools_openapi.py`, and report `prerequisites()` in plain words.
- [ ] **T035a [US1] BLOCKED — decide how EnterpriseOps-Gym's approval rule is derived.** The dataset ships verifiers, not solutions ([research.md](research.md) S1b), so `info.expected_changes` cannot be derived from them: a verifier says what must be *true*, not what must *change*, and every obvious translation either fails correct attempts or makes the collateral half vacuous. The proposal on the table is to seed each task's world at import time, evaluate each verifier against that initial state, and turn the ones that do not yet hold into `where` matchers from their SQL `WHERE` equality predicates. That is our own approval-rule translation, permitted by the constitution, but it is a design decision and it needs a person. **T036 and T037 wait on it.**
- [ ] T036 [US1] Freeze the first task set with the existing machinery — `wb corpus slate` or `wb corpus tiers` against the imported corpus — into `wfb/tasks/eog-<domain>-10/`, and confirm the manifest carries the source pin and every task's hash.
- [ ] T037 [US1] Write the failing end-to-end offline test in `wfb/tests/test_worlds_enterprise_ops.py`, then make it pass: the answer key passes the frozen sample, the null check passes none of it, and a round whose recorded source pin does not match the installed source is refused. **If T001 found no oracle path**, this task instead records that finding, the product declares it has no answer key, and US2's ceiling-line handling (T041) covers the consequence.
- [ ] T038 [US1] Run the quickstart's Part 2 EnterpriseOps-Gym block by hand with the containers up, and record the evidence. A green unit test is not enough; the world has to have actually run.

**Checkpoint**: a second product under test exists and a round on it reads.

---

## Phase 4: User Story 2 — A round on a foreign product reads honestly (P2)

**Goal**: no report on an external product can be misread, and no output can pool two products.

**Independent test**: generate a report for a round on an external product and read it; then attempt a paired comparison across two products and confirm it is refused.

- [ ] T039 [P] [US2] Write the failing tests in `wfb/tests/test_html_report.py` for the comparability sentence of [contracts/report.md](contracts/report.md): source, version, split, and which side supplied each half, generated from the source pin — never typed.
- [ ] T040 [US2] Implement the comparability sentence and the paid-participant sentence in `wfb/wb_studio/caveats.py`, extending `for_run` and `for_round`. Include the extra disclosure when `positive_half_is_end_state_only` is false.
- [ ] T041 [US2] Write the failing test, then implement in `wfb/wb_studio/report_data.py`: both halves of a failed verdict are visible; a source's own side-effect finding is shown beside ours and a disagreement is shown as a disagreement; an `ungraded` attempt is reported as ungraded, excluded from pass-rate denominators with its exclusion counted, never quietly a failure; and a product with no answer key draws no ceiling line and says why.
- [ ] T042 [US2] Write the failing test in `wfb/tests/test_summary.py`, then implement the refusal: any comparison, pairing, mean, cohort or standings row spanning two products is refused, naming both. This is the load-bearing guard of the feature.
- [ ] T043 [US2] Verify the rendered reports with the browser suite (`node tests/browser/suite.cjs`) in both themes, and confirm no figure lost its source line.

**Checkpoint**: two products can coexist without producing a misleading table.

---

## Phase 5: User Story 3 — A second foreign world on the same seam (P3)

**Goal**: AppWorld is a product, and adding it requires no change to the shared seam.

**Independent test**: run the same offline round shape as US1 against AppWorld, and confirm the shared files are untouched by the change that adds it.

- [ ] **T043a [US3] AppWorld needs its containerized server.** `AppWorld.execute(code)` calls `signal.SIGALRM`, which is POSIX-only, so the world can be built and graded on Windows but not driven on it ([research.md](research.md) S2). Bring up their container and reach it with `remote_environment_url`; the adapter is an HTTP client of the environment server. Also set `PYTHONUTF8=1` for that process: their evaluator's report writer trips on cp1252.
- [ ] T044 [US3] Record offline fixtures in `wfb/tests/fixtures/external/appworld/` from the S2 spike: task specs, a base database sample, a recorded `.evaluate()` return.
- [ ] T045 [P] [US3] Write the failing importer tests in `wfb/tests/test_external_import.py`: `--split test_normal` and `--split test_challenge` are refused by name, explaining that their reference solutions are not published and the answer-key competitor needs one; `train` and `dev` import; **no AppWorld content is written into this repository**, asserted by inspecting what the importer wrote.
- [ ] T046 [US3] Implement `wfb/wb_worlds/appworld/importer.py` and wire `wb corpus import-appworld` into the CLI.
- [ ] T047 [P] [US3] Write the failing adapter tests in `wfb/tests/test_worlds_appworld.py`, including that the source's own collateral-damage finding is recorded in `side_effects` beside ours and a disagreement surfaces.
- [ ] T048 [US3] Implement `wfb/wb_worlds/appworld/adapter.py` against the environment server: `/initialize`, `/execute`, `/evaluate`, `/close`, a service-keyed snapshot per app, and the interface document read from `data/api_docs/openapi/`. `positive_check` keeps `to_dict()` whole — `{success, difficulty, num_tests, passes, failures}` — with `passed = success` and `side_effects` taken from the `no_op`-labelled entries, which are AppWorld's own collateral-damage finding.
- [ ] T049 [P] [US3] Write `wfb/config/side-effects.appworld.yaml`.
- [ ] T050 [P] [US3] Write `wfb/config/products/appworld.yaml` and `wfb/config/plans/appworld-smoke.yaml`.
- [ ] T051 [US3] Import from `dev`, freeze a ten-task set into `wfb/tasks/appworld-dev-10/`, and run the offline round: answer key passes, null check passes none.
- [ ] T052 [US3] **Prove the seam**: show that the change adding AppWorld touched no shared file — `wb_world/adapter.py`, `registry.py`, `snapshot.py`, `grader/`, `http_shim.py`, `orchestrator.py`. If it did, the seam was shaped around its first source and that is the finding to fix.
- [ ] T053 [US3] Run `git status` and confirm no AppWorld content is staged or untracked inside the repository. Then run the quickstart's Part 2 AppWorld block and record the evidence.

**Checkpoint**: the seam is proven by a second implementation, not by assertion.

---

## Phase 6: User Story 4 — A world with a paid participant inside the attempt (P4)

**Goal**: τ²-bench is a product, and an attempt with two paid parties is disclosed, reserved and capped correctly.

**Independent test**: prepare a τ² round offline and read the disclosed attempt count and cost band; confirm both participants appear in the reservation and that a week that cannot cover the maximum refuses the round.

- [ ] T054 [US4] Record offline fixtures in `wfb/tests/fixtures/external/tau2/` (from the git clone, never from PyPI's `tau2`, which is an unrelated chemistry package) from the S3 spike: a domain's initial state, its tool list, a task with its `evaluation_criteria`, and a recorded reward result.
- [ ] T055 [P] [US4] Write the failing importer tests in `wfb/tests/test_external_import.py`, including that the source pin records the version and that a version below 1.0.1 is refused as non-comparable.
- [ ] T056 [US4] Implement `wfb/wb_worlds/tau2/importer.py` and wire `wb corpus import-tau2` into the CLI.
- [ ] **T056a [US4] Write the τ² world server**, `wfb/wb_worlds/tau2/server.py`, run by the τ² environment's own Python and reached over HTTP — the same shape `wb_world/server.py` already uses for the AutomationBench world. It holds one environment per attempt id and answers: the domain's tools and policy (`Environment.get_info`, `Tool.openai_schema`), a tool call (`make_tool_call`), the database state (`DB.model_dump`), and the reward. τ² cannot share this project's environment and its tools are Python functions, not a REST surface.
- [ ] **T056b [US4] Build the τ² message trajectory.** `EnvironmentEvaluator.calculate_reward` takes a message trajectory and replays it under `strict_replay`; it does not read a final state we hand it. Map our episode's `tool_calls` and the arm's turn log into τ² messages. This is the largest single piece of τ² work ([research.md](research.md) S3).
- [ ] T057 [P] [US4] Write the failing adapter tests in `wfb/tests/test_worlds_tau2.py`: domain environment per attempt, service-keyed snapshot, the three tools over its tool functions, and `positive_check` returning the source's reward **whole**, including its path-based parts.
- [ ] T058 [US4] Implement `wfb/wb_worlds/tau2/adapter.py`, including the simulated customer driven by the pinned model from the product configuration.
- [ ] T059 [US4] Write the failing tests in `wfb/tests/test_budget.py`: an attempt reserves **once** for the maximum liability of every participant; the per-attempt cap counts both; a week that cannot cover the total refuses the round and names the shortfall; the disclosed cost band before the round includes the second participant.
- [ ] T060 [US4] Implement the multi-participant reservation in `wfb/wb_orchestrator/orchestrator.py` and `wfb/wb_orchestrator/budget.py` usage — one reservation per attempt sized for all participants, settled from the sum. No second scope.
- [ ] T061 [P] [US4] Write the failing test, then confirm the participant fields enter the configuration hash by the existing path — changing the pinned customer model changes the round's hash.
- [ ] T062 [P] [US4] Write `wfb/config/side-effects.tau2.yaml`, `wfb/config/products/tau2.yaml` and `wfb/config/plans/tau2-smoke.yaml`.
- [ ] T063 [US4] Import one domain, freeze a ten-task set into `wfb/tasks/tau2-<domain>-10/`, and run the offline round plus the `--dry-run` disclosure from the quickstart.
- [ ] T064 [US4] Confirm the report carries both the composite-reward sentence and the paid-participant sentence.

**Checkpoint**: all three external worlds are selectable, and the one with a second paid party is honest about its money.

---

## Phase 7: Polish and cross-cutting

- [ ] T065 Run the whole suite offline with **none** of the three sources installed, and confirm every adapter refuses by name rather than raising an import error (FR-032, FR-007).
- [ ] T066 Run the whole suite on Windows detached with logs, wait for its exit, and record the test count against the count recorded at T026.
- [ ] T067 [P] Write the round evidence note in `monarch-benchmark/docs/rounds/` recording the three source pins, the frozen set hashes and the spike findings.
- [ ] T068 [P] Fold the spike results in `research.md` into their sections, so the document reads as settled research rather than as open questions.
- [ ] T069 Update the shared agent context by hand — no `update-agent-context` helper exists in `.specify/scripts/powershell/`: add the new paths to the file map in `CLAUDE.md`, add the feature row for `specs/026-external-benchmark-products/`, and update `monarch-benchmark/docs/STATE-OF-THE-PROGRAM.md` with where this leaves the program. Touch only the lines this feature owns — several sessions share this checkout.
- [ ] T070 Update `monarch-benchmark/PLAN.md`: the products under test are no longer one, and item E of the queue has moved.

---

## Dependencies

```
Phase 1 (Setup, spikes)
   │  T001 gates T027-T038      T002 gates T044-T053      T003 gates T054-T064
   ▼
Phase 2 (Foundational — the seam)          ← blocks every story; T026 is a hard gate
   ▼
Phase 3  US1  EnterpriseOps-Gym  (P1, MVP)
   ▼
Phase 4  US2  Honest reporting   (P2)      ← needs one external product to exist
   ├─────────────────────────────┐
   ▼                             ▼
Phase 5  US3  AppWorld  (P3)   Phase 6  US4  τ²-bench  (P4)
   └─────────────┬───────────────┘
                 ▼
          Phase 7  Polish
```

- **US1** depends on Phase 2 only.
- **US2** depends on US1, because there must be an external product to report on.
- **US3** and **US4** depend on Phase 2 and are independent of each other. Either can be
  built first, or both in parallel by different people; neither may modify a shared file
  (T052 is the check).
- T041's ceiling-line handling depends on T001's answer about whether EnterpriseOps-Gym
  can have an answer key.

## Parallel opportunities

- **Phase 1**: T001, T002, T003 are three independent spikes. T005, T006, T007 and T010
  are independent files.
- **Phase 2**: mostly serial — it is one slice through shared files, and parallel edits to
  shared files in a shared checkout is how this repository breaks.
- **Phases 5 and 6**: fully parallel with each other. Within each, the `[P]` tasks touch
  different files: importer tests, adapter tests and configuration files.
- **Phase 7**: T067 and T068 are independent documents.

## Implementation strategy

**MVP is Phase 1 + Phase 2 + Phase 3.** That delivers a second product under test,
running and grading under the lab's own rules, which is the whole value of the feature.
Everything after it widens the evidence and protects the reports.

**Stop points that are still coherent deliveries**:

- After Phase 3: one external product, one frozen set, one round.
- After Phase 4: that product safely reportable beside the existing one.
- After Phase 5: the seam proven by a second implementation.
- After Phase 6: all three, with the money model complete.

**The one thing that is not optional**: T026. If the seam breaks AutomationBench, stop
and fix it before writing a single adapter.
