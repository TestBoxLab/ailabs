# Contract: configuration and task files added or changed by feature 005

Extends `specs/001-declarative-benchmark-config/contracts/config-files.md`.
Shipped examples are the contract's executable form.

## tasks/tiers-manifest.yaml (new, written by `wb corpus tiers`)

```yaml
measure: >
  services seeded (initial_state keys except "meta") + expected changes
  (info.expected_changes) + tools needed (info.zapier_tools), computed from the
  task file; tiers are the terciles of the whole corpus, ties on a cut point
  falling in the lower tier.
generated_at: 2026-09-04T18:00:00Z
seed: 20260904
per_tier: 10
cuts:
  low: 9
  high: 12
corpus:
  - {dir: corpus/imported-simple,     domain: simple,     tasks: 200, usable: 200}
  - {dir: corpus/imported-finance,    domain: finance,    tasks: 100, usable: 98}
  - {dir: corpus/imported-hr,         domain: hr,         tasks: 100, usable: 100}
  - {dir: corpus/imported-marketing,  domain: marketing,  tasks: 100, usable: 99}
  - {dir: corpus/imported-operations, domain: operations, tasks: 100, usable: 100}
  - {dir: corpus/imported-sales,      domain: sales,      tasks: 100, usable: 99}
  - {dir: corpus/imported-support,    domain: support,    tasks: 100, usable: 99}
excluded:
  finance.batch_reconcile: "no approval rule (unmapped assertion types: [xero_bill_exists])"
  sales.legacy_import: "contract hash does not match content"
sets:
  tier-simple:
    by_domain: {simple: 7, finance: 3}
    tasks:
      - {task: simple.airtable_create_contact, domain: simple, score: 3, tier: simple,
         contract_sha256: e8584598a9d718a2}
      # … ten rows
  tier-medium:
    by_domain: {finance: 2, hr: 2, marketing: 2, operations: 2, sales: 1, simple: 1}
    tasks: [ … ]
  tier-complex:
    by_domain: {hr: 1, marketing: 2, operations: 2, sales: 2, support: 3}
    tasks: [ … ]
  random-10:
    by_domain: {simple: 3, sales: 2, support: 2, hr: 1, marketing: 1, operations: 1}
    tasks:
      - {task: support.sla_escalation, domain: support, score: 17, tier: complex,
         contract_sha256: 1f0c…}
      # … ten rows; `tier` is the tier the score falls in, not the set's name
```

Rules:

- Written only by `wb corpus tiers`. Hand editing it changes nothing about the
  task files and only makes the record wrong; the drawn folders are the artefact,
  this file is the proof of how they were chosen.
- `seed` plus the corpus folders is enough to rebuild every drawn folder byte for
  byte. A reader who cannot reproduce them has found a bug.
- `excluded` names every task left out of the pool and why — always one of "no
  approval rule (unmapped assertion types: […])" or "contract hash does not match
  content".
- Every row in `sets.*.tasks` carries `contract_sha256`, which must equal the
  hash of both the corpus original and the drawn copy.
- It enters no run's configuration hash. What a run records is the drawn task
  files and their own hashes, which is what freezes the round.

## tasks/tier-simple/, tier-medium/, tier-complex/, random-10/ (new, written by the draw)

Each holds ten task files. A drawn file is its corpus original with exactly two
keys added inside `info`:

```json
 "info": {
  "zapier_tools": ["…"],
  "initial_state": {"…": "…"},
  "assertions": ["…"],
  "expected_changes": ["…"],
  "allowed_changes": ["…"],
  "tier": "complex",
  "domain": "sales"
 },
 "contract_sha256": "1f0c9ab27de4f501"
```

Rules:

- `contract_sha256` is **identical** to the corpus original's. `contract_hash`
  ignores `info.tier` and `info.domain`, so a label is not a task change (rule 5).
- Nothing else differs: the request text, the starting data, the assertions and
  both change lists are copied verbatim. No prompt and no approval rule is edited
  by this feature, ever.
- `info.tier` in `random-10` is the literal `random`; the manifest carries that
  task's actual tier and score.
- The folders are committed only after the measure is confirmed (spec FR-013 and
  Open Question 1).

## config/plans/tier-simple.yaml (new; the other three differ only in `name`, `description` and `tasks`)

```yaml
name: tier-simple
description: >
  Round on the simple third of the corpus. Ten prompts drawn by
  `wb corpus tiers --seed 20260904` and frozen; the same competitors and baseline
  as pilot-monarch-create-run, so the four difficulty rounds and the pilot can be
  read side by side. Prompts: 10; attempts per prompt and competitor: 2; attempts
  per competitor: 20 = 10 × 2; competitors: 7; attempts in the round: 140.
  Internal.
tasks: tier-simple
mode: create-run
repetitions: 2                 # attempts per prompt and competitor
timeout_s: 900
concurrency: 4
competitors:
  - {harness: oracle}
  - {model: kimi-k3-fireworks, harness: api}
  - {model: glm-5.3-fireworks, harness: api}
  - {model: claude-opus-5, harness: api}
  - {model: gpt-5.6-terra, harness: api}
  - {model: gpt-5.6-sol, harness: api}
  - {harness: monarch}
cost_ceiling_usd: 40
baseline: claude-opus-5/api
audience: internal
approved_by: null              # Carlos approves each round before it starts
```

The other three:

| File | `name` | `tasks` | description differs by |
|---|---|---|---|
| `config/plans/tier-medium.yaml` | `tier-medium` | `tier-medium` | "the middle third of the corpus" |
| `config/plans/tier-complex.yaml` | `tier-complex` | `tier-complex` | "the complex third of the corpus" |
| `config/plans/random-10.yaml` | `random-10` | `random-10` | "ten prompts drawn at random from the whole corpus, as a check on the blended average" |

Rules:

- Same competitors, baseline, mode, repetitions, timeout, concurrency, audience
  and ceiling in all four. Only the task set differs, so a difference between
  rounds is a difference in the tasks and nothing else (rule 7 across rounds).
- `approved_by` stays empty in all four. Four rounds of 140 attempts each is
  four separate decisions.
- Every description states the size in the agreed words. A bare per-competitor
  total is not acceptable in any of them.

## config/products/simulated-apps.yaml (unchanged)

Already lists all forty-seven services, which cover all forty-two the six scored
domains seed (research R4). Listed here to record that it needs no edit — and
that `wb corpus import-ab` prints the difference so a future patch to the vendored
benchmark cannot introduce a service silently.

## config/side-effects.yaml (unchanged for now)

The reviewed side-effect list is what `wb corpus declare` uses for the scored
domains, exactly as it did for the baseline domain. Extending it, if the scored
domains turn out to need it, is its own reviewed change with Lucas's sign-off
(spec Open Question 4) and is not part of this feature.
