# Data Model: results report as HTML tables

Plain names in prose; code identifiers in parentheses where they differ. Nothing
here is stored. The results store, `EpisodeRow` and every configuration file are
unchanged; this feature adds blocks to the in-memory dictionary `build_report`
returns and renders them.

## 1. What does not change

| Thing | Status |
|---|---|
| `runs` and `episodes` tables | unchanged; no migration |
| `EpisodeRow` (`runner/schema.py`) | unchanged; no new field |
| `wb_stats` functions | unchanged; called, never reimplemented |
| `audiences.yaml` and the gate | unchanged |
| `render_md` and the markdown file | unchanged |
| every configuration file and every hash | unchanged |

## 2. The report dictionary, additions

`build_report()` returns what it returns today (`run_id`, `suite`,
`config_hash`, `source_suffix`, `audience`, `arms`, `arms_stripped_by_gate`,
`baseline`, `k`, `stop_reason`, `figures`) plus five blocks. `figures` is kept
as it is so `render_md` needs no change.

### 2.1 `size`

| Field | Meaning |
|---|---|
| `prompts` | number of tasks in the round |
| `repetitions` | attempts per prompt and competitor |
| `per_competitor` | `prompts * repetitions` |
| `competitors` | how many competitors are on the page |
| `total` | attempts in total |

Rendered as the header line of `contracts/report.md` section 7. The total never
appears without the product beside it.

### 2.2 `metrics` - a list, one entry per competitor

Every field of `contracts/report.md` section 1, as a flat mapping. Values are
numbers or `None`; `None` renders as `n/a`.

| Field | Type |
|---|---|
| `arm` | str |
| `attempts`, `passed`, `infra`, `agent_errors`, `timeouts` | int |
| `strict_pass` | `{mean, sem}`, either may be `None` |
| `pass_over_repetitions` | `{k, mean, sem}` |
| `infra_rate`, `cache_hit_rate` | float or `None` |
| `cost_total`, `cost_per_attempt`, `cost_per_passed` | float or `None` |
| `tokens` | `{prompt, cached, cache_write, output}` ints |
| `wall_clock` | `{mean, median, n_with, n_total}`, means `None` when `n_with` is 0 |
| `turns`, `tool_calls` | int |
| `phases` | mapping phase name -> `{wall_clock_s, cost_usd}`; empty for a competitor with no phases beyond `run` |
| `cost_per_model` | mapping model name -> float; empty when no `model:*` phase exists |
| `questions_asked`, `declined_to_build` | int |

`phases`, `cost_per_model`, `questions_asked` and `declined_to_build` are
present on every entry; the renderer omits their columns when no competitor on
the page has anything in them.

### 2.3 `comparisons` - a list, one entry per non-baseline competitor

| Field | Type |
|---|---|
| `arm`, `baseline` | str |
| `strict_pass_diff_pp` | float or `None` |
| `pass_rate_ratio`, `cost_per_passed_ratio` | float or `None` |
| `wins`, `losses`, `both`, `neither`, `pairs`, `dropped_infra` | int |
| `mcnemar` | `{b, c, statistic, p}` as `wb_stats.mcnemar` returns it |
| `verdict` | one of the four strings of `contracts/report.md` section 2 |
| `source` | the source dictionary, as the paired figures already carry |

Empty when the round has one competitor.

### 2.4 `matrix`

| Field | Meaning |
|---|---|
| `arms` | the column order |
| `has_domain`, `has_tier` | whether any task carries them; drives the leading columns |
| `rows` | one entry per task |

A row: `task_id`, `domain` or `None`, `tier` or `None`, and `cells`, a mapping
competitor -> `{passed, attempted, infra, category, detail}` where `category` is
one of `passed`, `unexpected change`, `assertion failed`, `error`, `infra`.

### 2.5 `failures`

A list, one entry per attempt with `passed == false`, ordered by task, then
competitor, then repetition: `task_id`, `arm`, `trial`, `termination`, `error`
(may be `None`), `unexpected_change_paths` (list of str, may be empty).

### 2.6 `provenance`

Every field of `contracts/report.md` section 5: `config_hash`, `plan`,
`product`, `mode`, `price_tables` (list of `name@date`), `missing_cost`
(`{missing, total}` or `None`), `suite`, `suite_version`, `task_hashes`,
`started`, `finished`, `stop_reason`, `audience`, `withheld` (a count for a
non-internal audience, the names for `internal`).

## 3. The summary dictionary (`build_summary`)

| Field | Meaning |
|---|---|
| `rounds` | a list of per-round entries: `run_id`, `plan`, `suite`, `size`, `metrics`, `source`, `stop_reason` |
| `arms` | every competitor appearing in any round, in a stable order |
| `aggregate` | one entry per competitor: `arm`, `mean_strict_pass`, `sem`, `n_rounds`, and `per_tier` (mapping tier -> mean) when tiers are present |
| `stratification` | present only when one round is a random draw: per competitor, `random`, `tier_mean`, `diff_pp` |
| `audience` | the audience the page was built for |
| `statement` | the fixed sentence about paired comparisons never being pooled |

`aggregate` holds a **mean of per-round rates**, never a recomputation over
pooled attempts. No paired figure, no McNemar and no ratio spanning rounds
exists in this dictionary - there is no field for one.

A round is treated as the random draw when its plan name contains `random`;
absent that, `stratification` is omitted rather than guessed.

## 4. Rendering values

| Value | Rendered |
|---|---|
| `None` | `n/a` |
| a rate | percentage, one decimal, e.g. `90.0%` |
| a rate with a SEM | `90.0% +/- 10.0%` |
| money | `US$ 1.3986`, four decimals |
| a ratio | `1.86x`, two decimals |
| seconds | `16.9 s`, one decimal |
| a count | an integer, no separator below 10,000 |

Every value passes through `html.escape(..., quote=True)` before it reaches the
page, including the `title` attributes of the matrix and failures tables
(research R4).
