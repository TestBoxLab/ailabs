# Contract: measures, the curve, and what a report asserts

Every number is computed once, server-side, from stored results — unchanged from the
existing rule. This contract names what changes.

## One estimator for uncertainty

`measures.wilson` is the only interval in the codebase.

| Consumer | Before | After |
|---|---|---|
| Rank in Standings | Wilson over attempts (`measures.pass_rate`) | unchanged |
| Interval shown beside rank | Wald over per-task shares (`leaderboard.uncertainty`) — can return zero width | Wilson over attempts, the same source as the rank |
| Difficulty interval | a third Wilson inlined in `difficulty.py` | `measures.wilson` |

A 95% interval is never zero-width. Rank and the interval printed beside it always come
from the same estimator.

## One cohort key

`report_data` uses `leaderboard`'s key. The weaker key is deleted.

Results are pooled only when **all** of these agree: task definitions (hashes), track,
judge, assistance, world manifest, workflow contract. A cohort missing a pinned judge is
rendered with its existing provisional sentence.

## One failure classification

`narrative.MODES` is the single taxonomy. Any second presentation of the same attempts
derives from it. `failure_analysis` buckets are either derived from `narrative` or
removed; two independent classifiers of one attempt set are a defect, not two views.

## Liveness of a stored attempt

Before rendering, each stored attempt's recorded task hash is compared with the current
corpus.

| State | Meaning | Rendering |
|---|---|---|
| `live` | hash matches the corpus | normal |
| `superseded` | the task definition has moved since grading | marked; excluded from every headline number and figure, or visibly distinguished |
| `absent` | the task is no longer in the corpus | marked; excluded |

A superseded attempt is **never** regraded against the replacement definition. The mark
is the deliverable.

## False completion

- Computed only over competitor-produced output, never over request text echoed back
  alongside it.
- Labelled as inferred from wording **at every point it is displayed**, not only under a
  chart in a different section.
- Absent when the competitor produced no output of its own.

## Service naming

An attempt's story names the service actually called, resolved from the full host, not
from a substring. Services sharing a provider domain are distinguished — `googleads`,
`sheets`, `drive`, `calendar` and `gmail` are five services, not one.

## Cost

| Measure | Definition |
|---|---|
| `cost_usd` | Existing total per attempt. Unchanged |
| `cost_by_phase` | Phase → cost, from `langfuse_cost.CostSummary.by_phase`. Phases: `authoring`, `execution`, `discovery` |
| `cost_per_pass` | Cohort cost divided by passes. `no passes` when nothing passed — never `unknown` |

Rules:
- Parts reconcile with the total to within one cent.
- Unknown is never zero and never omitted; it holds its reservation.
- `n/a` (this competitor has no such phase) is distinct from `unknown` (we could not
  read it).

## Time

| Measure | Definition |
|---|---|
| `duration_s` | Existing total per attempt. Unchanged |
| `configure_s` | Start to `authoring_ended_at` |
| `execute_s` | `authoring_ended_at` to finish |

Parts reconcile with the total to within one second.

## The curve

For each competitor, cumulative cost against number of executions:

```
reusable-artifact competitor:   configure + n × execute
per-request competitor:         n × per_request
```

- Costs are **per successful task** (FR-028), so a cheap competitor that fails is not
  cheap.
- The crossing point is the least integer `n` at which the product's cumulative cost
  falls below the compared competitor's.
- When no crossing exists within the observed range of `n`, the figure says so in words.
  It does not extrapolate.
- The same computation produces a time curve.
- Every figure carries its source line and a downloadable data table, as existing figures
  already do.

## The gap list

One record per gap, three renderings, one evidence base.

| Field | Rule |
|---|---|
| `evidence_kind` | `confirmed-result` or `code-reading`. The two are never presented as peers |
| `confirmed` | true only after a held-out confirmation; unconfirmed items are marked |
| renderings | engine-team (defects), lab (backlog), executive (frontier-gap narrative) |

No rendering may assert a fact another contradicts. A `code-reading` item stays
internal-only, per the existing rule that facts from Monarch's code do not leave the lab.

## Model-written prose

Unchanged in principle, stated here because the curve and the gap list sit beside it: a
model-written sentence is never rendered as a peer of a computed number, and a model does
not choose its own "fact" label.
