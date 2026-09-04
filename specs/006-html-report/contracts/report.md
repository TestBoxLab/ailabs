# Contract: the tables, their columns, and every formula

The page's authority. Each metric is defined once here, computed in one place in
`wb_report/metrics.py`, and rendered by both the per-round page and the summary
page. A metric the markdown report already shows keeps that report's value: the
same function serves both.

## 0a. Two formats, one dictionary

`wb report --format html` (the default) writes the technical page; `--format
executive` writes the stakeholder page. Both render the same `build_report`
dictionary, so the audience gate and every number are identical; only the
selection and the presentation differ. The markdown file is written either way
and is unchanged.

Both pages use **Monarch's design system**, copied from
`local-docs/monarch-arquitetura.html`: the same `:root` tokens (paper, ink,
accent with washes, blue, good, crit), the same three font families and their
`<link>`, the same light/dark handling (light default, `prefers-color-scheme`,
`[data-theme]`), and the same class names - `.layout`, `nav.toc` with the crown
brand, `header.hero` with eyebrow/h1/lede/chips, `section.part` with
`.part-eyebrow` and `.h2-sub`, `.tablewrap`, `.callout`, `.badge`, `.chip`.

**Fitting a laptop.** The technical page must not scroll horizontally at
1366x768. The sidebar is 200px, main padding 28px, `.content` full width, table
text 12.5px, and header cells wrap with the full name in a `title` attribute -
a column may be abbreviated, but the source line under the table always names
every competitor in full.

## 0b. The executive page (`--format executive`)

Monarch first in every table, chart, card and row.

| Section | Content |
|---|---|
| hero | eyebrow `Monarch benchmark`, the round name, one-sentence lede, chips: date, mode, prompts, attempts per competitor, spend |
| Headline | three cards, Monarch's figure beside the best model's: success rate, cost per passed attempt, median time per attempt |
| Every competitor | the same three metrics as bar charts, every competitor, Monarch first |
| What each task asked | one full-width row per task: the request, the expected change in plain words, and **one verdict for Monarch alone** (pass / fail with its short reason / not run). The other competitors do not appear here; the whole field is two sections above |
| In one sentence | the with-Monarch and without-Monarch summary, both computed |
| Provenance | as the technical page |

**Verdict colour**, per metric: Monarch at or above the best model is `--good`,
below it is `--crit`. Success is higher-is-better; cost per passed attempt and
median time are lower-is-better. An undefined figure (no passes, so no cost per
passed attempt) is `--crit` with one line saying why - a number that cannot be
computed is not a pass.

The interruption notice, where a round stopped short, is a `.callout.warn`.

## 0. The page's seven sections

Carlos reviewed the first page (PDF of `run-20260904-192933`) and rejected its
shape: too few sections, metrics of different kinds mixed into one table. The
page is now seven sections, in this order, each with its own caption, a
one-sentence reading guide and its source line. `wb summary` mirrors the
success, cost and time tables per round.

| # | Section (`id`) | Shows |
|---|---|---|
| 1 | Overview (`overview`) | the test mode in plain words, the size line, total spend, the competitor list, plan and product |
| 2 | Success (`success`) | strict pass rate per competitor as a bar chart with error bars, the same table, the task x competitor matrix with its details table, and the paired comparison with its plain-words verdict |
| 3 | Cost (`cost`) | total / per attempt / per passed attempt, a bar chart of cost per passed attempt, the four token counts and the cache hit rate; for Monarch, cost by phase (builder, dispatch) and by model of its team |
| 4 | Time (`time`) | wall-clock mean and median with a bar chart of the median, turns and tool calls; for Monarch, builder and dispatch wall-clock separately |
| 5 | Monarch phases (`monarch-phases`) | one row per Monarch attempt; rendered only when a Monarch competitor is on the page |
| 6 | Failures (`failures`) | every attempt that did not pass |
| 7 | Provenance (`provenance`) | what produced the numbers |

