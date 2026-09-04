# Tasks: Task Sets by Difficulty and the Scored AutomationBench Domains

**Input**: Design documents from `/specs/005-task-tiers/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md. Feature 001 must be green (the config loader, the plans, the
corpus commands). Features 002 and 004 are not prerequisites: this feature
touches neither the Monarch competitor nor any run.

**Tests**: Required. Constitution §II mandates red → green → refactor; every task
that adds logic starts with a failing test in the named test file. Everything is
offline: no key, no network, no model call, no `wb run` at any point.

**Organization**: Grouped by user story in spec priority order. US2 (the measure)
and US3 (the draw) come before US1 (the import) in build order even though all
three are P1: the draw is testable against a small synthetic corpus in seconds,
while the import is slow and depends on the vendored tree, and the hash change
underneath both must land first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 from spec.md

## Path Conventions

All code paths are under `monarch-benchmark/workflowbench/` (written as `wb/`
below). Tests run with
`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.

---

## Phase 1: Setup

- [ ] T001 [P] Create `wb/tests/fixtures/mini-corpus/` : twelve hand-written task files across three fake domains with known scores (services, expected changes, tools chosen so the terciles are arithmetic anyone can check by hand), one with an empty `expected_changes`, one whose `contract_sha256` deliberately does not match its content, one with a `meta` key in `initial_state`
- [ ] T002 [P] Write the four plans `wb/config/plans/tier-simple.yaml`, `tier-medium.yaml`, `tier-complex.yaml`, `random-10.yaml` per `contracts/config-files.md` (same seven competitors, baseline and mode as `pilot-monarch-create-run`; `approved_by: null`; each description stating "prompts: 10; attempts per prompt and competitor: 2; attempts per competitor: 20 = 10 × 2")

---

## Phase 2: Foundational (blocking)

**Purpose**: the hash ignore list, which everything that writes a drawn file depends on.

- [ ] T003 Write failing tests in `wb/tests/test_tiers.py::test_label_keys_are_not_hashed`: `contract_hash` returns the same value for a task with and without `info.tier` / `info.domain`; a change to any other field still moves it
- [ ] T004 Write failing test in `wb/tests/test_run_config.py::test_existing_hashes_do_not_move`: the `contract_sha256` recorded in each of the ten pilot task files and in twenty sampled `corpus/imported-simple` files equals `contract_hash` of that file's content, so the ignore-list change moved no existing hash
- [ ] T005 Add `info.tier` and `info.domain` to the ignore list in `wb/wb_orchestrator/orchestrator.py::contract_hash` per `data-model.md` §8 (`# ponytail: two ignored keys, not a metadata sidecar; every future label goes here deliberately`). T003 and T004 green

**Checkpoint**: a label can be added to a task copy without making it a different task.

---

## Phase 3: User Story 2 — Classify the corpus by difficulty (P1)

**Goal**: an objective score per task, two cut points, a tier per task, all reproducible.

**Independent test**: `wb/tests/test_tiers.py` against `fixtures/mini-corpus/`.

- [ ] T006 [US2] Write failing tests in `wb/tests/test_tiers.py`: `score_task` on a task with two services, three expected changes and four tools returns 9; a `meta` key in `initial_state` is not counted; a task with no tools and one service and one expected change returns 2
- [ ] T007 [US2] Create `wb/wb_orchestrator/tiers.py` with `score_task(task) -> int` per `data-model.md` §2. T006 green
- [ ] T008 [US2] Write failing tests in `wb/tests/test_tiers.py`: `tier_cuts(scores)` on a list whose terciles are unambiguous returns those two values; `tier_of(score, cuts)` returns `simple` at and below `low`, `complex` strictly above `high`, `medium` between; a score exactly on either cut point lands in the lower tier
- [ ] T009 [US2] Implement `tier_cuts` and `tier_of` in `wb/wb_orchestrator/tiers.py` per `data-model.md` §3. T008 green
- [ ] T010 [US2] Write failing test in `wb/tests/test_tiers.py::test_usable_pool`: `load_corpus(dirs)` returns one entry per task with its domain, score and hash, and an `excluded` mapping naming the fixture's task with no approval rule ("no approval rule…") and the one whose hash does not match ("contract hash does not match content"); neither is scored
- [ ] T011 [US2] Implement `load_corpus` in `wb/wb_orchestrator/tiers.py` per `research.md` R9 (reuse the two checks `validate_corpus` already performs; do not re-implement them). T010 green

