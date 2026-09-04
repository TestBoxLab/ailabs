# Design record: results report as HTML tables, per round and across rounds

**Date**: 4 September 2026 · **Decided with**: Carlos · **Status**: approved,
feeds feature 006 (`specs/006-html-report/`).

This is the design of record for feature 006. Its §2 decisions are settled; the
spec restates them as requirements and does not reopen them.

## 1. The problem

`wb report <run_id> --audience X` writes two files today: a markdown report and
an HTML file that is **the same markdown, HTML-escaped, wrapped in a `<body>`
with `<br>` between lines**. There is no table element in it. Both files carry
four numbers per competitor — strict pass rate, pass rate over repetitions,
infrastructure-failure rate, cache hit rate — plus cost when the audience is
internal, and a list of paired comparisons.

That is less than the team already expects to read. The round sheet
`monarch-benchmark/docs/rounds/pilot-monarch-create-run.md` promises, under
"What the report shows": pass rate with error bars, infrastructure failures
excluded from the denominator, cache hit rate, cost, paired comparisons with
McNemar, and for Monarch the wall-clock and cost per phase, cost per model of
its team, questions asked, and the reason when it declines to build a workflow.
None of that reaches the page. Everything needed is already in the results
store — `EpisodeRow` carries phases, tokens, unexpected changes, flags,
termination and error on every attempt — it is simply never rendered.

Reading a round today means opening the markdown, then opening Langfuse for the
traces, then querying SQLite by hand for anything per task. Carlos asked for one
page he can read like a spreadsheet.

## 2. The decisions

### 2.1 Scope and shape

- **The HTML page becomes the official record of a round.** Langfuse stays where
  the raw traces live; the page is what the team reads and what a summary links
  to. The markdown report stays as it is — it is what a diff and a commit show.
- **Real tables, no visual design work now.** Plain `<table>` elements, a small
  inline stylesheet (borders, padding, right-aligned numbers, zebra rows,
  sticky header), no framework, no chart, no logo. Sortable columns only if a
  handful of lines of inline JavaScript do it; otherwise not at all.
- **Every number comes from the results store.** No hand-typed figure, no
  number recomputed differently from the markdown report. Where the markdown and
  the page show the same metric they must show the same value from the same
  function.
- **Every table carries its source line**: task set and version, denominator,
  competitor, run id, price-table version, and the share of attempts with a
  missing cost — the suffix `_source_suffix()` already builds.

### 2.2 The per-round page: four tables plus provenance

`wb report <run_id> --audience X` already writes `report-<run>-<audience>.html`.
That file becomes this page.

1. **Metrics**, one row per competitor: attempts, passed, strict pass rate with
   its error bar, pass rate over repetitions, infrastructure failures as a count
   and a rate (excluded from the pass denominator), agent errors, timeouts, cost
   total, cost per attempt, cost per passed attempt, tokens prompt / cached /
   cache-write / output, cache hit rate, mean and median wall-clock per attempt,
   turns and tool calls. For Monarch, extra columns: authoring and execution
   wall-clock and cost, cost per model of its team, questions asked, and the
   count of attempts where it declined to build a workflow.
2. **Comparison against the baseline**, one row per other competitor:
   difference in strict pass rate in percentage points, ratio of pass rates,
   ratio of cost per passed attempt (competitor ÷ baseline), paired wins /
   losses / both / neither, McNemar p, and a plain-words verdict column — "no
   significant difference at this size" whenever p ≥ 0.05.
3. **Task matrix**: rows are tasks (with domain and tier when the task's `info`
   carries them), columns are competitors, cells are passed / attempted per
   repetition — `2/2`, `1/2`, `0/2 (infra 1)`. Each cell carries the failure
   reason category (unexpected change path, assertion failed, error string) as a
   tooltip, and a details table below repeats it in text so nothing is
   hover-only.
4. **Failures**: every failed attempt, one row — task, competitor, repetition,
   termination, error, unexpected change paths.
5. **Source and provenance block**: configuration hash, plan and product paths,
   price tables with their versions, the task set's hash list, run dates,
   audience.

**Audience rules do not change.** The public audience never shows a competitor
the allowlist excludes, in any table — the filter stays where it is, at query
level, before any statistic is computed. A new table must not become a new way
around the gate.

### 2.3 Across rounds

```
wb summary --runs a,b,c[,d] --audience X --out FILE.html
wb summary --plans tier-simple,tier-medium,tier-complex,random-10 --audience X --out FILE.html
```

`--plans` picks the latest run of each named plan. One page, containing:

- the per-round metrics tables, side by side;
- an aggregate table per competitor: mean strict pass rate across the rounds,
  and per tier when the rounds are tiers;
- the random-draw round beside the mean of the three tiers — the self-check
  Carlos asked for: if the tiers are a fair stratification, a random draw should
  land near their mean.

Feature 005 defines the tiers. Feature 006 only reads `info.tier` and
`info.domain` when a task carries them and leaves those columns out otherwise.

**Paired comparisons never pool across different task sets.** They are computed
per round, on that round's identical set, and the page says so in words. The
aggregate table is a mean of per-round rates, not a pooled recomputation.

### 2.4 Wording

Attempts are always described in full: "attempts per prompt and competitor: 2;
prompts: 10; per competitor: 20 = 10 × 2". Never the total alone — a bare "140
attempts" hides the shape of the round.

### 2.5 No new dependency

The page is built with the standard library: `html.escape` and string
templates, one inline `<style>`, and at most a few lines of inline JavaScript
for column sorting. No templating engine, no CSS framework, no charting
library. The bench is stdlib-first (constitution, Additional Constraints) and a
table needs nothing more.

## 3. Out of scope

- Charts of any kind.
- Visual design beyond legibility.
- The Slack post — that is work front D.
- Per-attempt Langfuse links, unless a trace id is already sitting in
  `turn_log`, in which case it is an optional column and nothing more.

## 4. Risks noted at design time

- **Tiers and domains do not exist on the pilot tasks yet.** The 10 pilot tasks
  carry `info.zapier_tools` and `info.initial_state`, and nothing else. The task
  matrix must degrade to no domain and no tier column, and the summary's
  per-tier aggregate must be absent rather than empty, until feature 005 lands.
- **Median wall-clock has no home in the current row.** Wall-clock lives per
  phase (`phases[*].wall_clock_s`); an attempt's total is the sum over its
  phases. Rows written before phases were populated have none, and the page must
  show "n/a", never 0.
- **Cost per passed attempt divides by zero** when a competitor passes nothing.
  It shows "n/a", and the page never prints an infinite ratio.