**Plain names.** The page says **builder** and **dispatch**. `authoring` and
`execution` remain the phase keys on the row and are named in the Monarch
section's source line, nowhere else.

**Test mode, in words**: `create-run` renders as `create + run: Monarch builds
the workflow (builder) and runs it (dispatch)`; `run-only` as `run-only:
dispatch only, on a workflow known to be correct`; `full-flow` as `full flow:
discovery, then the builder, then dispatch`. A round with no recorded mode says
nothing about one rather than guessing.

**Charts** are inline SVG, drawn from the same `_fmt` output the table beside
them shows, so a chart and its table can never print different numbers. A
missing value renders the text `n/a`, never a zero-length bar: zero reads as
"scored nothing" rather than "not known". No external resource of any kind.

## 5a. Monarch phases table - one row per Monarch attempt

Rendered only when a Monarch competitor is present. A single pass/fail hides the
difference between a builder that declined, a builder that never finished, and
an engine that timed out running a workflow that was written correctly.

| Column | Source |
|---|---|
| task | `task_id` |
| repetition | `trial` |
| builder | `declined` when `no_workflow` is flagged; `timeout` when the attempt timed out with no `execution` phase; `error` on `agent_error`; else `done` |
| questions | the `questions_asked=N` flag, summed |
| builder s | `phases.authoring.wall_clock_s` |
| builder cost | `phases.authoring.cost_usd` |
| dispatch | `parked-timeout` on a timeout; `infrastructure` on `infra:*`; `refused` when `gate_refusals` is non-empty; `error` on `agent_error`; else `success` or `failed` on the checker's verdict |
| dispatch s | `phases.execution.wall_clock_s` |
| checker | `pass` / `fail`, from `passed` |
| reason | `error`, first 200 characters |

## Notation

- `rows` - the attempt rows of one competitor in one round, as
  `EpisodeRow.model_dump()` dictionaries from `Store.episodes(run=..., arm=...)`.
- `infra(r)` - `str(r["termination"]).startswith("infra:")`, the definition
  `wb_stats.stats._is_infra` already uses.
- `ok = [r for r in rows if not infra(r)]` - the non-infrastructure attempts.
- Every division whose denominator is 0 yields `n/a` and is rendered as the
  string `n/a`. No `inf`, no `nan`, no silent `0`.
- Money is rendered with 4 decimals; rates as percentages with one decimal;
  seconds with one decimal; counts as integers.

## 1. Metrics table - one row per competitor

| Column | Formula | Note |
|---|---|---|
| competitor | `arm` | |
| attempts | `len(rows)` | every attempt, infrastructure included |
| passed | `sum(1 for r in ok if r["passed"])` | |
| strict pass rate +/- error | `arm_summary(rows)["strict_pass"]` - mean and SEM over per-task rates, infrastructure attempts excluded | `wb_stats.arm_summary`, unchanged |
| pass rate over repetitions | `pass_hat_k(rows, k)["mean"] +/- ["sem"]` | `wb_stats.pass_hat_k`, unchanged |
| strict pass denominator | `len(ok)` | the attempts the rate divides by; shown so the exclusion is visible beside the rate |
| infra failures | `len(rows) - len(ok)` | |
| infra rate | `(len(rows) - len(ok)) / len(rows)` | **excluded from the pass denominator**; reported on its own (PLAN.md section 1, rule 7) |
| agent errors | `sum(1 for r in rows if r["termination"] == "agent_error")` | |
| timeouts | `sum(1 for r in rows if r["termination"] == "timeout")` | |
| cost total | `sum(r["cost_usd"] or 0.0 for r in rows)` | includes infrastructure attempts: they were paid for |
| cost per attempt | `cost_total / len(rows)` | |
| cost per passed attempt | `cost_total / sum(1 for r in ok if r["passed"])` | `n/a` when nothing passed |
| tokens prompt | `sum(r["tokens"]["prompt"])` | 0 when `tokens` is null |
| tokens cached | `sum(r["tokens"]["cached"])` | |
| tokens cache-write | `sum(r["tokens"]["cache_write"])` | |
| tokens output | `sum(r["tokens"]["output"])` | |
| cache hit rate | `tokens_cached / tokens_prompt` | `n/a` when prompt is 0 |
| wall-clock mean | mean of `attempt_seconds(r)` over the rows that have one | see below |
| wall-clock median | median of the same values | `n/a` when no row has one |
| turns | `sum(p["turns"] for r in rows for p in r["phases"].values())` | |
| tool calls | `sum(r["tool_calls"] for r in rows)` | the row's own total, not the phase sum |

