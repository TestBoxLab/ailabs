# Tasks: Results Report as HTML Tables, Per Round and Across Rounds

**Input**: Design documents from `/specs/006-html-report/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md. Features 001, 002 and 004 as they stand; no code of theirs is
changed by this feature.

**Tests**: Required. Constitution section II mandates red -> green -> refactor;
every task that adds logic starts with a failing test in the named test file.
Every test is offline: no key in the environment, no network, no `wb run`, no
money at any point in this feature.

**Organization**: Grouped by user story in spec priority order. US1 (the
per-round page) is the MVP and is built first; US2 (Monarch's phase columns) and
US4 (the gate) fall out of it; US3 (the summary) comes last because it renders
tables US1 defines.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1-US5 from spec.md

## Path Conventions

All code paths are under `monarch-benchmark/workflowbench/` (written as `wb/`
below). Tests run with
`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.

---

## Phase 1: Setup

- [ ] T001 [P] Create `wb/tests/test_html_report.py` with the seeded-store fixtures this feature needs, modelled on `tests/test_m4.py::seeded_store`: (a) `four_arm_store` - 2 tasks x 4 competitors x 2 repetitions, one competitor with an infrastructure failure, one with an agent error, one task failed by everyone; (b) `phase_store` - one competitor whose rows carry `phases` with `authoring`, `execution` and `model:opus-4.8`, plus flags `questions_asked=2` and `no_workflow`; (c) `zero_pass_store` - a competitor that passes nothing. Fixtures only; no assertions yet
- [ ] T002 [P] Create `wb/tests/test_summary.py` with a `three_round_store` fixture: three runs of the same three competitors on three different task sets, one of whose plans is named `random-10`

---

## Phase 2: Foundational (blocking) - the metrics module

**Purpose**: every number the pages render, computed in one place and asserted
against hand-computed values before any HTML exists.

- [ ] T003 Write failing tests in `wb/tests/test_html_report.py::test_counts` for `wb_report.metrics.competitor_metrics(rows, k)`: `attempts`, `passed`, `infra`, `agent_errors`, `timeouts` on `four_arm_store`, each compared with a number written out in the test, not recomputed from the same rows
- [ ] T004 Create `wb/wb_report/metrics.py` with `competitor_metrics()` returning the counts of T003 per `data-model.md` section 2.2. T003 green
- [ ] T005 Write failing tests `::test_rates_come_from_wb_stats`: `strict_pass` and `pass_over_repetitions` equal `arm_summary(rows)["strict_pass"]` and `pass_hat_k(rows, k)` exactly - the test calls those functions itself and compares, so a reimplementation fails
- [ ] T006 Add the two rate fields to `competitor_metrics` by calling `wb_stats.arm_summary` and `wb_stats.pass_hat_k`. T005 green
- [ ] T007 Write failing tests `::test_infra_excluded_from_denominator_and_counted`: on a competitor with 4 attempts of which 1 is `infra:rate_limit` and 2 of the remaining 3 pass, `infra == 1`, `infra_rate == 0.25`, and the strict pass denominator is 3 - all three visible on one entry (FR-005, SC-004)
- [ ] T008 Write failing tests `::test_cost_metrics`: `cost_total` sums every attempt including infrastructure ones; `cost_per_attempt` divides by all attempts; `cost_per_passed` divides by the passed non-infrastructure count; on `zero_pass_store` `cost_per_passed is None` (FR-027, SC-005)
- [ ] T009 Implement the cost fields in `wb/wb_report/metrics.py` per `contracts/report.md` section 1. T007 and T008 green
- [ ] T010 Write failing tests `::test_token_metrics`: the four token sums, `cache_hit_rate == cached / prompt`, and `cache_hit_rate is None` when prompt is 0; a row with `tokens: null` contributes 0 and does not raise
- [ ] T011 Implement the token fields. T010 green
- [ ] T012 Write failing tests `::test_wall_clock_is_the_phase_sum`: `attempt_seconds` is the sum of the row's phase `wall_clock_s`; a row with no phase carrying one contributes to neither the mean nor the median; `wall_clock["n_with"]` and `["n_total"]` report the split; both means are `None` when no row has one (research R6)
- [ ] T013 Implement `attempt_seconds()` and the `wall_clock` block using `statistics.median`. T012 green
- [ ] T014 Write failing tests `::test_phase_and_monarch_fields` on `phase_store`: `phases` carries `authoring` and `execution` with their wall-clock and cost; `cost_per_model` maps `opus-4.8` to the summed cost of the `model:opus-4.8` phase; `questions_asked == 2`; `declined_to_build == 1`; and on `four_arm_store` all four are empty or zero without raising
- [ ] T015 Implement the phase fields, reading phase names off the row rather than matching a known list (`# ponytail: phase names read off the row; a phase 002 or 004 adds needs no change here`). T014 green
- [ ] T016 Write failing tests `::test_comparison_row`: `wb_report.metrics.comparison(rows_arm, rows_base, k)` returns the wins / losses / both / neither / pairs / dropped-infra of `paired_wl` verbatim, the McNemar block, `strict_pass_diff_pp` in signed percentage points, both ratios, and `None` for a ratio whose denominator is 0
- [ ] T017 Write failing tests `::test_verdict_wording`: the four exact strings of `contracts/report.md` section 2 for p >= 0.05, p < 0.05 with more wins, p < 0.05 with more losses, and zero pairs - asserted as literals so a reworded verdict fails
- [ ] T018 Implement `comparison()` and `verdict()` in `wb/wb_report/metrics.py`. T016 and T017 green

