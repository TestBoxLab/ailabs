# Implementation Plan: Results Report as HTML Tables, Per Round and Across Rounds

**Branch**: `006-html-report` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-html-report/spec.md`; design of
record `docs/superpowers/specs/2026-09-04-html-report-design.md`.

## Summary

Add `wb_report/metrics.py`, one module holding every formula of
`contracts/report.md`, computed from the attempt rows and calling
`wb_stats.arm_summary`, `pass_hat_k` and `paired_wl` rather than reimplementing
them. Extend `build_report` to put the new blocks (metrics rows, comparison
rows, task matrix, failures, provenance) into the dictionary it already returns.
Replace `render_html` with a real page built by `wb_report/html.py`: a
`_table()` helper, one inline stylesheet, an optional 12-line sorting script.
Add `wb summary` on top of the same builder for two to six rounds, with an
aggregate table that is a mean of per-round rates. `render_md` and the markdown
file are untouched. No schema change, no new dependency, no money: every test
runs offline against seeded stores and the recorded run in `out/wb.sqlite3`.

## Technical Context

**Language/Version**: Python 3.13, `uv`

**Primary Dependencies**: none new. `html`, `statistics`, `json`, `pathlib` from
the standard library; pydantic 2 and PyYAML already present and untouched here.

**Storage**: the existing SQLite results store, read-only. No migration.

**Testing**: pytest, offline, no key in the environment. Seeded stores as in
`tests/test_m4.py`, plus one rendering check against `out/wb.sqlite3`'s
`run-20260904-125645` (80 attempts, four competitors), skipped when that file is
absent so CI stays green on a fresh clone.

**Target Platform**: Windows host (Carlos) and Linux CI. The page is one file
that opens from disk with no network access.

**Project Type**: CLI tool + library (`workflowbench`).

**Performance Goals**: a page for a 200-task, 6-competitor round (2,400 attempts)
in under 2 s and under 2 MB of HTML. The task matrix is the only quadratic
surface and it is tasks x competitors, not attempts.

**Constraints**: constitution section III (no rule of `PLAN.md` section 1
changes; rules 7, 8, 9 and 10 are what this feature renders), section IV (no
command here spends money), section V (English, plain names). Stdlib only.

**Scale/Scope**: 2 new modules, 3 changed modules, 2 new test files; roughly 500
lines of code and 400 of tests.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Brainstorm -> spec -> plan -> tasks -> execute | PASS | Brainstormed with Carlos 4 Sep; design of record approved; spec 006 written from it; this is the plan. |
| II. Test-first | PASS | Every metric gets a failing test asserting its value against a hand-computed number on a seeded store, before the formula exists. The rendering check on the recorded run is the last of them. |
| III. Methodology fixed; inputs change | PASS | No rule of `PLAN.md` section 1 changes. This feature is rule 7 (infrastructure failures excluded and reported separately), rule 8 (every figure carries its source), rule 9 (cost complete, price table versioned, missing-cost share stated) and rule 10 (audience rules are code) made visible. Rule 5 is enforced by refusing pooled paired figures on the summary. |
| IV. Money and pre-registration gates | PASS | Neither `wb report` nor `wb summary` spends anything; both read the store. No task is edited; no hash moves. |
| V. Plain language, graph-grounded | PASS | Graph consulted (`build_report`, `arm_summary`, `Store.episodes` god nodes). Column headers and verdict strings in plain words. Graph refresh is the last task. |

**Additional constraints**: stdlib-first (research R3); every cell escaped
(R4); the renderer never touches the store (R7).

Post-design re-check (after Phase 1): unchanged, PASS. Four ponytail notes carry
into code comments: rendering only, no stored field added (R1); one `_table()`
helper rather than a template engine (R3); a click handler rather than a sorting
library (R5); the renderer takes a dictionary, not a `Store` (R7).

## Project Structure

### Documentation (this feature)

```text
specs/006-html-report/
├── spec.md
├── plan.md                    # this file
├── research.md                # R1-R10
├── data-model.md              # the report dictionary's new blocks
├── quickstart.md              # offline proof, no money at any step
├── contracts/
│   ├── cli.md                 # wb report's changed output; wb summary
│   └── report.md              # every table, column and formula
├── checklists/requirements.md
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root: `monarch-benchmark/workflowbench/`)

```text
wb_report/
├── metrics.py              # NEW: every formula of contracts/report.md; calls wb_stats,
                            #      never reimplements it; returns plain dictionaries
├── html.py                 # NEW: _table(), the stylesheet, the sort script,
                            #      render_page() and render_summary_page()
├── report.py               # CHANGE: build_report gains the new blocks; render_html
                            #         delegates to html.py; render_md untouched;
                            #         write_report unchanged in signature
└── audiences.yaml          # unchanged
wb_orchestrator/
└── cli.py                  # CHANGE: wb report gains --no-sort; wb summary added
tests/
├── test_html_report.py     # NEW: every metric, every table, escaping, the gate
├── test_summary.py         # NEW: wb summary over seeded rounds; the aggregate
└── test_m4.py              # CHANGE: assert render_md is unchanged; the html file has tables
```

Docs touched (repo root): `monarch-benchmark/PLAN.md`, project `CLAUDE.md`
(both written by the coordinator, not this branch).

**Structure Decision**: two new modules, split by job. `metrics.py` computes and
is tested by asserting numbers; `html.py` renders and is tested by asserting
strings in the output. Keeping them apart is what lets the metric tests be
readable without parsing HTML. `report.py` stays the entry point so no caller
changes.

## Design notes that tasks depend on

1. **The renderer never sees the store.** `build_report` produces one
   dictionary; `html.py` renders it. The audience gate already filters
   competitors before any statistic is computed, so a renderer that cannot query
   cannot re-admit a gated competitor (research R7). No task may pass a `Store`
   into `wb_report/html.py`.
2. **Metrics call the statistics module.** Strict pass rate, pass rate over
   repetitions and every paired figure come from `arm_summary`, `pass_hat_k` and
   `paired_wl` unchanged. `metrics.py` adds only arithmetic over row fields.
   A test asserts the page and the markdown report agree on the shared metrics.
3. **`n/a` is a rendering decision, not a value.** `metrics.py` returns `None`
   for anything it cannot compute; `html.py` renders `None` as `n/a`. No
   formula returns 0 for "unknown", and no page contains `inf` or `nan`.
4. **Wall-clock is the sum over phases**, absent when no phase carries one
   (research R6). The mean and the median are over the rows that have one, and
   the source line states how many contributed.
5. **The Monarch columns are driven by the data**, not by the competitor's name:
   they appear when some competitor on the page has a phase key other than `run`.
   A run-only round therefore shows execution columns and `n/a` for authoring
   without any special case for the mode.
6. **The summary is the same metrics table repeated** plus one aggregate table
   that is a mean of per-round rates. No new statistic; no paired figure spans
   rounds (rule 5).
7. **The markdown report does not change.** A test compares its output against
   the current bytes for the seeded stores, so a metric correction that moves the
   markdown is a deliberate, visible change and not a side effect.

## Complexity Tracking

No constitution violations. Two new modules, no new dependency, no new
abstraction, no schema change. The alternative considered and rejected -
extending `Store.status()`'s SQL to produce the page's numbers - would need JSON
extraction in SQL for phases, unexpected changes and flags, would be a fourth
place computing a pass rate, and could not be tested without a database
(research R2).