`attempt_seconds(r) = sum(p["wall_clock_s"] for p in r["phases"].values() if
p["wall_clock_s"] is not None)`, and is **absent** (not 0) when the attempt has
no phase carrying one. Rows with no wall-clock do not contribute to the mean or
the median, and the source line states how many contributed.

### Monarch-only columns

Rendered only when at least one competitor on the page has a phase key other
than `run`; absent from the table entirely otherwise. A competitor without them
shows `n/a` in each.

| Column | Formula |
|---|---|
| authoring wall-clock | mean of `r["phases"]["authoring"]["wall_clock_s"]`; `n/a` when the key is absent on every row (a run-only round) |
| authoring cost | `sum(r["phases"]["authoring"]["cost_usd"] or 0)` |
| execution wall-clock | mean of `r["phases"]["execution"]["wall_clock_s"]` |
| execution cost | `sum(r["phases"]["execution"]["cost_usd"] or 0)` |
| cost per model | the `cost_usd` of each phase key matching `model:<name>`, summed and grouped by name, rendered `opus-4.8 US$ 1.20 - sonnet-5 US$ 0.30`; `n/a` when no such phase key exists |
| questions asked | the count carried on the `questions_asked` flag, summed over rows; 0 when no row carries it |
| declined to build | `sum(1 for r in rows if "no_workflow" in (r["flags"] or []))` |

`# ponytail: phase names are read off the row, not matched against a table of
known phases, so a phase feature 002 or 004 adds shows up with no code change
here. Ceiling: a typo in a phase name becomes a column.`

## 2. Comparison table - one row per non-baseline competitor

The baseline is the plan's, as `build_report` already resolves it. Every figure
is on the **identical attempt set** - the pairs `paired_wl` finds - and
infrastructure attempts drop the pair on either side, exactly as today.

| Column | Formula |
|---|---|
| competitor | `arm` |
| strict pass difference (pp) | `(strict_pass[arm] - strict_pass[baseline]) * 100`, one decimal, signed |
| pass rate ratio | `strict_pass[arm] / strict_pass[baseline]`; `n/a` when the baseline is 0 |
| cost per passed ratio | `cost_per_passed[arm] / cost_per_passed[baseline]`; `n/a` when either is `n/a` |
| wins | `paired_wl(rows_arm, rows_base)["wins"]` |
| losses | `["losses"]` |
| both | `["both_pass"]` |
| neither | `["neither_pass"]` |
| pairs | `["pairs"]`, with `["dropped_infra"]` named beside it |
| McNemar p | `["mcnemar"]["p"]` |
| verdict | see below |

**Verdict**, in plain words, from p and the sign of wins minus losses:

| Condition | Text |
|---|---|
| `pairs == 0` | `no comparable attempts` |
| `p >= 0.05` | `no significant difference at this size` |
| `p < 0.05` and `wins > losses` | `better than the baseline (p = 0.012)` |
| `p < 0.05` and `losses > wins` | `worse than the baseline (p = 0.012)` |

No other wording. The verdict renders p; it is never a new test.

## 3. Task matrix

One row per task of the round's task set, one column per competitor.

- **Cell**: `passed/attempted` over the repetitions of that task and competitor,
  e.g. `2/2`. When the pair contains infrastructure failures they are named and
  excluded from the denominator: `1/1 (infra 1)`. `attempted` counts the
  non-infrastructure attempts, so `0/0 (infra 2)` is a legitimate cell.
