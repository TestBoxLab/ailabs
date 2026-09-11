# Data model: the search loop

**Feature**: 024-architecture-search | **Date**: 2026-09-11

Entities from the spec, with the records that hold them. Existing structures are named
so the plan wires rather than duplicates; new fields are marked **new**.

---

## Slate

A frozen, hashed set of tasks. Two exist: `development` and `held-out`. Stored the way
task sets already are — a directory of task files under `workflowbench/tasks/` — beside
a manifest, exactly as `tasks/achievable-50/` sits beside `achievable-50-manifest.yaml`.

| Field | Type | Rule |
|---|---|---|
| `name` | string | `development` or `held-out` |
| `tasks` | list of task id + `contract_sha256` | Frozen before any competitor runs |
| `role` | enum | `development` \| `held-out` |

**Validation**
- Every task hash is recorded at freeze time and never rewritten in place.
- The two slates are disjoint.
- Per difficulty tier and per domain, the two slates differ by at most one task (SC-013).

**State**: drawn → frozen. A held-out slate has no further transition; a redraw is
refused (FR-018).

---

## Slate manifest

One YAML file recording how the split was drawn, modelled on the existing
`tasks/tiers-manifest.yaml`.

| Field | Type | Rule |
|---|---|---|
| `measure` | string | Prose naming the difficulty measure |
| `measure_version` | string | **new** — so a later classification supersedes without rewriting history (FR-033) |
| `measure_kind` | enum | `structural-proxy` \| `empirical` \| `multidimensional`. Today `structural-proxy` |
| `cuts` | map | Tier cut points, as `tiers-manifest.yaml` already records |
| `seed` | int | The draw seed |
| `domains` | map | domain → count per slate, proving the spread |
| `tiers` | map | tier → count per slate, proving the mix |
| `tasks` | list | id, tier, domain, slate, `contract_sha256` |
| `generated_at` | timestamp | |

---

## Variant

A proposed change to the design space.

| Field | Type | Rule |
|---|---|---|
| `id` | string | |
| `kind` | enum | `architecture` \| `prompt-style` \| `graph-field` \| `technique` |
| `parent` | variant id or null | Null only for a root |
| `lineage` | string | **new** — the root's id; the key the once-only held-out rule uses |
| `subject` | reference | The published architecture version, prompt or graph field under test |
| `source` | reference | The library source or prior result it was argued from |

**Validation**
- A variant whose subject is identical to an already-tested variant is refused unless it
  declares itself a replication (spec edge case).

---

## Experiment record — the existing hypothesis record, extended

**This is not a new entity.** It is the record `wb_studio/genesis_hypotheses.py` already
validates, sizes and settles (R13). `check_hypothesis` (`:41`) validates the first block
below today; `settle` (`:409`) already produces `supported`; `smallest_plan` (`:517`)
already turns a record into a priced launch payload. Only the four **new** fields are
added by this feature.

| Field | Type | Rule |
|---|---|---|
| `claim` | string | Existing. Pre-registered before dispatch (FR-023) |
| `population` | object | Existing. The tasks in scope |
| `comparison` | object | Existing. Two setups, `a` and `b` |
| `measure`, `direction`, `minimum_effect` | — | Existing |
| `prior` | float or absent | Existing. A probability between 0 and 1 |
| `slate` | enum | **new** — `development` \| `held-out` (FR-020, FR-022) |
| `repetitions` | int | **new** — explicit on the run (FR-019) |
| `lineage` | string | **new** — the root record's id; the key the once-only held-out rule uses (FR-022) |
| `power` | object | **new** — assumed flip rate, expected discordant pairs, minimum needed, and observed after the run (FR-021) |
| `baseline` | run + setup reference | Existing behaviour: reused, not re-run (`report_data.historical_baseline`) |
| `paired` | object | Existing, from `measures.paired`: wins, losses, ties, delta, p_value |
| `outcome` | enum | Existing, from `settle`: `supported` \| `not-supported` \| `inconclusive` |
| `reserved_usd` / `settled_usd` | decimal | Against the research envelope |

**Sizing (corrected, R11)**: `smallest_plan` currently computes
`n = ceil(4·p·(1−p)/d²)` floored at 10 — a two-proportion normal approximation for
independent samples — while `settle` decides with a paired sign test over discordant
pairs. The two must agree. Sizing is against the test that settles it, and ten tasks is
below the floor at which that test can conclude.

