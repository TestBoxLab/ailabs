# PG-Waki v1: provenance of the reconstructed product knowledge

Recorded 8 September 2026 (unblock plan, M6 T6.1). Status: **reconstructed**. This version
descends from the knowledge lineage behind Lucas's best Monarch result, but it is not the
file that result consumed. It must never be presented as "the 67 % artifact".

## The result it descends from

| Item | Value |
|---|---|
| Arm | `matrix-v912-opus-max` (Monarch v9.12, runtime mode `monarch-graph-inline-v6`) |
| Model and effort | claude-opus-5, max |
| Score | 403 / 600 = 67.2 % strict; paired against bare Opus 5 max (348 / 600 = 58.0 %): wins 60, losses 32, McNemar p = 0.0046, bootstrap +4.67 points (1.5 to 7.7) |
| Suite | AutomationBench 1.0.6+evalrepair.10, 600 scored tasks, `suiteRevisionId afd2e0b2afc6dc7e…` |
| Cost | US$ 337.84 |
| Date | 26 August 2026 |
| Record | `C:/Users/Lucas Wakigawa/Monarch_Main/_recovery/transcripts/C--Users-Lucas-Wakigawa-MonarchBench/dd07c78f-92b5-4c62-b354-d9c969241c86.jsonl` (tool result at 2026-08-26T18:31:28Z) |
| Implementation revision | `atlas-monarch-v8-1-p0-runtime-record-opus5-graph-inline-v8-evalrepair10-port-v6` |

What is gone: the run store `MonarchBench/.automationbench-runs/matrix-v912-*` and the graph
bytes it loaded. The `MonarchBench` workspace was deleted; only recovered source and transcripts
survive under `Monarch_Main/_recovery/`.

## The artifact this version is built from

| Item | Value |
|---|---|
| File | `C:/Users/Lucas Wakigawa/Monarch_Main/ATLAS/backend/config/bridge-v8-zapier-hard50-reviewed-capabilities-enriched-4a8e106-v2.json` |
| Size | 2,234,630 bytes |
| sha256 | `7aea3d995c260edba3a84457f4cd634fd9c8c5e30f5bd6bebd52f0927a6c487d` |
| Schema | version 1; generator `automationbench-zapier-hard50-reviewed-capabilities-v1`; frozen hash `11a73896100c2973…` |
| Content | 273 entries (`source_action_id` + reviewed `contract`), 43 product contexts, carried review notes, policy |
| Role in the lineage | the `canonical_catalog` every graph-inline v6 and v8 run configuration names (`ATLAS/backend/config/bench-corpus-parity-106-*.json`, `runtime_files.canonical_catalog`); verified by sha256 against `preflight_pins` in `bench-episode-worker.py` before each run |

Companion material, same folder tree:

- `ATLAS/backend/data/bench/product-graph-corpus-v1/manifest.json` (53,243 bytes, sha256
  `c18ee4bfa534f76de92723ec9e188d7caf23c6ce2ee6977dabdc61f2036004c9`) plus `graphs/` with 47
  product graphs: 755 routes, 1,143 request parameters, 139 capability documents.
- `ATLAS/backend/scripts/fixtures/postgres-seeds/atlas-product-graphs.seed.json.gz` (the ATLAS
  Postgres seed, 1,071,564 bytes, sha256 `0b726138756e1516…`).
- The v9.12 route into Feature Discovery: `_recovery/MonarchBench/monarch/feature-discovery/api/src/seeds/fixtures/monarchbench-vendor-contracts.json`
  (4,921 bytes, sha256 `d73814b9e2aaf147…`) with `monarchbench-seed-coverage.ts`.

## What the reconstruction does and does not carry

The catalog carries reviewed action semantics: purpose, non-effects, idempotency, where the
response records live, argument and value semantics, and product contexts with cross-product
relationships. It does not carry the v9.12 runtime behaviours (declared work list, write gates,
reconciliation, retrieval implementation and index), which lived in ATLAS code. A lab Monarch
instance seeded from this file is therefore "Monarch Enterprise with reconstructed reviewed
knowledge", compared as a new version. Each later change to the knowledge is a new version
folder here, with its own hash and the rounds that used it.

## Next step (M6 T6.3)

Generate lab seeds for the 47 bench products whose action descriptions come from this catalog,
ship them as fixtures of the lab instance's Feature Discovery, import by slug, grant to the lab
organisation, and pin the seed hashes into the lab competitor's knowledge file.
