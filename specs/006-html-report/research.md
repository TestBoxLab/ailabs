# Research: results report as HTML tables

Phase 0 of `/speckit-plan`. Every finding below was checked against the code in
`monarch-benchmark/workflowbench/` and against the recorded run
`run-20260904-125645` in `out/wb.sqlite3` (80 attempts, four competitors).
Design decisions from the brainstorm (design section 2) are taken as given and
not re-argued.

## R1. Everything the four tables need is already stored

**Finding**: `Store.episodes()` returns whole `EpisodeRow` dictionaries out of
`episodes.row_json`. Read against the recorded run, a row carries `passed`,
`assertions_passed`, `invariant_passed`, `unexpected_changes`, `n_changes`,
`termination`, `error`, `retries`, `flags`, `cost_usd`, `tokens`
(`prompt`, `cached`, `cache_write`, `output`), `tool_calls` and `phases`
(each with `turns`, `tool_calls`, `tokens_input`, `tokens_output`, `cost_usd`,
`wall_clock_s`).

**Decision**: no schema change, no migration, no new recorded field. The feature
is rendering only.

**Rationale**: the cheapest correct version of this feature is the one that adds
no write path. Anything the page cannot show today is a gap in what the runner
records, and that is a different feature.

`# ponytail: rendering only. No column is added to the results store for this.`

## R2. Where the metrics live

**Finding**: three places compute overlapping numbers today.
`wb_stats.arm_summary` computes strict pass, cost, cache hit and infrastructure
rate for the report. `Store.status()` computes a nearly identical set in SQL for
`wb status`. `build_report` sums cost a third time for the cost ratio.

**Decision**: one new module, `wb_report/metrics.py`, holds every formula of
`contracts/report.md` and is the only place the page reads. It **calls**
`arm_summary`, `pass_hat_k` and `paired_wl` rather than reimplementing them, so
a metric the markdown report shows keeps that report's value.

**Rationale**: the page adds about twenty metrics. Putting them in `report.py`
beside the renderers would make one 600-line module doing three jobs; putting
them in `wb_stats` would mix "statistics" with "arithmetic over row fields".
A third computation of strict pass rate is how two reports come to disagree.

**Alternatives considered**: extending `Store.status()`'s SQL - rejected: half
the fields the page needs live inside `row_json` (phases, unexpected changes,
flags), so the SQL would have to grow JSON extraction for each; the Python is
shorter and testable without a database.

## R3. HTML with the standard library

**Decision**: `html.escape` plus f-strings and one `_table(headers, rows,
source_line)` helper, about 30 lines. One inline `<style>` block.

**Rationale**: a table is `<tr><td>`. A templating engine would be a dependency
for string concatenation, and the constitution's Additional Constraints make
stdlib-first the default. `html.escape` on every cell value is the whole safety
requirement, since error strings and change paths come from model output.

`# ponytail: one _table() helper, not a template engine. Ceiling: if the page
ever needs conditional layout beyond a table, revisit.`

**Alternatives considered**: `string.Template` (no advantage over f-strings
here), Jinja2 (a dependency), writing the tables in markdown and converting
(needs a markdown library, and the markdown report exists already).

## R4. Escaping and untrusted content

**Finding**: the failures table and the task matrix render `error` and
`unexpected_changes[*].path`, both of which originate from model output or from
the simulated apps. Today's `render_html` escapes the whole markdown blob once,
which is safe by accident.

**Decision**: every cell value passes through `html.escape(..., quote=True)`,
including the `title` attributes. One test renders a store whose error string is
`<script>alert(1)</script>` and asserts the tag does not appear unescaped in the
file.

**Rationale**: input validation at a trust boundary is not something laziness
skips. The page will be opened in a browser and may be shared.

## R5. Sortable columns: yes, with a flag to turn them off

**Decision**: about 12 lines of inline JavaScript that sorts a table by the
clicked column, numeric when every cell parses as a number and lexicographic
otherwise. `wb report --no-sort` omits it.