**State**: proposed → (refused | admitted) → running → recorded → (confirmed | closed).

**Validation**
- `proposed → admitted` requires: the power check passes (FR-021), the envelope can cover
  the maximum (FR-035), and the slate is the development slate unless this is a
  confirmation (FR-020, FR-022).
- `slate == held-out` requires an earlier `supported` verdict on development for the same
  lineage, and no prior held-out record for that lineage (FR-022).
- `verdict` is `inconclusive` when discordant pairs are zero — never "no difference"
  (spec edge case).

---

## Research envelope

| Field | Type | Rule |
|---|---|---|
| `week_start` | date | Monday 00:00 America/Sao_Paulo, matching the ledger |
| `amount_usd` | decimal | Set by a person (FR-035) |
| `per_experiment_ceiling_usd` | decimal | Set by a person |
| `set_by` | string | The person, recorded |
| `reserved_usd` / `settled_usd` | decimal | Counted per FR-005 |

**Validation**
- Strictly inside the lab's weekly ceiling; exhaustion stops the loop and never draws on
  the remainder (FR-035, SC-014).
- A holding reservation counts at its **reserved maximum** until settled, not at its
  settled-so-far amount — the defect R12 names.

---

## Attempt cost and time

Extends the existing result row. The phase breakdown already exists upstream
(`langfuse_cost.CostSummary.by_phase`, phases `authoring` / `execution` / `discovery`)
and is currently discarded below the arm.

| Field | Type | Rule |
|---|---|---|
| `cost_usd` | decimal | Existing total. Unchanged, and must reconcile with the parts |
| `cost_by_phase` | map | **new on the row** — phase → cost. Wired from `by_phase` (R2) |
| `duration_s` | float | Existing total |
| `authoring_ended_at` | timestamp | **new** — the single recorded value FR-025 needs (R3) |
| `configure_s` / `execute_s` | float | Derived from the timestamp |

**Validation**
- Parts reconcile with the total: cost within one cent, time within one second (SC-009).
- An unreadable side is `unknown`, never zero, and holds its reservation (FR-026) —
  reusing the existing `cost_missing` flag discipline.
- A competitor with no authoring phase records **not applicable**, distinct from unknown
  (R2).

---

## Curve point

Derived, not stored.

| Field | Type |
|---|---|
| `competitor` | string |
| `executions` | int |
| `cumulative_cost_usd` | decimal |
| `cumulative_time_s` | float |

**Derivation**: `configure + n × execute` for a competitor that builds a reusable
workflow; `n × per_request` for one that does not. The crossing point is the least `n`
where the product's cumulative cost falls below the competitor's, or `none-in-range`
(FR-029). Cost is per successful task (FR-028).

---

## Gap item

| Field | Type | Rule |
|---|---|---|
| `id` | string | |
| `statement` | string | What stands between the product and the frontier |
| `evidence_kind` | enum | `confirmed-result` \| `code-reading`. Never presented as peers (FR-032) |
| `evidence` | references | Experiment records, attempts, or code-index entries |
| `confirmed` | bool | True only after a held-out confirmation (FR-032) |
| `audience_renderings` | map | engine-team \| lab \| executive — three views, one base (FR-031) |

**Validation**
- A `code-reading` item is internal-only, per the existing rule that facts from Monarch's
  code do not leave the lab.
- Renderings are derived from this record; none may assert a fact another contradicts
  (SC-011).

---

## Proposal

Produced by a held-out confirmation (FR-034). A written specification for the engine
team — not an executable artifact.

| Field | Type |
|---|---|
| `variant` | variant id |
| `paired_result` | the confirming experiment's paired object, with uncertainty |
| `slate` + `repetitions` | what it was measured on |
| `rationale` | why it wins, citing attempts |

---

## Relationships

```text
Slate manifest ──describes──> Slate (development, held-out)
Variant ──parent──> Variant          (lineage = root id)
Experiment record ──tests──> Variant
Experiment record ──runs on──> Slate
Experiment record ──reserves against──> Research envelope
Experiment record ──pairs against──> baseline run rows
Attempt cost/time ──aggregates into──> Curve point
Experiment record (confirmed) ──produces──> Proposal
Experiment record | code index ──evidences──> Gap item
```
