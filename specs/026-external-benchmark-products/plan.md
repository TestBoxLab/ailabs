# Implementation Plan: External benchmarks as products under test

**Branch**: `026-external-benchmark-products` | **Date**: 2026-09-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/026-external-benchmark-products/spec.md`

## Summary

Three external benchmarks — EnterpriseOps-Gym, AppWorld and τ²-bench — become products
under test with their own task sets, selectable by `wb run --product X --plan Y`.

The technical approach came out of Phase 0 smaller than it looked. The machine already
has the seam; it just has no name. `wb_world/snapshot.py` and `grader/invariant.py` are
world-agnostic already. The whole coupling to AutomationBench sits in three places:
`Episode` is constructed directly at `wb_orchestrator/orchestrator.py:559`, the positive
half of `grader/grade.py` goes through the vendor's assertion registry, and
`wb_arms/http_shim.py` takes an `Episode` by type. So the work is: name the interface
that the surrounding code already demands of an episode, make the product choose the
implementation, make the positive half a per-product path, and write three adapters.

The three adapters differ mostly in how they seed and dump a world. Their checks are run
as shipped: EnterpriseOps-Gym's verifiers are SQL strings with expected values,
AppWorld's is a `.evaluate()` call, τ²'s is its own reward. The lab supplies the
"nothing else changed" half for all three from its own snapshot diff.

## Technical Context

**Language/Version**: Python 3.13, managed by `uv` (`pyproject.toml:9`)

**Primary Dependencies**: existing — `pydantic`, `mcp>=1.0`, `automation-bench`,
`pyyaml`, the provider SDKs. New, both **optional extras** so the offline suite runs
without them: `appworld`, `tau2`. EnterpriseOps-Gym needs no new dependency (`mcp` is
present, `sqlite3` is standard library, its verifiers are data). Reasons in
[research.md](research.md) R9.

**Storage**: task files as JSON under `workflowbench/corpus/` and `workflowbench/tasks/`
as today; run records in `out/wb.sqlite3`; the weekly ledger in
`research/budget.sqlite3`. External world data lives outside the repository, named by
product configuration.

**Testing**: `cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.
The whole feature's tests run offline: no containers, no downloads, no network, no
provider keys (FR-032). Recorded fixtures stand in for each source.

**Target Platform**: Windows 11 for development, Linux for the hosted Studio. The
EnterpriseOps-Gym adapter needs a container runtime at round time and refuses by name
when it is absent (FR-007).

**Project Type**: a Python command-line benchmark with a web Studio beside it. Single
project, existing package layout.

**Performance Goals**: none new. An attempt's wall clock is dominated by the competitor,
not by the adapter. One constraint does bite: a snapshot must be deterministic, so
adapters sort rows by primary key before dumping ([research.md](research.md) R3).

**Constraints**: offline-capable tests; stdlib-first; no paid round launched by anything
in this feature; the weekly ledger and approval gate unchanged; every task frozen by
hash before any competitor runs.

**Scale/Scope**: three adapters, three importers, three product files, at least one
frozen task set and one plan per world. Frozen sets are drawn small — about ten tasks —
by the existing machinery. The sources hold 1,150, 750 and several hundred tasks
respectively; importing them is cheap, running them is a budget decision for a later
round and is out of scope here.

## Constitution Check

*GATE: must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Before research | After design |
|---|---|---|---|
| **I — Brainstorm → spec → plan → tasks → execute** | The spec came from a settled brief, not a cold start. Planning does not write code. | PASS — brainstormed with Lucas on 11 Sep, four decisions recorded in the spec. Superpowers commands are unavailable in this session, so execution follows [docs/HARNESS-PROCEDURES.md](../../docs/HARNESS-PROCEDURES.md) with the same artifacts and gates. | PASS |
| **II — Test-first** | Red → green → refactor; no task complete without runnable evidence; the suite is the named pytest command. | PASS | PASS — every task in `tasks.md` starts with a failing test. Recorded fixtures per source keep the suite offline. |
| **III — Methodology is fixed; features change its inputs** | No rule in `PLAN.md` §1 may be reopened. | PASS — this feature adds products and task sets, which are inputs. | PASS — and three fixed rules are strengthened rather than touched: "nothing grades itself" (FR-011), "frozen by hash" (FR-018, with the joint-pinning caveat made explicit in FR-028), "paired comparisons only on identical sets" (FR-030). |
| **IV — Money and pre-registration** | Ledger and approval gates unchanged; nothing launches a paid round. | PASS | PASS — τ²'s second participant is folded into the existing per-attempt reservation rather than given a new money path ([research.md](research.md) R6). No task in this feature spends. |
| **V — Plain language, graph-grounded** | English; plain names in shared docs; ground in the graph. | PASS with a correction: `graphify-out/` does not exist (CLAUDE.md, final section). Grounding is the code and the file map. | PASS — artifacts use the plain names (competitor, task set, approval rule, answer key, product under test). |
| **Additional — stdlib-first, dependency reasons** | New dependencies need a reason. | PASS | PASS — two new optional extras, each with a reason in [research.md](research.md) R9; EnterpriseOps-Gym adds none. |
| **Additional — upstream immutability** | Do not edit another benchmark's world or assertions. | PASS | PASS — decision D1 is the whole point: their checker runs as shipped. τ²'s partly path-based reward is disclosed, not filtered ([research.md](research.md) R2). |
| **Additional — publication** | Pushes and publication need Carlos's explicit request. | PASS | PASS — nothing here publishes. AppWorld content is never committed (FR-020, [research.md](research.md) R5). |