**Rationale**: the metrics table has more than twenty columns and the task
matrix has one row per task; "which task did everyone fail" is the first
question anyone asks, and sorting answers it without a database. Twelve lines of
stdlib-free JavaScript is cheaper than the tooling anyone would otherwise reach
for. The flag exists because a page that must be pure markup (pasted into
another document, archived) should be able to be.

`# ponytail: a click handler over table.rows, not a sorting library. Ceiling:
it sorts one table by one column and forgets; that is the whole requirement.`

**Alternatives considered**: no sorting at all (the design left it optional) -
rejected because the cost is a dozen lines and the benefit is the matrix's main
use; a sorting library from a CDN - rejected, the page must open from disk with
no network (FR-028).

## R6. Wall-clock per attempt

**Finding**: `EpisodeRow` has no total duration. It has `started_at` and
`finished_at`, and `phases[*].wall_clock_s`. On the recorded run every row has
one phase, `run`, with `wall_clock_s` set.

**Decision**: an attempt's wall-clock is the **sum over its phases**, and is
absent when no phase carries one. `finished_at - started_at` is not used.

**Rationale**: the phase sum is what the round sheet promises to report per
phase, so the total must be consistent with it. The timestamp difference would
include queueing and snapshotting, which is a different quantity and would not
add up to the phase columns beside it.

**Consequence**: rows written before phases were populated show `n/a`, and the
source line says how many attempts contributed to the mean and the median.

## R7. The audience gate does not move

**Finding**: `build_report` filters competitors out of `arms` before any
statistic is computed, raises `GateError` when nothing is left, refuses
`monarch-lab*` outside `internal`, and swaps dollars for ratios when the
audience is not internal. `render_md` never names gated competitors for a public
audience - it prints a count.

**Decision**: the page renders from **the same `report` dictionary**
`build_report` already produces, extended with the new tables. It never queries
the store itself.

**Rationale**: rule 9 says the audience rules are code. Four new tables are four
new chances to re-query the store and re-admit a competitor the gate removed.
Making the renderer unable to reach the store removes the possibility rather
than testing for it.

`# ponytail: the renderer takes a dictionary, not a Store. Not layering - it is
the gate that makes it necessary.`

## R8. Tiers and domains do not exist yet

**Finding**: the 10 pilot tasks carry `info.zapier_tools` and
`info.initial_state`; there is no `info.tier` and no `info.domain` on any task
in `tasks/`.

**Decision**: the task matrix reads `info.domain` and `info.tier` when present
and omits the columns entirely when no task carries them. The summary's per-tier
aggregate is omitted the same way. Feature 005 will supply them; this feature
does not wait and does not define them.

**Rationale**: an empty column is worse than no column, and inventing a tier
here would collide with feature 005's definition.

## R9. `wb summary` reads finished runs only

**Decision**: the command reads the store like `wb report` does, per round, and
refuses a run that does not exist. It does not refuse an unfinished run, but
notes `stop_reason` on that round's source line where one is set.

**Rationale**: a round stopped by the cost ceiling is still a real, partial
result, and hiding it would be worse than labelling it. A run id that is simply
absent is a typo and must fail loudly before a file is written.

## R10. Both pages come out of one renderer

**Decision**: `wb_report/html.py` holds the table helpers and both page
builders. `wb_summary` is not a separate package: the summary page is the
metrics table repeated plus one aggregate table.

**Rationale**: the aggregate is a mean of numbers the per-round path already
computes. A second module would duplicate the table helper and the source-line
formatting to save nothing.

## Unknowns carried as open questions (none blocking)

1. Whether the median should exclude rows with no wall-clock (proposed: yes,
   with the contributing count stated). Owner: Carlos.
2. The default filing location of the summary page (proposed
   `out/summary-<date>-<audience>.html`). Owner: Carlos.
3. Whether per-attempt Langfuse trace links are worth an optional column - only
   if a trace id already sits in `turn_log`; not investigated further because the
   design put it out of scope.
