# Feature Specification: Results Report as HTML Tables, Per Round and Across Rounds

**Feature Branch**: `006-html-report`

**Created**: 2026-09-04

**Status**: Draft

**Input**: User description: "Feature 006: the official results report of a round as an HTML page with real tables, readable like a spreadsheet. Per round: metrics per competitor, comparison against the baseline, task matrix, failures, provenance. Across rounds: `wb summary` over several runs or plans, with an aggregate per competitor and the random-draw round beside the mean of the tiers. Every number from the results store, every table with its source line, audience rules unchanged, no new dependency, no charts."

**Design of record**: `docs/superpowers/specs/2026-09-04-html-report-design.md`
(approved 4 Sep 2026 by Carlos). This spec restates that design as requirements;
it does not reopen the decisions in its §2.

## Why

`wb report` writes an HTML file today, but that file is the markdown report
escaped into a `<body>` with `<br>` between lines. It contains no table. Both
files show four numbers per competitor and a list of paired comparisons.

The round sheet the team already reads
(`monarch-benchmark/docs/rounds/pilot-monarch-create-run.md`, "What the report
shows") promises considerably more: infrastructure failures counted separately
and excluded from the denominator, cache hit rate, cost, paired comparisons with
McNemar, and for Monarch the wall-clock and cost per phase, the cost per model
of its team, the questions asked and the reason when it declines to build a
workflow. All of that is already recorded on every attempt — `EpisodeRow` holds
phases, tokens, unexpected changes, flags, termination and error — and none of
it is rendered.

So reading a round means opening the markdown, then Langfuse, then querying the
results database by hand for anything per task. This feature makes the HTML file
the **official record of a round**: one page, real tables, read like a
spreadsheet, every number out of the results store and every table carrying its
source. Langfuse stays where the raw traces live.

Rounds are also about to come in families. Feature 005 splits the corpus into
tiers (simple, medium, complex) plus a random draw, and the question "does the
random draw land near the mean of the tiers?" is a check on the stratification
itself. That check needs one page over several rounds, which is the second half
of this feature.

## Vocabulary

Plain names, as in `CLAUDE.md` → *Plain names*.

| Plain name | Meaning here |
|---|---|
| competitor | one thing being measured: a model with a harness, the answer key, Monarch |
| task set | the frozen folder of prompts a round runs |
| attempt | one task, one competitor, one repetition |
| repetitions | how many times the same prompt is tried per competitor |
| approval rule | what must change and what must not, for a task to pass |
| answer key | the scripted competitor that always does the task right |
| round | one `wb run`: one product under test × one plan |
| infrastructure failure | an attempt the harness lost (rate limit, model unavailable, crash), not a task the competitor failed |
| agent error | the competitor itself failed or stopped abnormally |
| baseline | the competitor every other one is compared against, named by the plan |
| audience | who may read the page: `internal` or `public-rung2` |

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Read one round as a page (Priority: P1) 🎯 MVP

Carlos finishes a round and wants to know, in one place, how each competitor
did, how each compares to the baseline, which task each one failed, and what it
all cost — without opening a database.

**Why this priority**: it is the whole point of the feature and it stands alone.
The summary page is a second reader of the same tables.

**Independent test**: run `wb report` on the recorded run
`run-20260904-125645` (present in `out/wb.sqlite3`, 80 attempts, four
competitors) and open the HTML file. It contains four tables and a provenance
block. No money is spent.

**Acceptance scenarios**:

1. **Given** a completed round with four competitors, **When** `wb report <run>
   --audience internal` runs, **Then** the HTML file contains a metrics table
   with one row per competitor and every column of `contracts/report.md` §1.
2. **Given** the same round, **When** the page is opened, **Then** a comparison
   table shows every competitor other than the baseline with its difference in
   percentage points, its two ratios, its wins / losses / both / neither,
   McNemar p and a plain-words verdict.
3. **Given** a competitor with an infrastructure failure, **When** the metrics
   table is read, **Then** that attempt is counted in the infrastructure column
   and excluded from the strict-pass denominator, and the two facts are visible
   as separate columns.
4. **Given** the same round, **When** the task matrix is read, **Then** each
   cell shows passed over attempted for that task and competitor, and a cell
   with an infrastructure failure names it.
5. **Given** a failed attempt, **When** the failures table is read, **Then** its
   task, competitor, repetition, termination, error and unexpected change paths
   are all shown.
6. **Given** any table on the page, **When** it is read, **Then** a source line
   under it names the task set and version, the denominator, the competitors,
   the run id, and — when they apply — the price-table version and the share of
   attempts with a missing cost.
7. **Given** a competitor that passed nothing, **When** cost per passed attempt
   is rendered, **Then** the cell reads `n/a` and no division by zero occurs.

---

### User Story 2 — Read Monarch's phases on the same page (Priority: P1)

Monarch's row must carry what only Monarch has: how long authoring took versus
execution, what each cost, what its model team cost per model, how many
questions it asked, and how often it declined to build a workflow.

**Why this priority**: the create + run and run-only pilots are the next rounds,
and a page that cannot show the phase split cannot report them.

**Independent test**: a seeded store with one Monarch competitor whose rows
carry `phases.authoring` and `phases.execution`; the metrics table shows the
phase columns for that row and leaves them blank for the others.

**Acceptance scenarios**:

1. **Given** a round with a Monarch competitor, **When** the metrics table is
   rendered, **Then** the Monarch columns (authoring and execution wall-clock and
   cost, cost per model, questions asked, declined-to-build count) appear, and
   are empty for competitors that have no phases.
2. **Given** a round with no Monarch competitor, **When** the page is rendered,
   **Then** those columns are absent entirely rather than a block of empties.
3. **Given** a run-only round, whose rows have an execution phase and **no**
   authoring phase, **When** the metrics table is rendered, **Then** the
   authoring cells read `n/a`, never `0`.
4. **Given** attempts whose cost could not be read, **When** any cost figure is
   rendered, **Then** the source line states the share of attempts with a
   missing cost, as it does today.

---

### User Story 3 — Compare rounds on one page (Priority: P2)

Feature 005 produces four rounds — three tiers and a random draw. Carlos wants
one page showing them side by side, with a mean per competitor across the rounds
and the random draw next to the mean of the tiers.

**Why this priority**: it depends on the per-round tables existing, and the
rounds it compares do not exist yet.

**Independent test**: a seeded store with three runs of the same competitors on
different task sets; `wb summary --runs a,b,c --out page.html` produces one page
with three metrics tables and one aggregate table.

**Acceptance scenarios**:

1. **Given** three or four runs, **When** `wb summary --runs a,b,c --audience
   internal --out FILE.html` runs, **Then** the page carries each round's metrics
   table with its own source line, and an aggregate table with one row per
   competitor and the mean strict pass rate across the rounds.
2. **Given** four runs of which one is the random draw, **When** the page is
   rendered, **Then** a row or column places the random draw's rate beside the
   mean of the other three, so the two can be read against each other.
3. **Given** rounds run on different task sets, **When** the page is read,
   **Then** it states in words that paired comparisons are per round on identical
   sets and are never pooled, and no pooled paired figure appears anywhere.
4. **Given** `--plans p1,p2,p3`, **When** the command runs, **Then** it uses the
   most recent run of each named plan and names the run it picked for each.
5. **Given** a competitor present in some rounds and absent from others, **When**
   the aggregate is computed, **Then** its mean is over the rounds where it ran,
   and the page says over how many rounds.

---

### User Story 4 — The audience gate holds in every table (Priority: P1)

A public page must never show a competitor the allowlist excludes, in any of the
four tables or in the summary.

**Why this priority**: the gate is a fixed rule of the methodology (`PLAN.md`
§1 rule 9, "audience rules are code"), and four new tables are four new ways to
leak.

**Independent test**: build a public page from a store with a lab competitor and
assert its name appears nowhere in the file.

**Acceptance scenarios**:

1. **Given** a round with `monarch-lab` present, **When** the page is built for
   `public-rung2`, **Then** the build refuses or the competitor is absent from
   every table, and its name appears nowhere in the file.
2. **Given** the same round, **When** the page is built for `internal`, **Then**
   the lab competitor appears and the page carries the existing "DO NOT EXPORT"
   watermark.
3. **Given** the public audience, **When** the page is rendered, **Then** exact
   dollar figures are replaced by ratios exactly as the markdown report already
   does, in every table including the task matrix and failures.
4. **Given** a summary over several runs, **When** it is built for a public
   audience, **Then** the same filter applies to every round on the page.

---

### User Story 5 — Read the wording of the round's size (Priority: P3)

Anyone opening the page must see the shape of the round, not only its total.

**Independent test**: the page's header contains "attempts per prompt and
competitor", "prompts" and the "N = P × R" form.

**Acceptance scenarios**:

1. **Given** any page, **When** its header is read, **Then** it states attempts
   per prompt and competitor, the number of prompts, and attempts per competitor
   written as the product, not the total alone.

---

### Edge cases

- A run with a single competitor: no comparison table (nothing to compare), and
  the page says so rather than rendering an empty table.
- A run with zero failed attempts: the failures table is replaced by one line
  saying no attempt failed.
- A competitor whose attempts are all infrastructure failures: strict pass rate
  is `n/a`, never `0` — the existing store behaviour, made visible.
- Tasks with no `info.tier` or `info.domain` (every pilot task today): those
  columns are absent from the task matrix, not empty.
- Rows written before phases were recorded: wall-clock and phase cells read
  `n/a`.
- A very long error string in the failures table: truncated in the cell with the
  full text available, and never allowed to break the table layout.
- A summary asked for a run id that does not exist: refuses naming it, before
  writing any file.
- Two runs on the same page with different price-table versions: each round's
  source line carries its own; the aggregate table names both.

## Requirements *(mandatory)*

### Functional Requirements

**The per-round page**

- **FR-001**: The HTML file written by `wb report` MUST contain the four tables
  of `contracts/report.md` — metrics, comparison, task matrix, failures — plus a
  source and provenance block.
- **FR-002**: Every figure on the page MUST be computed from the results store,
  through the same functions the markdown report uses where the metric already
  exists. No figure may be typed or recomputed a second way.
- **FR-003**: Every table MUST carry a source line naming the task set and its
  version, the denominator, the competitors, the run id, and — where they apply
  — the price-table version and the share of attempts with a missing cost.
- **FR-004**: The metrics table MUST have one row per competitor and the columns
  and formulas of `contracts/report.md` §1.
- **FR-005**: Infrastructure failures MUST be shown as their own count and rate
  and MUST be excluded from the strict-pass denominator; agent errors and
  timeouts MUST be shown as separate columns from infrastructure failures.
- **FR-006**: The comparison table MUST have one row per non-baseline
  competitor with the columns and formulas of `contracts/report.md` §2,
  including a plain-words verdict that reads "no significant difference at this
  size" whenever McNemar p ≥ 0.05.
- **FR-007**: The task matrix MUST have one row per task and one column per
  competitor, each cell showing passed over attempted for that pair, naming the
  infrastructure failures it contains.
- **FR-008**: Each task-matrix cell MUST carry its failure reason category, and
  the same information MUST appear in a details table below it so that nothing
  is available only on hover.
- **FR-009**: The task matrix MUST show a domain and a tier column when the
  tasks' `info` carries them, and MUST omit those columns entirely otherwise.
- **FR-010**: The failures table MUST list every failed attempt with its task,
  competitor, repetition, termination, error and unexpected change paths.
- **FR-011**: The provenance block MUST show the configuration hash, the plan
  and product identifiers, the price tables with their versions, the task set's
  hash list, the run's start and finish, and the audience.
- **FR-012**: A page MUST state the round's size as attempts per prompt and
  competitor, number of prompts, and attempts per competitor written as the
  product.
- **FR-013**: The markdown report MUST keep working unchanged; the page is an
  addition, and both MUST show the same value for any metric they share.

**Monarch's columns**

- **FR-014**: When a competitor's rows carry phases, the metrics table MUST show
  wall-clock and cost for the authoring and execution phases.
- **FR-015**: It MUST show cost per model of the competitor's model team when
  the rows carry it, questions asked, and the count of attempts where the
  competitor declined to build a workflow.
- **FR-016**: An absent phase MUST render as `n/a`, never as zero, and the
  Monarch-only columns MUST be absent from a page with no such competitor.

**Across rounds**

- **FR-017**: `wb summary --runs a,b,c[,d] --audience X --out FILE.html` MUST
  write one page carrying each named round's metrics table and an aggregate
  table.
- **FR-018**: `wb summary --plans p1,p2,...` MUST select the most recent run of
  each named plan and MUST name the run it selected for each.
- **FR-019**: The aggregate table MUST show, per competitor, the mean strict
  pass rate across the rounds and the number of rounds it is a mean over, and —
  when the rounds carry tiers — a mean per tier.
- **FR-020**: The page MUST place the random-draw round's rate beside the mean
  of the tier rounds so the two can be read against each other.
- **FR-021**: The page MUST NOT show any paired comparison pooled across
  different task sets, and MUST state in words that paired figures are per round
  on identical sets.
- **FR-022**: `wb summary` MUST refuse, before writing anything, when a named
  run or plan does not exist, naming it.

**The audience gate**

- **FR-023**: The audience allowlist MUST be applied before any statistic is
  computed, exactly as today; a competitor it excludes MUST NOT appear in any
  table, in any hover text, in the provenance block or in the page's title.
- **FR-024**: A page for a non-internal audience MUST replace exact dollar
  figures with the ratios the markdown report already uses, in every table.
- **FR-025**: `wb summary` MUST apply the gate to each round on the page and
  MUST refuse for the same reasons `wb report` refuses today.

**Constraints**

- **FR-026**: The page MUST be built with the standard library only — no new
  dependency, no external stylesheet, no external script, no chart.
- **FR-027**: A cell whose value cannot be computed MUST read `n/a`; no division
  by zero, no infinite ratio, no silent zero.
- **FR-028**: The page MUST be one self-contained file that opens from disk with
  no network access.

### Key Entities

- **Page**: one HTML file per round per audience, or one per summary.
- **Table**: a set of rows, a header, and one source line.
- **Metric**: a named value with a formula over the attempt rows, defined once
  in `contracts/report.md` and computed in one place.
- **Round**: one run in the results store, with its configuration and attempts.
- **Aggregate**: a mean over rounds, per competitor, never a pooled recount.

## Success Criteria *(mandatory)*

- **SC-001**: `wb report run-20260904-125645 --audience internal` writes a page
  containing the four tables, offline, with no key in the environment and no
  money spent.
- **SC-002**: Every metric on that page matches the value computed directly from
  the store in a test, to the last digit shown.
- **SC-003**: A page built for `public-rung2` from a store containing a lab
  competitor does not contain that competitor's name anywhere in the file.
- **SC-004**: A competitor with an infrastructure failure shows a strict pass
  rate whose denominator excludes it, and an infrastructure column that counts
  it, in the same row.
- **SC-005**: A competitor that passed nothing shows `n/a` for cost per passed
  attempt, and the page contains no `inf` and no `nan`.
- **SC-006**: `wb summary --runs a,b,c` over three seeded runs writes one page
  with three metrics tables, one aggregate table, and the sentence stating that
  paired figures are never pooled.
- **SC-007**: The page's header states the round's size as a product, and the
  string "attempts per prompt and competitor" appears on it.
- **SC-008**: The markdown report of the same run is byte-identical to what the
  current code produces, except where a shared metric was corrected.
- **SC-009**: `uv run python -m pytest tests -q` is green and the suite needs no
  package that is not already in `pyproject.toml`.

## Out of Scope

- Charts, graphs and any visual design beyond legibility.
- The Slack post rendered from the report — work front D (`PLAN.md` WS-D).
- Defining the tiers and the random draw — feature 005. This feature reads
  `info.tier` and `info.domain` if present and degrades gracefully if not.
- Per-attempt Langfuse links, unless a trace id already sits in `turn_log`, in
  which case an optional column is allowed and nothing more.
- Changing what is recorded per attempt; `EpisodeRow` is unchanged.
- Any new statistic. The page renders what `wb_stats` already computes, plus
  arithmetic over row fields defined in `contracts/report.md`.

## Assumptions

- The results store holds everything the page needs. Verified against
  `runner/schema.py` and against `run-20260904-125645` in `out/wb.sqlite3`.
- The pilot tasks carry no `info.tier` and no `info.domain` today; the page must
  work without them.
- Wall-clock per attempt is the sum over that attempt's phases; rows without
  phases have none.
- Feature 005 will add the tiers; this feature does not wait for it.

## Dependencies

- Features 001, 002 and 004 as they stand: the configuration files, the phase
  fields on the row, and the run-only source line.
- Nothing outside the repository. Every test is offline.

## Open Questions

1. **Sortable columns**: worth the inline JavaScript, or not? Decided in
   `research.md` R5; recorded here so the answer is visible. Owner: Carlos.
2. **Median wall-clock for rows with no phases**: shown as `n/a`, or excluded
   from the median of the rows that have one? Proposed: excluded, with the count
   of rows that contributed on the source line. Owner: Carlos.
3. **Where the summary page is filed** by default when `--out` is omitted —
   proposed `out/summary-<date>-<audience>.html`. Owner: Carlos.
