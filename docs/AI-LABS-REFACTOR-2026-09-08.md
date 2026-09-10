# AI Labs refactor — September 8, 2026

Implemented locally; not pushed or deployed. Historical task sets and run records
were preserved. Browser verification used an isolated copy of Studio data.

## Product journey

Runs is a searchable, filterable, sortable, expandable history table with pagination
and CSV export. Architecture Studio is directly accessible in the top navigation.
The interface remains light by default with an optional dark technical theme.
Runtime exposes capacities, component versions, API examples, and the separate
Monarch reference setup.

Architectures declare agentic-request or workflow creation-and-execution purpose.
New versions cannot embed Monarch Enterprise as a node. Workflow experiments
produce a validated action DAG before executing it; discovery during authoring is
read-only. Monarch retains its own verified runtime and configuration.

Product graph review separates schema editing from enrichment history. Each field
shows before/after values and retained research logs. Explicit unknown values are
reported as unresolved. Mobile reviews stack both values instead of hiding columns.

Leaderboard comparisons group matching task hashes, track, judge, assistance,
world and execution configuration. Complete task coverage is required; infrastructure
failures remain in the denominator. Historical unpinned results are provisional.
Only an eligible native Bare record enables a signed green/red percentage-point
difference; unmatched evidence remains neutral. No Bare result has been fabricated.

Failure analysis records exclusive observed categories, explicit denominators,
per-task checks and evidence links. These categories are not causal proof. Hypotheses
and experimental confirmation remain separate from observed failures.

## Runtime and APIs

`GET /api/components`, `GET /api/runtime`, `GET /api/jobs`,
`GET /api/jobs/:id/diagnostics`, and `GET /api/leaderboard` expose the same records
used by the UI. Run creation accepts track, concurrency and installed component IDs.
Trusted Python implementations register separately versioned brain, action-builder
and judge roles; source fingerprints are checked during resolution.

The local runtime shares agent/provider concurrency and request-rate admission
across runs. Jobs and events persist; unclaimed queued jobs resume after restart.
Claimed work is interrupted rather than replayed with unknown charges. An OS lock
prevents two Studio processes owning one data directory.

## Boundaries that remain

- This is a single-host worker, not a distributed or tenant-isolated production scheduler.
- Provider admission controls concurrent requests and requests/minute; token-based
  limits and adaptive provider-wide quotas are not implemented.
- Native Codex/Claude Code launches remain blocked by existing isolation/readiness
  requirements. End-to-end reusable native Bare comparisons are therefore not yet available.
- Monarch sync checks GitHub main and preserves commit/lockfile identity records. Updating deployed
  Monarch services is separate and must pass the existing verification checks.
- The experimental workflow executor supports a bounded DAG, not every Monarch
  workflow feature. It does not claim full runtime equivalence.
- Paid experiment launches were not performed. Existing per-request/attempt billing
  controls do not establish a full-run shared reservation before dispatch.
- Automated research/R&D is scheduled; first scheduled execution is unobserved.

## Design and research evidence

See `AI-LABS-UI-RESEARCH-2026-09-08.md`, `../research/synthesis-matrix.csv`,
and `../research/glossary.md`. The reference mix combines Braintrust comparison,
Inspect evidence inspection and React Flow graph interaction. License boundaries
are recorded; no proprietary UI implementation was copied.

Chrome browser automation exercised 13 desktop/mobile views and saved screenshots
under `../artifacts/studio-refactor/`. The confirmation pass reported no page errors
or horizontal page overflow. Native computer-use initialization was blocked by the
Windows sandbox ACL error, so browser automation was used instead. Impeccable's
mechanical detector ran in degraded regex mode because parser dependencies were
unavailable; it cannot certify computed contrast or accessibility.

Offline validation: the Studio and runtime-registry suites passed 392 tests in
54.44 seconds after updating intentional legacy contract expectations. A UI
specialist inspected the final dark report, architecture canvas, provisional
leaderboard and mobile graph diff and found no severe remaining visual defects.

Final runner-freezing change passed 62 focused regression tests in 12.28 seconds
(runner pins, outcomes, execution and comparison modes). Saved API configurations
include effective model/provider/effort, rate-card metadata and a configuration
fingerprint; they are explicitly raw API controls, not native Bare. Stock source
manifest alignment separately passed all 7 architecture tests. These checks
supplement the earlier 392-test suite; counts overlap and are not additive.
