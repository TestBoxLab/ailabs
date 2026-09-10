# Studio refactor offline verification

Date: 2026-09-08 (America/Sao_Paulo).

## Full Studio validation

Working directory: `C:\Users\Lucas Wakigawa\Documents\AILabs\monarch-benchmark\workflowbench`.

Exact PowerShell command executed:

```powershell
$studioTestFiles = @(Get-ChildItem tests/test_studio*.py | ForEach-Object { $_.FullName })
& .venv/Scripts/python.exe -m pytest @studioTestFiles tests/test_runtime_registry.py -q --tb=short
```

Observed final summary: **392 passed in 54.44s**. Process exit code: **0**.

This is a summary of the observed tool output, not a reconstructed raw pytest log. The full run used offline fixtures and fake providers; no paid calls were made.

## What the checks verify

- Studio lifecycle: execution claims, cancellation before execution, recovery of unclaimed queued work, and interruption of claimed work without replay.
- Runtime admission: shared agent/provider concurrency, cancellation, deadline expiry without dispatch, requests-per-minute boundaries, gateway budget arguments, and process ownership locks.
- Components: installed role selection, immutable identifiers, whole-source-module SHA-256 pins, unavailable or changed pins, and a metadata-only catalog.
- Saved workflows: artifact recording before action dispatch, dependency ordering and references, read-only authoring, invalid-plan rejection, error telemetry, cancellation, and timeout.
- Leaderboard: comparable task/track/judge cohorts, separate implementation/configuration groups, complete task coverage per arm, operational failure denominators, unknown costs, ties, and preservation of source run records.
- Architecture publication and runtime registry: legacy Monarch nodes rejected before publication, legacy execution diagnostics retained, and readiness/capability/manifest evidence preserved for supported definitions.
- Monarch Enterprise reference: explicit `create-and-run` track, verification prerequisites, fake builder/execution telemetry, reservations and cost reconciliation, and checkout drift rejection.

## Relationship to earlier artifacts

The existing `tests.log` and `tests.xml` in this directory record the initial run with **19 failed, 373 passed**. Those failures came from intentionally changed contracts. Tests were updated to verify the new contracts, after which the full command above passed. The initial raw artifacts have been retained unchanged for history and are superseded by this observed passing summary.

After the full 392-test run, the parent agent reported an additional targeted run of `tests/test_studio_architectures.py`: **7 passed**, following a track-manifest correction. That follow-up result is parent-reported; its exact command and duration were not provided here. The full 392-test suite was not rerun after that subsequent correction.
