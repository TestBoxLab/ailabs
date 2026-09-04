# Data Model: Task Sets by Difficulty and the Scored AutomationBench Domains

Plain names in files; code identifiers in parentheses where they differ. Only
what feature 005 adds or changes; everything else is feature 001's data model.

## 1. Corpus task (unchanged shape, six new folders)

`corpus/imported-<domain>/<task name>.json`, one folder per domain, written by
`wb corpus import-ab` and completed by `wb corpus declare`:

```json
{
 "example_id": 501,
 "task": "sales.multi_hop_lookup",
 "prompt": [{"role": "system", "content": "…"}, {"role": "user", "content": "…"}],
 "answer": "",
 "info": {
  "zapier_tools": ["salesforce_find_records", "gmail_send_email", "…"],
  "initial_state": {"meta": {…}, "gmail": {…}, "salesforce": {…}},
  "assertions": [{"type": "salesforce_field_equals", "…": "…"}],
  "expected_changes": [{"service": "salesforce", "op": "changed", "path": "…"}],
  "allowed_changes": [{"service": "gmail", "op": "*", "path": "gmail.messages[*].is_read"}]
 },
 "contract_sha256": "e8584598a9d718a2"
}
```

Verified across all 600 scored-domain rows: `zapier_tools`, `initial_state`,
`assertions` and `task_name` are always present; `expected_changes` and
`allowed_changes` are never present before the derivation. `initial_state` may
carry a `meta` key that is bookkeeping, not a service.

Folders: `imported-simple` (200, exists), `imported-finance`, `imported-hr`,
`imported-marketing`, `imported-operations`, `imported-sales`,
`imported-support` (100 each, new).

## 2. Difficulty score (`score_task`)

```
score(task) = |{k for k in info.initial_state if k != "meta"}|
            + |info.expected_changes|
            + |info.zapier_tools|
```

One integer per task. Computed from the task file alone; no external input, no
judgment call, no randomness. Measured medians on the current corpus: simple 4,
finance 10, hr 12, marketing 12, operations 12, sales 13, support 15.

## 3. Tiers (`tier_cuts`, `tier_of`)

| Name | Meaning |
|---|---|
| `low` | the lower tercile of the whole corpus's scores; the **simple** tier |
| `high` | the upper tercile; the **complex** tier begins above it |
| `tier_of(score)` | `simple` when `score <= low`; `complex` when `score > high`; `medium` otherwise |

`low` and `high` are the two values that split the sorted score list into three
parts as equal as the distribution allows. Ties on a cut point fall in the
**lower** tier, by the comparison above — a stated rule, never a coin flip.
Measured today over 800 tasks: `low = 9`, `high = 12`.

## 4. Drawn task (`tasks/tier-<name>/<task name>.json`, `tasks/random-10/…`)

A byte copy of the corpus task with exactly two keys added:

```json
 "info": {
  "…": "…",
  "tier": "complex",
  "domain": "sales"
 }
```

| Field | Type | Meaning |
|---|---|---|
| `info.tier` | `simple` \| `medium` \| `complex` \| `random` | which drawn set this copy belongs to |
| `info.domain` | str | the corpus folder's domain it came from |

**`contract_sha256` is unchanged from the corpus original.** `contract_hash`
ignores `info.tier` and `info.domain`, so a label cannot make a copy a different
task (research R6). Nothing else in the file differs — the request text, the
starting data, the assertions and both change lists are copied verbatim.

`info.tier` on a task in `random-10` is `random`, not the tier its score falls
in; the manifest records that task's actual tier and score, so the two readings
are both available and neither is guessed.

## 5. Manifest `tasks/tiers-manifest.yaml` (`TiersManifest`)

Written by `wb corpus tiers`; read by people and by tests, not by a run.

