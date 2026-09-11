# Contract: configuration and data files added or changed

## `tasks/split-manifest.yaml` (new)

How the development and held-out slates were drawn. Modelled on the existing
`tasks/tiers-manifest.yaml`, which this file deliberately resembles.

```yaml
measure: services seeded (initial_state keys except "meta") + expected changes
  (info.expected_changes) + tools needed (info.zapier_tools), computed from the task
  file; tiers are the terciles of the whole corpus, ties on a cut point falling in
  the lower tier.
measure_kind: structural-proxy      # not empirical difficulty; see AI-LABS-DIRECTION.md
measure_version: '1'                # a later classification supersedes without rewriting
generated_at: '2026-09-11T14:02:07Z'
seed: 20260911
per_slate: 50
because: architecture search needs a development slate and an untouched confirmation slate
cuts:
  low: 10
  high: 15
corpus:
  - dir: corpus/imported-finance
    domain: finance
    tasks: 100
    usable: 100
  # … one per domain
balance:
  development: {tiers: {simple: 17, medium: 17, complex: 16},
                domains: {finance: 8, hr: 7, marketing: 7, operations: 7, sales: 7,
                          simple: 7, support: 7}}
  held-out:    {tiers: {simple: 17, medium: 17, complex: 16},
                domains: {finance: 8, hr: 7, marketing: 7, operations: 7, sales: 7,
                          simple: 7, support: 7}}
tasks:
  - id: finance.invoice_approval_routing
    slate: development
    tier: complex
    domain: finance
    score: 17
    contract_sha256: 4b1e…
  # … 100 rows, both slates
```

Rules:
- Written once at freeze. Never rewritten in place; a redraw writes a new manifest and
  the old slate is retired with a recorded reason.
- Per tier and per domain, the two slates differ by at most one task.
- `measure_kind` and `measure_version` exist so a later empirical or multidimensional
  classification supersedes this one without invalidating the frozen slates.

## `genesis/envelope.json` (new)

The weekly research envelope. Sits beside the existing `genesis/autonomy.json`.

```json
{
  "week_start": "2026-09-07",
  "amount_usd": "200.00",
  "per_experiment_ceiling_usd": "45.00",
  "set_by": "human:lucas",
  "set_at": "2026-09-11T13:40:02Z"
}
```

Rules:
- Absent means **zero**, not unlimited. With no envelope the loop proposes and never
  spends.
- `amount_usd` must be strictly below the lab's weekly ceiling.
- Exhaustion stops the loop; it never draws on the ceiling's remainder.
- Accounting per FR-005: a holding reservation counts at its reserved maximum until it
  settles.

## `genesis/autonomy.json` (changed)

Defaults invert. Absent file now means **off**, not on.

| Dial | Before | After |
|---|---|---|
| `cards` | `act` | `off` |
| `runs` | `smoke` | `off` |
| `initiative` | `off` | `off` |
| `paused` | `false` | `false` |

A workspace that has never been configured performs no paid activity (FR-002). The
watcher and the scheduler do not start until a person enables them.

## Plan files (changed)

Two new optional fields, both inside the config hash.

```yaml
repetitions: 3          # explicit; default 1 (FR-019)
attempt_cap_usd: '3.00' # already exists in the CLI path; now always set (FR-008)
```

## Front-door configuration (changed)

The proxy gains an unguessable per-run path segment. Monarch is unaffected because the
segment rides in the seed URL, which `wb monarch setup --front-door` already templates.

```
before:  https://<studio>/front-door/airtable/v0/...
after:   https://<studio>/front-door/<run-secret>/airtable/v0/...
```

- The secret is generated per run, stored with the run record, never logged, never
  rendered in a report.
- A request to `/front-door` without a valid current secret is refused before any relay.
- Every method — GET, POST, PUT, PATCH, DELETE — is checked. Today `do_PUT`, `do_PATCH`
  and `do_DELETE` reach the proxy without any authentication call at all.

## Result rows (changed)

Additions only; the existing total fields keep their meaning and must reconcile.

```json
{
  "cost_usd": "1.52",
  "cost_by_phase": {"authoring": "1.08", "execution": "0.44"},
  "duration_s": 211.0,
  "authoring_ended_at": "2026-09-11T14:05:18Z",
  "configure_s": 197.0,
  "execute_s": 14.0
}
```

- `cost_by_phase` is wired from the existing `langfuse_cost.CostSummary.by_phase`, whose
  phases are `authoring`, `execution` and `discovery`. No new telemetry.
- A competitor with no authoring phase writes `"authoring": "n/a"` — not applicable,
  distinct from unknown and from zero.
- An unreadable side writes `"unknown"` and holds its reservation, reusing the existing
  `cost_missing` flag discipline.