---

## Phase 4: User Story 3 — Draw four frozen task sets (P1) 🎯 MVP

**Goal**: four folders and a manifest, byte-reproducible from a seed, every drawn task a copy with an unchanged hash.

**Independent test**: `wb/tests/test_tiers.py::test_draw_is_deterministic` on the mini corpus.

- [ ] T012 [US3] Write failing test in `wb/tests/test_tiers.py::test_stratified_draw`: over a tier holding four domains with uneven counts, `draw_tier(pool, per_tier, rng)` returns as many distinct domains as the counts allow, fills the shortfall from the rest, and walks the domains in alphabetical order
- [ ] T013 [US3] Implement the round-robin draw in `wb/wb_orchestrator/tiers.py` per `research.md` R8 (`# ponytail: round-robin, not proportional allocation; with ten slots proportional is mostly rounding rules`). T012 green
- [ ] T014 [US3] Write failing test in `wb/tests/test_tiers.py::test_tier_too_small_refuses`: a tier with fewer usable tasks than `per_tier` raises, naming the tier and the count, and nothing is written
- [ ] T015 [US3] Write failing test in `wb/tests/test_tiers.py::test_drawn_task_is_a_frozen_copy`: every written file equals its corpus original except for `info.tier` and `info.domain`, and its `contract_sha256` is unchanged; `validate_corpus` on the written folder reports zero contract drift
- [ ] T016 [US3] Implement the writer in `wb/wb_orchestrator/tiers.py`: byte copy plus the two keys, sorted keys, explicit trailing newline. T015 green
- [ ] T017 [US3] Write failing test in `wb/tests/test_tiers.py::test_draw_is_deterministic`: `draw(corpus, seed=1, out=A)` then `draw(corpus, seed=1, out=B)` produce identical file trees (compare every file's bytes and the manifest); `seed=2` differs; the fixed consumption order of `research.md` R7 is what makes it hold
- [ ] T018 [US3] Implement `draw()` end to end in `wb/wb_orchestrator/tiers.py` per `data-model.md` §9: one `random.Random(seed)`, tiers in order, domains alphabetical, candidates sorted then shuffled, then the unstratified random set. T017 green
- [ ] T019 [US3] Write failing test in `wb/tests/test_tiers.py::test_manifest`: the manifest matches `contracts/config-files.md` — the measure in words, both cut points, the seed, `per_tier`, one corpus row per folder with total and usable counts, the `excluded` mapping with its reasons, and per set the per-domain counts and one row per drawn task with `task`, `domain`, `score`, `tier` and `contract_sha256`; the `random-10` rows carry each task's real tier, and those files carry `info.tier: random`
- [ ] T020 [US3] Implement the manifest writer in `wb/wb_orchestrator/tiers.py`. T019 green
- [ ] T021 [US3] Write failing test in `wb/tests/test_tiers.py::test_corpus_is_not_written`: after a draw, every file under the corpus folders has its original bytes and modification time; make it green if anything writes back
- [ ] T022 [US3] Add the `corpus tiers` subcommand to `wb/wb_orchestrator/cli.py` (`--seed` required, `--per-tier`, repeatable `--corpus`, `--out`) with the output and exit codes of `contracts/cli.md`; assert them in `wb/tests/test_tiers.py::test_cli`

**Checkpoint**: four frozen sets and a manifest, reproducible from a seed, on the fixture corpus.

---

## Phase 5: User Story 1 — Import the six scored domains (P1)

**Goal**: the corpus grows to 800 tasks with derived approval rules, through the existing machinery.

**Independent test**: `wb/tests/test_corpus.py` against a stub dataset, so the suite does not need the vendored tree.

- [ ] T023 [US1] Write failing tests in `wb/tests/test_corpus.py`: `import_ab(["finance"], dest)` against a stub `get_domain_dataset` writes tasks carrying the request text, the tools needed, the starting data, the assertions, empty change lists and a hash; `import_ab` with several domains and a `--dest` containing `{domain}` writes one folder per domain; several domains without `{domain}` raise
- [ ] T024 [US1] Extend `import_ab` in `wb/wb_orchestrator/corpus.py` for the per-domain destination and keep the conversion untouched (`# ponytail: one function over the vendor's own loader; a second reader of their Python would rot`). T023 green
- [ ] T025 [US1] Write failing test in `wb/tests/test_corpus.py::test_all_domains`: `--domains all` resolves to the six scored domains plus the baseline one, in a fixed order; an unknown domain name is refused with the list of known ones
- [ ] T026 [US1] Implement the `all` alias in `wb/wb_orchestrator/corpus.py` from the vendor's own public-domain list plus the baseline domain. T025 green
- [ ] T027 [US1] Write failing test in `wb/tests/test_corpus.py::test_missing_services_reported`: given a stub domain whose starting data seeds a service the product does not list, the import names it and returns a non-zero code; given only listed services, it prints "none" and returns zero
- [ ] T028 [US1] Implement the service check in `wb/wb_orchestrator/corpus.py` (compare the union of `initial_state` keys, minus `meta`, with the product's `services`) and wire it into `cli.py`'s `import-ab` per `contracts/cli.md`. T027 green
- [ ] T029 [US1] Update `wb/wb_orchestrator/cli.py`'s `import-ab` parser: `--domains` help mentions `all`, `--dest` help mentions `{domain}`, `--product` added (default `simulated-apps`) for the service check; assert in `wb/tests/test_corpus.py`

---

## Phase 6: User Story 4 — One round per task set (P2)

**Goal**: four plans that load, validate and state their size in the agreed words.

**Independent test**: `wb/tests/test_config.py`.

- [ ] T030 [US4] Write failing test in `wb/tests/test_config.py::test_tier_plans`: the four plans load; each names its own task set; all four carry the same seven competitors, baseline `claude-opus-5/api`, `mode: create-run`, `repetitions: 2`, `audience: internal` and `approved_by: null`; a plan naming a mode the product or the harness does not support still fails validation. Make it green (T002 wrote the files; fix them until the test passes)
- [ ] T031 [US4] Write failing test in `wb/tests/test_run_config.py::test_banner_states_the_arithmetic`: the run banner prints "prompts: 10; attempts per prompt and competitor: 2; attempts per competitor: 20 = 10 × 2" and "competitors: 7; attempts in the round: 140", and never a bare per-competitor total
- [ ] T032 [US4] Implement the banner wording in `wb/wb_orchestrator/cli.py::_banner` per `contracts/cli.md`, for every plan and not only these four. T031 green

---

## Phase 7: User Story 5 — Read what changed (P3)

**Goal**: the plan of record, the project instructions and the configuration docs describe the feature.

**Independent test**: read the files against FR-030 and FR-031.

- [ ] T033 [P] [US5] Update `monarch-benchmark/PLAN.md` with the lines this feature contributes: the tracked work under WS-F (import the six scored domains; derive and validate their rules; draw the four sets), the deliverable for the tiered rounds with its definition of done, the decisions of 4 Sep 2026 (three tiers of ten run as separate rounds rather than the vendor's hardest-ten method; the difficulty measure and its terciles, with domain-as-proxy as the recorded alternative; drawn tasks are frozen copies whose hash does not move), and this feature's open questions with owners
- [ ] T034 [P] [US5] Update the project `CLAUDE.md`: add `specs/005-task-tiers/`, the four task sets, `tasks/tiers-manifest.yaml` and `wb corpus tiers` to the "What lives where" table, and update the status paragraph
- [ ] T035 [P] [US5] Update `wb/config/README.md`: the four plans, the drawn task sets, the manifest, and the two corpus commands with the note that both are free and offline

---

## Phase 8: Polish and gates

- [ ] T036 Run the full suite `cd wb && uv run python -m pytest tests -q`; paste the summary line below this task; fix any regression before continuing
- [ ] T037 **Free, offline**: `uv run wb corpus import-ab --domains all --dest 'corpus/imported-{domain}'`; paste the per-domain counts and the service line. If a service is named, stop and add it to `wb/config/products/simulated-apps.yaml` and `wb/config/side-effects.yaml` before continuing
- [ ] T038 **Free, offline**: for each of the six scored domains run `wb corpus declare corpus/imported-<d> --overwrite --product simulated-apps` then `wb corpus validate corpus/imported-<d>`; paste the totals and record how many tasks came out with unmapped assertion types — that number answers spec Open Question 4 and goes to Lucas
- [ ] T039 **Gate, no money, decision**: ask Carlos and Lucas to confirm the difficulty measure (services seeded + expected changes + tools needed, terciles at the corpus's cut points), with the domain-as-proxy alternative on the table. Record the answer in `research.md` R5 and `PLAN.md`. **The drawn sets are not committed before this is answered** (FR-013)
- [ ] T040 **Free, offline**: `uv run wb corpus tiers --seed <the agreed seed>`; paste the cut points and the four per-domain breakdowns; then `wb corpus validate tasks/tier-complex` (contract drift must be 0) and a second draw into a temporary directory with `diff -r` showing no differences. Commit the six corpus folders, the four task sets and the manifest
- [ ] T041 Refresh the knowledge graph from the repo root: `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`; confirm `graphify-out/GRAPH_REPORT.md` lists `tiers` and `score_task`
- [ ] T042 **The four rounds are not part of this branch.** Each needs Carlos's approval of that specific run, stated as "prompts: 10; attempts per prompt and competitor: 2; attempts per competitor: 20 = 10 × 2; competitors: 7; attempts in the round: 140" with a cost band, run one at a time in the order simple, medium, complex, random. Record here only the date each was approved and its report path

---

## Dependencies

```
Phase 1 → Phase 2 → US2 (Phase 3) → US3 (Phase 4) → US1 (Phase 5)
US4 (Phase 6) any time after Phase 1; US5 (Phase 7) any time after Phase 4.
Phase 8 last; T037 → T038 → T039 → T040 in order.
```

- US3 needs the score, the cut points and the pool of US2, and the hash ignore
  list of Phase 2.
- US1 is independent of US2 and US3 in code but is built after them, because the
  draw is testable in seconds against a fixture and the import is slow and needs
  the vendored tree.
- T039 gates T040 only: the code and its tests land before the measure is
  confirmed; the drawn artefacts do not.

## Parallel execution examples

- Phase 1: T001 and T002 together.
- Phase 7: T033, T034 and T035 together.
- Phase 5 and Phase 6 touch different files and can run in parallel once Phase 4
  is done.

## Implementation strategy

1. **MVP** = Phases 1–4: the draw works, is deterministic, freezes what it copies
   and records how it chose. That alone proves rule 5 for the new sets and gives
   Carlos something to look at before any import runs.
2. Phase 5 grows the corpus. It is separated because it is the slow half and the
   half that depends on the vendored tree — and because if Lucas's patches land
   first, this is the phase that is re-run, not the draw's code.
3. Phase 6 makes the sets runnable. The plans are four small files and one banner
   wording; nothing here starts a round.
4. Phase 7 and the graph refresh close the work. T039 is the one decision the
   feature cannot take for itself, and it gates only the committed artefacts.