```yaml
measure: >
  services seeded (initial_state keys except "meta") + expected changes
  (info.expected_changes) + tools needed (info.zapier_tools), computed from the
  task file; tiers are the terciles of the whole corpus, ties on a cut point
  falling in the lower tier.
generated_at: 2026-09-04T18:00:00Z
seed: 20260904
per_tier: 10
cuts: {low: 9, high: 12}
corpus:
  - {dir: corpus/imported-simple, domain: simple, tasks: 200, usable: 200}
  - {dir: corpus/imported-finance, domain: finance, tasks: 100, usable: 98}
  # … one row per corpus folder
excluded:
  finance.some_task: no approval rule (unmapped assertion types: [x_y_exists])
  sales.other_task: contract hash does not match content
sets:
  tier-simple:
    by_domain: {simple: 7, finance: 3}
    tasks:
      - {task: simple.airtable_create_contact, domain: simple, score: 3, tier: simple, contract_sha256: e8584598a9d718a2}
      # … ten rows
  tier-medium: {…}
  tier-complex: {…}
  random-10:
    by_domain: {…}
    tasks:
      - {task: support.sla_escalation, domain: support, score: 17, tier: complex, contract_sha256: …}
      # … ten rows, each with the tier its score falls in
```

| Field | Required | Meaning |
|---|---|---|
| `measure` | yes | the rule in words, so a reader needs no code to understand the classification |
| `generated_at` | yes | when it was written; not part of any hash |
| `seed` | yes | the seed that produced this draw; a different seed is a different set |
| `per_tier` | yes | how many prompts per set |
| `cuts` | yes | `low` and `high` |
| `corpus` | yes | one row per folder drawn from, with total and usable counts |
| `excluded` | yes | task id → why it was left out of the pool; may be empty |
| `sets` | yes | one entry per drawn set: per-domain counts and one row per drawn task |

Every drawn task row carries `task`, `domain`, `score`, `tier` and
`contract_sha256`, so the draw can be verified against the files without
re-running it.

## 6. Draw result (`DrawResult`, in `wb_orchestrator/tiers.py`)

Returned by the draw and printed by the command:

| Field | Meaning |
|---|---|
| `cuts` | the two cut points |
| `scored` | how many corpus tasks were scored |
| `usable` | how many entered the candidate pool |
| `excluded` | task id → reason |
| `sets` | set name → the drawn task ids in written order |
| `by_domain` | set name → domain → count |
| `written` | the paths written |

## 7. Plans `config/plans/tier-simple.yaml`, `tier-medium.yaml`, `tier-complex.yaml`, `random-10.yaml`

Same schema as feature 001; four files differing in `name`, `description` and
`tasks` only.

| Field | Value |
|---|---|
| `tasks` | `tier-simple` \| `tier-medium` \| `tier-complex` \| `random-10` |
| `mode` | `create-run` |
| `repetitions` | 2 — attempts per prompt and competitor |
| `timeout_s` | 900 |
| `concurrency` | 4 |
| `competitors` | the seven of `pilot-monarch-create-run` |
| `baseline` | `claude-opus-5/api` |
| `audience` | `internal` |
| `cost_ceiling_usd` | 40 |
| `approved_by` | `null` — Carlos approves each specific round |

Each round: **prompts: 10; attempts per prompt and competitor: 2; attempts per
competitor: 20 = 10 × 2; competitors: 7; attempts in the round: 140.**

## 8. Contract hash (`contract_hash`), changed

The hash now ignores `info.tier` and `info.domain`. Everything else it covered
before, it still covers.

**Invariant a test must hold**: the `contract_sha256` of every one of the 200
already-imported tasks is unchanged by this edit. Adding keys to the ignore list
must not move any hash that exists today, or every stored row becomes
non-regradable — the failure this feature exists to avoid.

## 9. Flow of one draw

```
read every corpus folder
  → per task: check it has an approval rule and its hash matches its content
        no  ──► excluded, named, not scored
        yes ──► score it
→ sort all scores → cut at the terciles → assign a tier to every usable task
→ for each tier, in order simple, medium, complex:
      round-robin over the tier's domains (alphabetical), one shuffled candidate
      at a time, until per_tier are held
        fewer usable than per_tier ──► refuse, naming the tier and the count
→ draw per_tier from the whole usable pool, unstratified, same generator
→ write four folders of byte copies + info.tier + info.domain (hash unchanged)
→ write the manifest
```
