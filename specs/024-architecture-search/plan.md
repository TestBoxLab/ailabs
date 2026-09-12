# Implementation Plan: The search loop — measurement foundations for architecture search

**Branch**: `genesis-loop` (feature 024) | **Date**: 2026-09-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/024-architecture-search/spec.md`; design of
record [`docs/superpowers/specs/2026-09-11-architecture-search-design.md`](../../docs/superpowers/specs/2026-09-11-architecture-search-design.md);
Phase 0 findings in [research.md](./research.md).

## Summary

The lab runs architecture search over Monarch's design space, scored by the benchmark.
This feature makes the scorer trustworthy and the searcher safe before the search is
allowed to run, then closes the loop that turns a confirmed win into a written proposal.

The dominant technical finding from Phase 0 is that **most of this already exists and is
either not wired or internally inconsistent**: per-phase cost (R2), the strict cohort key
and exclusion reasons (R5), the approval module (R9), run-only execution (R10), the
structural difficulty measure (R4), and the whole experiment record with its sizing and
settling machinery (R13). The work is overwhelmingly repair and wiring, not construction.

Three findings shape the sequencing more than the rest:

- **R11** — `genesis_hypotheses.smallest_plan` sizes experiments with a two-proportion
  normal approximation floored at ten tasks, while `settle` and the round report decide
  with a paired sign test. Ten tasks typically yield three or four discordant pairs, and
  below six no win count reaches p < 0.05. The lab's sizing function recommends
  experiments its own settling function can never conclude.
- **R13** — the spec's "experiment record" is the existing hypothesis record. It needs
  four fields, not a replacement.
- **R12** — the standing research envelope must not be built before the envelope
  accounting is correct.

Only two things are genuinely new: a secret path segment on the front-door proxy (R1),
and one recorded timestamp for the authoring boundary (R3).

## Technical Context

**Language/Version**: Python 3.13, managed by `uv`. Always `uv run`, never bare Python.

**Primary Dependencies**: None new. Existing in-repo packages only — `wb_orchestrator`,
`wb_arms`, `wb_report`, `wb_world`, `wb_studio`. Stdlib-first per the constitution.

**Storage**: Existing. Run records as JSON under `out/studio/<job>/`; the weekly ledger
in `research/budget.sqlite3`; frozen task sets as files under `workflowbench/tasks/` with
a YAML manifest; Genesis state under `out/studio/genesis/`.

**Testing**: `pytest`. `cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.
Baseline is 1091 passing, ~11 minutes; on Windows run the full suite detached and wait for
its exit. Per-file runs during development — `tests/conftest.py`'s `fake_monarch.stop()`
deadlocks a whole-suite run. The frontend has one suite, `node tests/browser/suite.cjs`,
which currently resolves Playwright from a hard-coded path on one machine.

**Target Platform**: The Studio process on Railway (unattended runner), and developer
machines on Windows. The browser reads and queues; it does not run rounds.

**Project Type**: Python package set with a stdlib HTTP server and a hand-written
vanilla-JS frontend. No build step, no framework, no bundler. Not introduced here.

**Performance Goals**: None new. The one relevant constraint is that a refusal must
happen **before** any reservation, so every gate added here is a pure function evaluated
ahead of dispatch.

**Constraints**:
- The simulated world is immutable: no change to `vendor/automation-bench` routes, seeds,
  requests, initial data or assertions.
- Old rows are never regraded against replacement task definitions — they are marked.
- No new runtime dependency without a reason recorded here. There are none.
- The front-door repair must not require any change on Monarch's side (R1).

**Scale/Scope**: 800 corpus tasks across 7 domains; slates of ~50; 3 repetitions per
variant test; 150 attempts per experiment; 7–20 experiments per weekly envelope. Two
human users. ~35 functional requirements across 5 prioritised stories.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1.*

