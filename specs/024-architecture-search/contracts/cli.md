# Contract: CLI additions and changes

Features 001 to 006's `wb run / resume / status / doctor / grade / report / summary /
corpus / monarch / approvals / approve / deny / budget` are unchanged except where
stated. Everything below is offline unless marked paid.

## `wb corpus split` (new, offline)

Draws the development and held-out slates, stratified by difficulty tier and domain,
and freezes both with one manifest. Refuses to overwrite a frozen held-out slate.

```
wb corpus split --corpus DIR[,DIR…] --size N --seed N
                --dev-out DIR --heldout-out DIR --manifest FILE
                --because TEXT
```

- `--size` is the number of tasks **per slate**. Both slates get the same size.
- The draw is stratified: within each (tier, domain) cell the two slates receive equal
  counts, remainders assigned by the seeded order. Per tier and per domain the slates
  differ by at most one task.
- The tier measure is the one `wb corpus tiers` already uses — seeded services plus
  expected changes plus tools needed, cut at the terciles of the whole corpus. The
  manifest records it, its kind (`structural-proxy`) and its version.
- `--because` is required and recorded, as `wb corpus slate` already requires.

```
$ uv run wb corpus split --corpus 'corpus/imported-*' --size 50 --seed 20260911 \
    --dev-out tasks/dev-50 --heldout-out tasks/heldout-50 \
    --manifest tasks/split-manifest.yaml \
    --because 'architecture search needs a development slate and an untouched confirmation slate'
drawn from 800 usable tasks across 7 domains
development  50 tasks   simple 17  medium 17  complex 16
held-out     50 tasks   simple 17  medium 17  complex 16
domains balanced: finance 8/8  hr 7/7  marketing 7/7  operations 7/7  sales 7/7  simple 7/7  support 7/7
frozen: tasks/dev-50 (sha 3f2a…), tasks/heldout-50 (sha 91c7…)
manifest: tasks/split-manifest.yaml
```

Refusals:

```
$ uv run wb corpus split ... --heldout-out tasks/heldout-50 ...
refused: tasks/heldout-50 is a frozen held-out slate. A held-out slate is never redrawn.
Draw a new one under a different name and retire this one with a recorded reason.
```

## `wb experiment propose` (new command, existing record — offline, never spends)

A CLI surface over the hypothesis record `wb_studio/genesis_hypotheses.py` already
validates, sizes and settles. It introduces **no new record**: the command writes the
same record Genesis's tools write, adding this feature's four fields (slate, repetitions,
lineage, power). Today that record is reachable only through Genesis's tools, which is
why a command is worth having.

The sizing it reports comes from `smallest_plan`, corrected to size against the paired
sign test that actually settles the hypothesis rather than the two-proportion
approximation it uses today (R11).

```
wb experiment propose --variant ID --predict TEXT
                      [--slate development|held-out] [--repetitions N]
```

- `--slate` defaults to `development` (FR-020).
- Runs the power check (FR-021) and the envelope check (FR-035) **before** reserving.
- Records the prediction, the parent lineage and the expected discordant-pair count.

```
$ uv run wb experiment propose --variant graph-field-owner-v2 \
    --predict 'naming the record owner in the graph raises pass rate on multi-application tasks'
admitted  exp-0007  variant graph-field-owner-v2  lineage graph-field-owner
  slate development (50 tasks)   repetitions 3   150 attempts
  expected discordant pairs 12 (minimum 6 can reach p<0.05; 10 wins of 12 needed)
  maximum $31.50 against the research envelope ($184.00 remaining this week)
```

Refusals, both before any reservation:

```
refused: 10 tasks at 1 repetition can reach at most 4 discordant pairs, assuming a flip
rate of 0.35. Six are needed before any win count reaches p<0.05, so this hypothesis
cannot be settled at this size however it turns out. Use the development slate
(50 tasks), or raise repetitions to 3.

refused: this experiment reserves up to $31.50; the research envelope has $12.40 left
this week. Short by $19.10. It will not draw on the lab's weekly ceiling.
```

## `wb experiment confirm` (new, paid)

Runs an already-supported variant once on the held-out slate.

```
wb experiment confirm --experiment ID
```

- Refuses unless the lineage has a `supported` verdict on development (FR-022).
- Refuses if any experiment in the lineage has already reached held-out (FR-022).
- On success, writes the proposal — a written specification for the engine team (FR-034).

```
refused: lineage graph-field-owner already reached the held-out slate on 2026-09-18
(exp-0007, verdict supported). A lineage reaches held-out once.
```

## `wb budget envelope` (new, offline)

Sets and shows the weekly research envelope. Strictly inside the weekly ceiling.

```
wb budget envelope --set AMOUNT --per-experiment AMOUNT --by NAME
wb budget envelope status
```

```
$ uv run wb budget envelope status
week of 2026-09-07 (America/Sao_Paulo)
research envelope   $200.00 set by Lucas    reserved $15.50   settled $0.60   left $184.00
lab weekly ceiling  $300.00                 reserved $18.90   settled $3.10   left $281.10
experiments this week: 1 admitted, 0 refused
```

## `wb run` (changed)

- **`--repetitions N`** (new, default 1). Explicit on the run and inside the config hash
  (FR-019). The Studio launch path carries the same field.
- **`--operator NAME`** is already required by `WB_OPERATOR`; the Studio path now sets it
  too (FR-007).
- A per-attempt cap is always set. A run that does not name one takes the plan's
  `attempt_cap_usd`, and never the whole run ceiling (FR-008).

## `wb monarch recipes` (unchanged, paid)

Already built (`wb_orchestrator/monarch_recipes.py`). Named here because this feature
**runs** it to produce the recipe data the curve's x-axis needs (FR-027). No change.

## `wb report` (changed)

- A round opens with the curve, the accuracy comparison with its uncertainty and sample
  count, and the gap list (FR-030).
- Attempts whose task definition has moved are marked and excluded from headline numbers
  (FR-012).
- `--for engine-team|lab|executive` chooses which framing of the gap list is written
  (FR-031). Deliberately **not** `--audience`: that word already names
  `wb_report/audiences.yaml`, the competitor allowlist that PLAN.md §1 makes a fixed
  rule ("audience rules are code"). One flag meaning both "who may appear" and "how it
  reads" would let a framing silently drop a competitor. The two stay separable.

  **Open for Lucas:** do the three framings differ only in wording, or may one withhold
  a fact another shows? "All three, from the same evidence" reads as framing-only, and
  FR-031 is written that way — no rendering may assert a fact another contradicts. If an
  executive view should omit something the engine view carries, that is a visibility
  gate under a new name and needs his explicit say-so.