**Checkpoint**: every number of the page exists and is tested without any HTML.

---

## Phase 3: User Story 1 - the per-round page (P1) 🎯 MVP

**Goal**: `wb report` writes a page with four tables and a provenance block.

**Independent test**: `wb/tests/test_html_report.py::test_page_has_the_four_tables`.

- [ ] T019 [US1] Write failing tests `::test_matrix_block`: `build_report` returns a `matrix` block per `data-model.md` section 2.4 - one row per task, one cell per competitor with `passed`, `attempted`, `infra` and a `category` from the five of `contracts/report.md` section 3; a cell whose attempts were all infrastructure reads `attempted == 0` and `infra == 2`; `has_domain` and `has_tier` are false when no task carries them (FR-007, FR-009, research R8)
- [ ] T020 [US1] Write failing tests `::test_failures_block`: one entry per failed attempt with task, competitor, repetition, termination, error and the `path` of each unexpected change, ordered by task then competitor then repetition; an empty list when nothing failed (FR-010)
- [ ] T021 [US1] Write failing tests `::test_size_and_provenance_blocks`: `size` carries prompts, repetitions, per-competitor as the product, competitors and total; `provenance` carries the configuration hash, price tables, task hashes, run dates, stop reason and audience (FR-011, FR-012)
- [ ] T022 [US1] Extend `wb/wb_report/report.py::build_report` with `size`, `metrics`, `comparisons`, `matrix`, `failures` and `provenance`, reusing the rows it already reads per competitor and leaving `figures` untouched. T019, T020, T021 green
- [ ] T023 [US1] Write failing test `::test_markdown_is_unchanged`: `render_md` on the seeded stores of `test_m4.py` produces exactly what it produces today (the strings that file already asserts), proving the new blocks changed nothing (FR-013, SC-008)
- [ ] T024 [US1] Create `wb/wb_report/html.py` with `_esc()`, `_fmt()` per `data-model.md` section 4, and `_table(headers, rows, source_line, title)`; write failing tests `::test_table_helper` first: `None` renders `n/a`, a rate renders `90.0%`, money renders `US$ 1.3986`, and a cell containing `<script>` is escaped (FR-027, research R4)
- [ ] T025 [US1] Write failing test `::test_page_has_the_four_tables`: `render_html(build_report(store, run))` contains four `<table` elements, the header size line, and a source line under each table; assert on the four table captions by their exact text
- [ ] T026 [US1] Implement `render_page()` in `wb/wb_report/html.py` and make `wb/wb_report/report.py::render_html` delegate to it, keeping its signature. T025 green
- [ ] T027 [US1] Write failing test `::test_matrix_details_table_repeats_the_hover_text`: every `title` attribute in the matrix has its text repeated in the details table below it, so nothing is hover-only (FR-008); make it green
- [ ] T028 [US1] Write failing test `::test_no_inf_or_nan`: neither `inf` nor `nan` appears in the rendered page for `zero_pass_store`, and `n/a` appears in the cost-per-passed cell (SC-005); make it green if anything slipped through
- [ ] T029 [US1] Add the inline stylesheet to `wb/wb_report/html.py`: borders, padding, right-aligned numeric cells, zebra rows, a sticky header, and the two themes `render_html` already switches on by audience. No external stylesheet (FR-026, FR-028)
- [ ] T030 [US1] Write failing test `::test_sort_script_present_and_optional`: the page contains the sorting script by default and does not when `render_page(..., sortable=False)`; implement the ~12-line click handler per research R5 (`# ponytail: a click handler over table.rows, not a sorting library`)
- [ ] T031 [US1] Add `--no-sort` to `wb report` in `wb/wb_orchestrator/cli.py` per `contracts/cli.md`, threaded through `write_report`; test in `wb/tests/test_html_report.py` that `main(["report", ...,"--no-sort"])` writes a page with no `<script`
- [ ] T032 [US1] Write failing test `::test_single_competitor_round`: a round with one competitor renders no comparison table and says so in a line rather than rendering an empty table; and `::test_no_failures` renders `no attempt failed` instead of the failures table; make both green