| Principle | Status | Evidence |
|---|---|---|
| **I. Brainstorm → spec → plan → tasks → execute** | PASS | Brainstormed 11 Sep across four question rounds; design of record written; `/speckit-specify` produced spec.md and the requirements checklist; this is `/speckit-plan`. `/speckit-tasks` follows. No code written in planning. |
| **II. Test-First (NON-NEGOTIABLE)** | PASS | Every task in Phase 2 is red→green. Each defect in stories 1 and 2 has a reproducing test written first against the stored evidence; gates are tested by attempting the reach and asserting refusal. |
| **III. The methodology is fixed** | PASS | `PLAN.md` §1 untouched. This feature changes inputs — a new task split, a repetitions field, a cost boundary, a confirmation gate — and reopens no rule. Explicitly out of scope in the spec. |
| **IV. Money and pre-registration gates** | PASS, and strengthened | FR-001..FR-009 repair gates that are currently weaker than the constitution states. FR-007 wires the existing `approvals.py` so "an agent never approves its own round" becomes code rather than prose. FR-017 pre-registers both slates by hash. FR-035's standing envelope is explicitly sequenced behind FR-005 (R12). |
| **V. Plain language, graph-grounded** | PASS | All artifacts in English, using the plain names (competitor, task set, repetitions, attempt, approval rule, product under test). Graphify refresh is a task after code changes. |
| **Stack: Python 3.13 + uv, stdlib-first** | PASS | No new dependencies. |
| **Upstream world immutable** | PASS | No task, seed, route or assertion is edited. Moved definitions are marked, never regraded (FR-012). |
| **Laziness within discipline** | PASS | Phase 0 established that 7 of the 9 capability requirements are wiring or repair of existing modules. Where a module exists and is unused, the plan wires it and deletes the weaker duplicate rather than adding a third. |

**No violations. Complexity Tracking omitted.**

### Post-Phase-1 re-evaluation

Re-checked after data-model.md, contracts/ and quickstart.md were written. One violation
was found and corrected during the re-check rather than carried forward:

- The first draft proposed a new experiment record alongside
  `wb_studio/genesis_hypotheses.py`, which already validates, sizes and settles exactly
  that record (R13). That would have been a third parallel implementation in a codebase
  whose two worst reporting defects — two failure classifiers, two interval estimators —
  are both duplicated implementations of one rule. Corrected: the record is extended with
  four fields, and `wb experiment` is a CLI surface over it, not a second store.

Two notes carried into tasks:

- `approvals.py:77` currently imports `wb_studio.enterprise`, so the benchmark depends on
  the UI package. FR-007's wiring must invert that edge, not deepen it.
- Phase 1 added no dependency, no new package and one new data artifact (the slate
  manifest), which sits beside the existing `tasks/tiers-manifest.yaml` and follows its
  shape.

## Project Structure

### Documentation (this feature)

```text
specs/024-architecture-search/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 — 12 findings, all from code
├── data-model.md        # Phase 1 — entities and their records
├── quickstart.md        # Phase 1 — how to verify each story
├── contracts/
│   ├── cli.md           # New and changed `wb` commands
│   ├── config-files.md  # Slate manifest, research envelope
│   └── measures.md      # Result-row fields, curve, gap item
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
└── tasks.md             # Phase 2 — /speckit-tasks, NOT created here
```

### Source Code (repository root)

Files this feature touches, grouped by the story that drives them. Every one already
exists; this feature adds no new package.

