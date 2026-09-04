# Implementation Plan: Task Sets by Difficulty and the Scored AutomationBench Domains

**Branch**: `005-task-tiers` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-task-tiers/spec.md`; design of
record `docs/superpowers/specs/2026-09-04-task-tiers-design.md`.

## Summary

Let `wb corpus import-ab` name the six scored domains (and `all`), so the corpus
grows from 200 to 800 tasks through the machinery that already imported the
baseline domain and derives approval rules from the reviewed side-effect list.
Add one offline command, `wb corpus tiers --seed N`, that scores every corpus
task (services seeded + expected changes + tools needed), cuts the corpus at its
terciles, draws ten per tier stratified by domain plus ten from the whole corpus,
and writes four frozen task folders plus a manifest recording the measure, the
cut points, the seed and every drawn task. Drawn tasks are byte copies with
`info.tier` and `info.domain` added and the contract hash unchanged — the two
keys are excluded from the hash. Add four plans, one per set. Nothing here calls
a model; the four rounds are separate decisions Carlos takes later.

## Technical Context

**Language/Version**: Python 3.13, `uv`

**Primary Dependencies**: none new. Stdlib (`random`, `hashlib`, `json`,
`statistics`) plus PyYAML, already present. The vendored benchmark is read
through its own loader, as today.

**Storage**: task JSON files under `workflowbench/corpus/` and
`workflowbench/tasks/`; one YAML manifest; four YAML plans. No database change.

**Testing**: pytest, offline, no key, no network. A small synthetic corpus built
in a temporary directory drives every scoring, tier and draw test; a stub dataset
drives the import test, so the vendored tree is not required to run the suite.

**Target Platform**: Windows host (Carlos) and Linux CI. The draw must produce
identical bytes on both, which is why files are written with sorted keys and
explicit newlines.

**Project Type**: CLI tool + library (`workflowbench`).

**Performance Goals**: scoring and drawing over 800 tasks in under five seconds;
the import of six domains bounded by the vendored loader, a few minutes at worst.

**Constraints**: constitution §III (rules 5, 7, 8 and 11 enforced, none changed),
§IV (nothing here spends; the four plans ship unapproved and each round needs its
own approval with the attempt arithmetic and a cost band), §V (plain names,
English). The drawn sets are not committed before the measure is confirmed
(FR-013).

**Scale/Scope**: 800 corpus tasks, 4 drawn sets of 10, 4 plans; 2 modules
changed, 1 new module, 1 new manifest, 4 new plans, 3 docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Brainstorm → spec → plan → tasks → execute | PASS | Brainstormed with Carlos 4 Sep; design of record written; spec 005 restates it; this is the plan. |
| II. Test-first | PASS | Every unit of logic — the score, the cut points, the tie rule, the shuffle order, the stratification, the exclusions, the hash invariance — gets a failing test first, all offline on a synthetic corpus. |
| III. Methodology fixed; inputs change | PASS | No rule in `PLAN.md` §1 changes. New inputs: six corpus folders, four task sets, four plans, one manifest. Rule 5 is the reason drawn tasks are byte copies with an unchanged hash; rule 7 is the reason the four rounds are separate and never pooled; rule 8 is the reason the manifest exists at all. |
| IV. Money and pre-registration gates | PASS | Nothing in this feature calls a model. The four plans ship with `approved_by: null` and state the attempt arithmetic in the agreed words. The classification is pre-registered before the sets are committed (FR-013). |
| V. Plain language, graph-grounded | PASS | Graph consulted (`corpus`, `declare`, `config.resolve`, `contract_hash`). Files in English with plain names; "tier" is defined in the spec's vocabulary table. Graph refresh is the last task. |

**Additional constraints**: stdlib-first; the vendored tree is read, never
written; provenance kept (the manifest is the reproducibility artefact and enters
no run hash of its own — the drawn task files carry their own hashes, which is
what a run already records).

Post-design re-check (after Phase 1): unchanged, PASS. Three ponytail notes
carried into code comments: the import stays one function over the vendor's
loader (R3), the two ignored hash keys rather than a sidecar file (R6), and the
round-robin stratification rather than proportional allocation (R8).

## Project Structure

### Documentation (this feature)

```text
specs/005-task-tiers/
├── spec.md
├── plan.md                    # this file
├── research.md                # R1–R11
├── data-model.md              # score, tiers, manifest, drawn task, plans
├── quickstart.md              # offline proof + the ordered, gated rounds
├── contracts/
│   ├── cli.md                 # wb corpus import-ab --domains all; wb corpus tiers
│   └── config-files.md        # manifest, the four plans, info.tier / info.domain
├── checklists/requirements.md
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root: `monarch-benchmark/workflowbench/`)