**Checkpoint**: `wb report` writes the page. MVP complete.

---

## Phase 4: User Story 2 - Monarch's phase columns (P1)

**Goal**: the phase split, cost per model, questions asked and declined-to-build
appear where they exist and nowhere else.

**Independent test**: `wb/tests/test_html_report.py`, `phase_store`.

- [ ] T033 [US2] Write failing test `::test_phase_columns_render`: on `phase_store` the metrics table has authoring and execution wall-clock and cost columns, a cost-per-model cell reading `opus-4.8 US$ ...`, a questions-asked cell and a declined-to-build cell (FR-014, FR-015)
- [ ] T034 [US2] Write failing test `::test_phase_columns_absent_without_phases`: on `four_arm_store` (only a `run` phase) none of those column headers appears in the page at all (FR-016)
- [ ] T035 [US2] Write failing test `::test_absent_authoring_is_na`: a store whose rows have `execution` but no `authoring` - the run-only shape of feature 004 - renders `n/a` in the authoring cells and never `0` (FR-016, spec US2 scenario 3)
- [ ] T036 [US2] Implement the conditional columns in `wb/wb_report/html.py`. T033, T034, T035 green
- [ ] T037 [US2] Write failing test `::test_missing_cost_share_on_the_source_line`: a store with a Monarch competitor flagged `cost_missing` renders `cost missing on 1/3 attempts` under the metrics table, from the existing `_source_suffix`; make it green

---

## Phase 5: User Story 4 - the gate holds in every table (P1)

**Goal**: no table, hover text, caption or provenance line names a competitor
the audience excludes.

**Independent test**: `wb/tests/test_html_report.py::test_gate_in_every_table`.

- [ ] T038 [US4] Write failing test `::test_gate_in_every_table`: a store with `monarch` and `monarch-lab` rendered for `public-rung2` - the string `monarch-lab` appears nowhere in the file, in any table, `title` attribute, caption or provenance line (FR-023, SC-003)
- [ ] T039 [US4] Write failing test `::test_public_audience_shows_ratios_not_dollars`: for a non-internal audience no `US$` appears in any table and the cost columns are ratios against the baseline (FR-024)
- [ ] T040 [US4] Write failing test `::test_renderer_cannot_query_the_store`: `wb/wb_report/html.py` imports neither `Store` nor `sqlite3` - assert on the module's source or its imports, so a future change that passes a store in fails the suite (plan design note 1, research R7)
- [ ] T041 [US4] Make T038-T040 green: every new block is built inside `build_report` from the already-gated `arms` list, and the renderer receives only the dictionary
- [ ] T042 [US4] Write failing test `::test_internal_watermark_survives`: an internal page containing a lab competitor still carries the DO NOT EXPORT watermark the markdown report already emits; make it green

---

## Phase 6: User Story 3 - the summary page (P2)

**Goal**: two to six rounds on one page, with an aggregate and the
stratification check.

**Independent test**: `wb/tests/test_summary.py`.