```text
monarch-benchmark/workflowbench/
├── wb_studio/
│   ├── app.py                  # P1: front-door gate before auth; operator + repetitions
│   │                           #     on launch; attempt cap; wire approvals
│   ├── genesis_autonomy.py     # P1: default off; pause honoured
│   ├── genesis.py              # P1: pause in chat; attribution for the envelope
│   ├── genesis_watcher.py      # P1: daily allowance counts launched runs
│   ├── genesis_access.py       # P1: envelope accounting (FR-005) — blocks FR-035
│   ├── usage.py                # P1: holds counted at reserved maximum while unsettled
│   ├── genesis_ingest.py       # P1: refuse private/loopback/link-local; bound redirects
│   ├── reports.py              # P2: name the service actually called
│   ├── measures.py             # P2: false-completion source; P4: cost by phase, per pass
│   ├── report_data.py          # P2: liveness mark, competitor labels, one cohort key
│   ├── failure_analysis.py     # P2: derived from narrative modes, or removed
│   ├── narrative.py            # P2: the single failure classification
│   ├── leaderboard.py          # P2: cohort key and exclusion_reason promoted
│   ├── difficulty.py           # P2: inlined Wilson deleted in favour of measures
│   └── static/reports.js       # P2: data-derived titles; P5: the curve
│   ├── genesis_hypotheses.py   # P3: sizing matched to the settling test; slate,
│   │                           #     repetitions, lineage, power on the existing record
├── wb_orchestrator/
│   ├── approvals.py            # P1: wired from the Studio; UI import inverted
│   ├── budget.py               # P1: overrun scoped to its week and clearable
│   ├── corpus.py, slate.py     # P3: stratified split + manifest
│   ├── monarch_recipes.py      # P4: unchanged; run to produce recipe data
│   └── cli.py                  # P3/P4: `wb corpus split`, envelope and experiment
│                               #     commands as a surface over genesis_hypotheses
├── wb_arms/
│   ├── monarch.py              # P4: authoring-end timestamp; by_phase onto the row
│   └── langfuse_cost.py        # P4: unchanged — by_phase already correct
└── tests/                      # every change above, test-first
```

**Structure Decision**: No new packages, no new top-level directories. The feature is a
repair-and-wire pass across the existing `wb_studio`, `wb_orchestrator` and `wb_arms`
packages, plus one new frozen-data artifact (the slate manifest) alongside the existing
`tasks/tiers-manifest.yaml`. This follows directly from Phase 0: adding modules here
would create third implementations of rules that already have two.

## Phase 2 sequencing

Ordered by the spec's story priorities. Within each, ordered by dependency.

### P1 — The gates hold

Two of these are live on a public URL, so they lead.

| Step | Work | Requirement | Note |
|---|---|---|---|
| 1.1 | Secret per-run path segment on `/front-door`; proxy refuses without it; auth check precedes the proxy for every method | FR-001 | R1. Seed URL carries it — no Monarch-side change |
| 1.2 | Autonomy defaults to off; watcher and scheduler do not start until enabled | FR-002 | R-none; `genesis_autonomy.py:25` |
| 1.3 | Pause read in `genesis.chat`, the single paid funnel; skipped jobs recorded | FR-003 | |
| 1.4 | Daily allowance counts reserved maxima of launched runs | FR-004 | |
| 1.5 | **Envelope accounting corrected and verified** | **FR-005** | **R12 — blocks 3.6** |
| 1.6 | Overrun scoped to its week; recorded human clear path | FR-006 | `budget.py:269` |
| 1.7 | Operator on every launch; `approvals.py` wired; UI import edge inverted | FR-007 | R9 |
| 1.8 | Per-attempt cap passed through from the Studio | FR-008 | `app.py:617` |
| 1.9 | Fetch refuses private, loopback, link-local; bounded redirects | FR-009 | |

### P2 — Numbers a scientist can act on

Each starts with a test that reproduces the defect against the lab's stored ten-task run.

| Step | Work | Requirement |
|---|---|---|
| 2.1 | Service named from the host actually called | FR-010 |
| 2.2 | False-completion restricted to competitor output; labelled as inferred everywhere shown | FR-011 |
| 2.3 | Stored task hash compared to the live corpus; non-comparable attempts marked and excluded from headline numbers | FR-012 |
| 2.4 | One failure classification (`narrative.MODES`); the second view derived or removed | FR-013 |
| 2.5 | Competitor labels carry model and version | FR-014 |
| 2.6 | Figure titles derived from their data | FR-015 |
| 2.7 | `leaderboard`'s cohort key used by `report_data`; the weaker key deleted; provisional mark surfaced | FR-016 |
| 2.8 | One interval estimator — Wilson over attempts — for both rank and display; `difficulty.py`'s inlined copy deleted | FR-016, R6 |

