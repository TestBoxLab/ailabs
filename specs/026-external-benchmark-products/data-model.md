# Data model — external benchmarks as products under test

**Feature**: [026-external-benchmark-products](spec.md) · **Date**: 2026-09-11

Entities are described by what they hold and what must be true of them. Field names are
the ones the code will use; plain names are used in prose, as `CLAUDE.md` requires.

---

## Product under test

What a round runs against. Today one file describes the simulated API set; this feature
adds the fields an external world needs. Existing fields keep their meaning.

| Field | Holds | Rules |
|---|---|---|
| `name` | the product's name | equals the file stem |
| `kind` | `simulated`, `real-api`, `real-api-ui` | already exists and is already validated |
| `world` | which adapter serves this product's attempts | **new**; must resolve in the adapter registry, else the product is refused by name |
| `source` | the source pin, below | **new**; absent for the simulated API set, whose pin lives in `data.dataset` |
| `services` | the top-level keys a snapshot of this world carries | must match what the adapter actually dumps, or the approval rules cannot address anything |
| `side_effects` | the reviewed per-service side-effect list | unchanged |
| `modes` | supported test modes | unchanged; a round asking for an unsupported mode is refused before anything is reserved |
| `participants` | paid participants inside an attempt besides the competitor | **new**; empty for two of the three worlds |

### Source pin

Which benchmark, at which version, in which configuration. It is what makes "frozen by
hash" honest for a world whose answer key lives outside our files.

| Field | Holds |
|---|---|
| `benchmark` | `enterprise-ops-gym`, `appworld`, `tau2` |
| `version` | the installed source's own version string |
| `split` | the source's own split or subset name — `dev`, `train`, a domain, a tool-set mode |
| `checker` | where the positive half comes from, in words, for the report sentence |
| `positive_half_is_end_state_only` | false for τ², whose reward is partly path-based; drives the disclosure in the comparability sentence |

**Rule**: a round records the source pin it ran under. A round whose recorded pin does
not match the installed source is refused rather than graded against a different answer
key, and existing rows stay readable, marked as belonging to the old pin.

### Participant

A paid party inside an attempt that is not the competitor. Today only τ²'s simulated
customer.

| Field | Holds |
|---|---|
| `role` | what it does — `simulated-user` |
| `model` | the pinned model id |
| `price_table` | the versioned price table its cost is computed against |

**Rules**: every field is part of the configuration hash. An attempt reserves once for
the maximum liability of every participant including the competitor; the per-attempt cap
counts all of them; a week that cannot cover the total refuses the round with the
shortfall named.

---

## World adapter

The per-source bridge. Not a configuration entity — it is code, named by
`product.world`, and its contract is [contracts/world-adapter.md](contracts/world-adapter.md).
It is listed here because the data it produces is what everything downstream reads.

Responsibilities: seed a private world for one attempt; serve it behind the three tools;
dump a snapshot; run the source's own check afterwards; report its prerequisites.

**Rule**: an adapter is imported lazily. A missing source package or runtime is a named
refusal at round preparation, never an import error at start-up, so the offline suite
runs with none of the three sources installed.

---

## Task

One request, frozen. Imported tasks keep the shape the existing task-set machinery
already reads, which is why `wb corpus slate`, `tiers` and `split` work on them unchanged.

| Field | Holds | Rules |
|---|---|---|
| `task` | the task's name | unique within its corpus |
| `prompt` | the request text | identical for every competitor |
| `source` | the source pin this task was imported under | present for external tasks |
| `source_ref` | the identifiers the source's own checker needs — its task id, its verifiers, its seed reference | opaque to us; we do not interpret it, we hand it back |
| `info.expected_changes` | the approval rule: what must change | non-empty, or the task is not usable |
| `info.allowed_changes` | what may change without being required | may be empty |
| `contract_sha256` | the content hash | recomputed and compared before any competitor runs; a mismatch refuses the round and names the task |

**What the hash covers, said plainly**: the request text, the approval rule and the
source pin. It does not cover the source's assertions, which live in the source. "Frozen
by hash before any competitor runs" therefore holds jointly with the pinned source
version, and every report on an external product says so.

---

## Snapshot

The state of one world at one instant.

**Shape**: a dictionary whose top-level keys are service names and whose values are plain
JSON. `meta` is reserved for harness state and is excluded from every comparison.

**Rules**:

- Deterministic. Two dumps of an untouched world are identical. Rows are sorted by
  primary key before dumping; this is the adapter's job.
- Plain JSON only — no source objects, no datetimes, nothing that does not survive a
  round trip through a file.
- Top-level keys equal the product's declared `services`.

This shape is not new. `wb_world/snapshot.py` already consumes exactly it, walks nested
dictionaries and lists, keys list items by `id` when present, and emits
`{service, op, path, before, after}`. No change is needed there.

---

## Verdict

What grading produces for one attempt. Both halves are required; neither alone is a pass.

| Field | Holds |
|---|---|
| `positive` | the source's own finding: passed or not, plus whatever detail it returned, kept whole |
| `positive_source` | which checker produced it |
| `collateral` | the lab's approval-rule finding: missing expected changes, unexpected changes, count violations |
| `source_collateral` | the source's own side-effect finding, where it has one — AppWorld does |
| `disagreement` | true when `source_collateral` and `collateral` differ |
| `termination` | how the attempt finished |
| `passed` | `positive` and `collateral` both passed and the attempt finished normally |
| `ungraded` | true when the source's checker failed to produce a verdict; the error is kept |

**Rules**:

- Grading runs after the attempt, from stored snapshots, outside the competitor's
  process. Nothing grades itself.
- A task with no reachable positive check does not pass. This preserves today's
  behaviour, where a task with no assertions fails, as a safety property rather than an
  accident.
- A checker that raises leaves the attempt `ungraded` with the error retained — not
  passed, not failed.
- A disagreement between the source's side-effect finding and ours is recorded and
  visible, never silently resolved.

---

## Task set

A frozen selection of tasks with a manifest, drawn by the existing machinery.

**Rules**: a task set belongs to exactly one product. Its manifest records the difficulty
measure, the seed, the source pin and every drawn task's hash — the same manifest the
existing sets carry, with the world block generalized from "which AutomationBench
revision" to "which source pin". Results from task sets belonging to different products
are never pooled, paired or averaged; an attempt to do so is refused, naming both
products.

---

## Corpus manifest

One per imported corpus, as today. The only change is its world block: it records a
source pin rather than a vendored AutomationBench revision, with the simulated API set
becoming one case of the general shape rather than the only shape.