No violations. The Complexity Tracking table below stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/026-external-benchmark-products/
├── plan.md              # This file
├── spec.md              # Phase -1: the settled brief as a specification
├── research.md          # Phase 0: evidence for every unknown, plus three spikes
├── data-model.md        # Phase 1: entities and the snapshot contract
├── quickstart.md        # Phase 1: runnable, offline-first validation
├── checklists/
│   └── requirements.md  # Specification quality
├── contracts/
│   ├── world-adapter.md     # What every world implements
│   ├── config-files.md      # Product configuration additions
│   ├── cli.md               # Importers and the per-product front door
│   └── report.md            # The comparability sentence
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source code (repository root)

Paths below are under `monarch-benchmark/workflowbench/`. New files are marked; every
other line is an existing file this feature touches.

```text
wb_world/
├── adapter.py                    NEW  the world-adapter protocol (contracts/world-adapter.md)
├── registry.py                   NEW  product name -> adapter, lazy import, named refusal
├── episode.py                    —    unchanged; it already satisfies the protocol
├── snapshot.py                   —    unchanged (diff_snapshots is world-agnostic)
├── openapi.py                    —    unchanged; joined by the tool-wrapping publisher
└── tools_openapi.py              NEW  publish a tool list as operations (research.md R4)

wb_worlds/                        NEW  one package per external source
├── enterprise_ops/
│   ├── adapter.py                     seed from the task's .sql, serve, snapshot, verify
│   ├── importer.py                    dataset rows -> task files
│   └── LEGAL.md                       Apache-2.0, ServiceNow AI Research
├── appworld/
│   ├── adapter.py                     AppWorld(task_id=...) lifecycle, .evaluate()
│   ├── importer.py                    train and dev only (research.md R5)
│   └── LEGAL.md                       dual licence; content never committed
└── tau2/
    ├── adapter.py                     domain environment, tools, reward, paid customer
    ├── importer.py
    └── LEGAL.md                       MIT, Sierra Research

grader/
├── grade.py                      —    positive half becomes a per-product path
└── invariant.py                  —    unchanged

wb_arms/
└── http_shim.py                  —    takes the adapter protocol instead of Episode

wb_orchestrator/
├── orchestrator.py               —    line 559: adapter from the product, not Episode
├── config.py                     —    product schema: source pin, participants, world
├── corpus.py                     —    manifest world block generalized to a source pin
└── cli.py                        —    corpus import-eog / import-appworld / import-tau2

wb_studio/
└── caveats.py                    —    comparability and paid-participant sentences

config/products/
├── enterprise-ops-gym.yaml       NEW
├── appworld.yaml                 NEW
└── tau2.yaml                     NEW

config/plans/
├── eog-smoke.yaml                NEW  one runnable plan per world
├── appworld-smoke.yaml           NEW
└── tau2-smoke.yaml               NEW

tests/
├── test_world_adapter.py         NEW  the protocol, against all four implementations
├── test_worlds_enterprise_ops.py NEW  recorded fixtures, offline
├── test_worlds_appworld.py       NEW
├── test_worlds_tau2.py           NEW
├── test_external_grading.py      NEW  both halves, disagreement, ungraded-on-error
├── test_external_import.py       NEW  refusals, hashes, manifests
└── fixtures/external/            NEW  recorded rows, databases and checker outputs
```

**Structure Decision**: the existing single-project layout is kept. External sources get
their own top-level package `wb_worlds/`, one subpackage each, rather than being folded
into `wb_world/`. The reason is the licence boundary as much as tidiness: each source's
legal note, importer and adapter sit together, and `wb_worlds/appworld/` is the only
place that knows AppWorld content must never be written into the repository. Shared
machinery stays in `wb_world/` where it already lives.

## Phase sequence

Phase 0 and Phase 1 are complete; the artifacts are listed above. Execution order is set
in `tasks.md` and follows the spec's story priorities, with two constraints that come
from research rather than from preference:

1. **The three spikes gate the adapters they belong to** ([research.md](research.md)
   S1–S3). S1 in particular can return a finding that makes EnterpriseOps-Gym
   unsuitable; it runs before the work it gates, not after.
2. **The seam lands before any adapter.** The protocol, the registry, the grading path
   and the shim change are one slice, verified against the existing AutomationBench
   implementation, which must keep passing the whole suite unchanged. A seam that breaks
   the working product is a worse outcome than three missing products.

## Complexity Tracking

No constitution violations. Table intentionally empty.