### P3 — An experiment that can return a verdict

| Step | Work | Requirement | Note |
|---|---|---|---|
| 3.1 | Stratified split by tier and domain; frozen; manifest with measure, version, cuts, per-slate domain counts, seed, per-task tier/domain/hash | FR-017, FR-033 | R4 |
| 3.2 | Redraw of a frozen held-out slate refused | FR-018 | |
| 3.3 | Repetitions as an explicit field on a run, through the Studio launch path | FR-019 | |
| 3.4 | Development slate the default for a variant test | FR-020 | |
| 3.5 | `smallest_plan` sized for the paired sign test that settles it; refusal before any reservation, naming the sufficient count | FR-021 | R11 — the sizing formula and the settling test currently disagree |
| 3.6 | Weekly research envelope with per-experiment ceiling; exhaustion stops the loop | FR-035 | **after 1.5** |
| 3.7 | Lineage on the hypothesis record; held-out reachable once per lineage | FR-022 | R13 |
| 3.8 | Slate, repetitions, prediction and power added to the existing hypothesis record; CLI surface over it | FR-023 | R13 — extend, do not duplicate |

### P4 — The fitness function

| Step | Work | Requirement | Note |
|---|---|---|---|
| 4.1 | `by_phase` carried onto the result row; configure and execute costs reconcile to the total | FR-024 | R2 — wiring only |
| 4.2 | Authoring-end timestamp recorded; two durations derived | FR-025 | R3 — the one new value |
| 4.3 | Unknown on either side stays unknown, never zero; reservation held | FR-026 | existing `cost_missing` discipline |
| 4.4 | Recipes generated; repeated execution produces per-execution cost and time | FR-027 | R10 — run the built command |
| 4.5 | Cost compared per successful task | FR-028 | |

### P5 — The curve and the gap list

| Step | Work | Requirement |
|---|---|---|
| 5.1 | Cumulative cost against executions per competitor; crossing point named or absence stated | FR-029 |
| 5.2 | Round opens with curve, accuracy with uncertainty and n, gap list | FR-030 |
| 5.3 | One gap evidence base, three renderings, no contradiction | FR-031 |
| 5.4 | Each gap item states its evidence kind; unconfirmed marked | FR-032 |
| 5.5 | Proposal artifact from a held-out confirmation | FR-034 |

### Closing work

- Refresh the Graphify graph (constitution V).
- Correct `STATE-OF-THE-PROGRAM.md` §3, which lists feature 004 as "specified, not built"
  when `monarch_recipes.py` is complete (R10).
- Update `CLAUDE.md`'s file map for the slate manifest and the envelope.

## Risks

| Risk | Mitigation |
|---|---|
| The front-door repair breaks a live Monarch round | The secret rides in the seed URL, which is already per-round configurable. Verify with `wb monarch verify` before any paid round. |
| Marking non-comparable attempts empties the only report the lab has | That is the correct outcome and the reason the gauntlet matters. The mark is the deliverable, not the number that survives it. |
| The power refusal blocks every experiment the lab can afford | Possible and worth knowing early. Step 3.5 lands before the envelope (3.6) so the constraint is visible before unattended spending is enabled. If a correctly-sized experiment proves unaffordable, that is a finding about the programme, not a reason to loosen the test. |
| Correcting `smallest_plan` invalidates the seven hypotheses already queued | They have never been tested (`TRACK.md`: 7 proposed, 0 tested), so nothing is lost. Re-size them under the corrected rule and record which were under-powered as originally written. |
| Only Monarch reports phases, so the curve compares unlike things | Non-Monarch competitors report authoring cost as *not applicable*, distinct from unknown. That asymmetry is the finding, not a defect. |
| The browser suite runs on one machine and not in CI | Out of scope here, but it means P2 and P5 frontend changes have no automated guard. Record it; do not silently rely on it. |

## Complexity Tracking

Not required — Constitution Check passed with no violations.