```text
wb_orchestrator/
├── corpus.py               # CHANGE: import_ab accepts the scored domains and "all",
                            #         and a per-domain destination
├── tiers.py                # NEW: score, cut points, the draw, the manifest writer
├── orchestrator.py         # CHANGE: contract_hash ignores info.tier / info.domain
└── cli.py                  # CHANGE: `corpus tiers` subcommand; import-ab dest pattern
config/
└── plans/
    ├── tier-simple.yaml    # NEW
    ├── tier-medium.yaml    # NEW
    ├── tier-complex.yaml   # NEW
    └── random-10.yaml      # NEW
corpus/
└── imported-<domain>/      # NEW, written by the import (six folders, 600 tasks)
tasks/
├── tier-simple/            # NEW, written by the draw (committed after FR-013)
├── tier-medium/            # NEW
├── tier-complex/           # NEW
├── random-10/              # NEW
└── tiers-manifest.yaml     # NEW
tests/
├── test_tiers.py           # NEW: scoring, cut points, the draw, determinism, exclusions
├── test_corpus.py          # CHANGE: the scored domains and "all" in the import
├── test_config.py          # CHANGE: the four plans load and validate
└── test_run_config.py      # CHANGE: the banner's attempt arithmetic
```

Docs touched (repo root): `monarch-benchmark/PLAN.md`, project `CLAUDE.md`,
`monarch-benchmark/workflowbench/config/README.md`.

**Structure Decision**: one new module. The draw is self-contained — read task
files, score, cut, shuffle, copy, write — and shares nothing with the import
except the folder it reads, so folding it into `corpus.py` would only make that
file longer. The hash change belongs in `orchestrator.py` where `contract_hash`
lives, because every caller must see the same ignore list.

## Design notes that tasks depend on

1. **The hash ignore list is the load-bearing change.** `contract_hash` must
   ignore `info.tier` and `info.domain` before anything writes a drawn file,
   otherwise every drawn copy is a new task. It is tested against the existing
   corpus first: the hashes of the 200 already-imported tasks must not move.
2. **The score reads `expected_changes`, so it runs after the derivation**, never
   before. A corpus folder that has not been declared scores every task low and
   would corrupt the tiers; the draw therefore excludes tasks with no approval
   rule (R9) rather than scoring them as zero-change.
3. **One seeded generator, one fixed consumption order** (R7). Determinism is a
   property of the whole draw, not of one shuffle, so the test compares whole
   directory trees byte for byte, not individual lists.
4. **Stratification is a round-robin** over the tier's domains in alphabetical
   order (R8). The manifest records the per-domain counts so the result is
   visible without re-running.
5. **The draw never writes into the corpus folders it reads** (FR-025). It opens
   them read-only and writes only under the output directory.
6. **The four plans differ in exactly one field**, the task set. Writing them from
   one template by hand is four small files; generating them would be a machine
   for four lines.
7. **The banner arithmetic** is a formatting change in the run banner, stated as
   "prompts: N; attempts per prompt and competitor: K; attempts per competitor:
   N×K; competitors: C; attempts in the round: N×K×C". It applies to every plan,
   not only these four, and is asserted in a test.

## Complexity Tracking

No constitution violations. One new module, one new subcommand, one ignore list.
The alternative considered and rejected — computing the tier at report time
instead of freezing it into drawn sets — would mean the sets were never frozen,
the classification could change after results were seen, and the four rounds
would not be four rounds at all but one round re-sliced, which is exactly the
blended number this feature exists to replace.