- **Reason category** per cell, taken from the first failing attempt of the pair:

  | Category | Chosen when |
  |---|---|
  | `unexpected change` | `r["unexpected_changes"]` is non-empty; the paths are the detail |
  | `assertion failed` | `r["assertions_passed"]` is false |
  | `error` | `r["error"]` is set; the string is the detail |
  | `infra` | `infra(r)`; the termination is the detail |
  | `passed` | none of the above |

  Rendered as the cell's `title` attribute **and** repeated in a details table
  below the matrix (task, competitor, repetition, category, detail), so nothing
  is available only on hover.
- **Leading columns**: `task`, then `domain` and `tier` **only when** at least
  one task carries `info.domain` / `info.tier`. Absent otherwise.
- **Row order**: by tier when present, then by task id.

## 4. Failures table

One row per attempt with `passed == false`, infrastructure ones included,
ordered by task, then competitor, then repetition.

| Column | Source |
|---|---|
| task | `task_id` |
| competitor | `arm` |
| repetition | `trial` |
| termination | `termination` |
| error | `error`, truncated at 200 characters in the cell, the full text in the cell's `title` |
| unexpected changes | the `path` of each entry of `unexpected_changes`, joined by `, `; empty when none |

When no attempt failed, the table is replaced by the line `no attempt failed`.

## 5. Source and provenance block

| Field | Source |
|---|---|
| configuration hash | `runs.config_hash` |
| plan, product | the plan and product identifiers in `config_json` |
| test mode | `config_json["mode"]` when set |
| price tables | `config_json["price_tables"]`, each as `name@prices_verified` |
| missing cost | the share of Monarch attempts flagged `cost_missing`, as `_source_suffix` already computes |
| task set | `runs.suite` and its version |
| task hashes | the distinct `contract_sha256` of the round's rows, first 8 characters each |
| run started / finished | `runs.started`, `runs.finished` |
| stop reason | `runs.stop_reason` when set |
| audience | the audience the page was built for |
| competitors withheld | the count only, for a non-internal audience; the names for `internal` |

## 6. Source line under every table

The existing string, unchanged in shape:

```
src: <task set> - v<version> - n=<denominator> - <competitors> - <run id><suffix>
```

where `<suffix>` is what `_source_suffix()` already appends: the price tables,
the share of attempts with a missing cost, and the run-only sentence. The
wall-clock columns add `- wall-clock from N of M attempts` when some rows carry
none.

## 7. The round's size, in the page header

```
prompts: 10 - attempts per prompt and competitor: 2 - per competitor: 20 = 10 x 2
- competitors: 4 - attempts in total: 80
```

The total never appears alone (design section 2.4).

## 8. Audience

The allowlist is applied where it is applied today: competitors are filtered out
of the query before any statistic is computed. No table on this page may re-read
the store for a competitor the gate removed. For a non-internal audience, every
dollar column of sections 1 and 2 is replaced by its ratio against the baseline,
as `build_report` already does for `cost_ratio_vs_baseline`.

## 9. Summary page (`wb summary`)

| Section | Content |
|---|---|
| header | the rounds on the page, each with its run id, plan, task set and the size line of section 7 |
| per round | the metrics table of section 1, once per round, each with its own source line |
| aggregate | one row per competitor: mean strict pass rate over the rounds where it ran, the number of such rounds, and - when tiers are present - one column per tier |
| stratification check | the random-draw round's strict pass rate beside the mean of the tier rounds, per competitor, with the difference in percentage points |
| statement | the sentence `Paired comparisons are computed per round, on that round's identical task set, and are never pooled across rounds.` |

The aggregate is a **mean of per-round rates**, never a recomputation over
pooled attempts:
`mean(strict_pass[round][arm] for round in rounds if arm in round)`. Its error
bar is the SEM over those round rates when there are at least two.

No paired comparison, no McNemar and no ratio spanning more than one round
appears on the summary page.