- [ ] T043 [US3] Write failing tests in `wb/tests/test_summary.py::test_build_summary`: `wb_report.report.build_summary(store, run_ids, audience, baseline)` returns the dictionary of `data-model.md` section 3 - one round entry per run with its own metrics and source, the competitor list, and an aggregate whose mean is the mean of per-round rates
- [ ] T044 [US3] Implement `build_summary()` in `wb/wb_report/report.py`, calling `build_report` per round. T043 green
- [ ] T045 [US3] Write failing test `::test_aggregate_counts_only_the_rounds_a_competitor_ran`: a competitor present in two of three rounds has `n_rounds == 2` and a mean over those two (FR-019, spec US3 scenario 5); make it green
- [ ] T046 [US3] Write failing test `::test_no_pooled_paired_figures`: the summary dictionary has no field carrying wins, losses or a McNemar p, and the rendered page contains neither `McNemar` nor `W /` outside a per-round metrics table; the never-pooled sentence is present verbatim (FR-021, rule 5)
- [ ] T047 [US3] Write failing test `::test_stratification_block`: with a round whose plan is named `random-10` and three tier rounds, the block gives per competitor the random rate, the mean of the tiers and the difference in percentage points; with no such round the block is absent rather than empty (FR-020)
- [ ] T048 [US3] Implement the stratification block and the per-tier aggregate columns (present only when the rounds carry `info.tier`) in `wb/wb_report/report.py` and `wb/wb_report/html.py`. T046, T047 green
- [ ] T049 [US3] Implement `render_summary_page()` in `wb/wb_report/html.py`, reusing `_table()` and the stylesheet; write the failing test `::test_summary_page_shape` first: one metrics table per round each with its own source line, then the aggregate table, then the statement
- [ ] T050 [US3] Write failing tests `::test_summary_cli` in `wb/tests/test_summary.py` for `contracts/cli.md`: `--runs a,b` writes the file; `--plans p1,p2` prints the run picked for each and uses the most recent; `--runs` and `--plans` together are refused; one round is refused; seven rounds are refused; an unknown run is refused naming it and writes nothing; the default `--out` path is `out/summary-<timestamp>-<audience>.html` (FR-017, FR-018, FR-022)
- [ ] T051 [US3] Add the `summary` subcommand to `wb/wb_orchestrator/cli.py` per `contracts/cli.md`. T050 green
- [ ] T052 [US3] Write failing test `::test_summary_applies_the_gate_per_round`: a public summary over rounds containing a lab competitor omits it from every round's table and refuses when a round is left empty (FR-025); make it green

---

## Phase 7: The real round, and polish

- [ ] T053 Write `wb/tests/test_html_report.py::test_recorded_run_renders_four_tables`: open `out/wb.sqlite3`, build the internal page for `run-20260904-125645` with baseline `claude-opus-5/api`, and assert the four tables, 4 metrics rows, 3 comparison rows, 10 matrix rows, the size line `20 = 10 x 2`, the configuration hash `a5d4e4135f3f2385`, and no `inf` or `nan`. Mark it `pytest.mark.skipif` on the database being absent so a fresh clone stays green (SC-001)
- [ ] T054 Write `wb/tests/test_html_report.py::test_page_and_markdown_agree`: for the seeded stores, every strict pass rate and cost total printed in the page equals the value in the markdown report of the same run, parsed out of both strings (SC-002)
- [ ] T055 Run the full suite `cd wb && uv run python -m pytest tests -q`; paste the summary line below this task; fix any regression before continuing
- [ ] T056 Render the page for `run-20260904-125645` by hand (`uv run wb report run-20260904-125645 --audience internal --baseline claude-opus-5/api`), open it in a browser, and paste here: the four table captions, the metrics row for `oracle`, and confirmation that sorting a column works and that the page opens with no network access
- [ ] T057 [P] Update `wb/config/README.md` (or the CLI help if the reports are not documented there) with `wb summary` and the fact that `wb report`'s HTML file is now the official page
- [ ] T058 Refresh the knowledge graph from the repository root: `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`; confirm `graphify-out/GRAPH_REPORT.md` lists `metrics` and `html` under `wb_report`
- [ ] T059 Ask Carlos the three open questions of `spec.md` (whether the median excludes rows with no wall-clock; where the summary page is filed by default; whether sortable columns earned their twelve lines) and record the answers in `research.md`

---

## Dependencies

```
Phase 1 -> Phase 2 -> US1 (Phase 3) -> US2 (Phase 4) -> US4 (Phase 5) -> US3 (Phase 6) -> Phase 7
```

- Every story depends on Phase 2: the metrics module is what all of them render.
- US2 and US4 both edit `wb/wb_report/html.py`; run them in order, not in
  parallel.
- US3 renders the metrics table US1 defines; it cannot start earlier.
- T053 and T054 need every table to exist and so come last.

## Parallel execution examples

- Phase 1: T001 and T002 together.
- Phase 2: T003/T005/T007/T008/T010/T012/T014/T016/T017 are all in one test file
  and are written in order; their implementations (T004, T006, T009, T011, T013,
  T015, T018) each follow their own test immediately.
- Phase 7: T057 alongside T055.

## Implementation strategy

1. **MVP** = Phases 1-3: `wb report` writes the page with four tables for any
   existing round. That alone replaces the escaped-markdown file and makes rules
   7, 8 and 9 visible on one screen.
2. Phase 4 adds the columns the Monarch pilots need; Phase 5 proves the gate
   survives four new tables, which is the one way this feature could do harm.
3. Phase 6 is the second reader of the same tables and can be deferred without
   blocking a round: until it lands, two rounds are read as two pages.
4. Phase 7 proves it against the real recorded round and refreshes the graph.
   Nothing in this feature costs money, so there is no gated live step.
