# Configured run controls: implementation and deployment

Carlos approved implementation on September 11, 2026. Scope and acceptance:
[specification](../../../specs/013-benchmark-config-repository/operational-follow-ups/spec.md).

## Delivered

- Configured runs now use Pause to stop new admissions and drain active attempts.
  Pause survives restart; cancellation remains terminal.
- Resume shows required work separately from possible retries, known spending,
  unresolved charges, reserved capacity and the remaining original ceiling.
  Dispatch rechecks this preview and preserves the run ID and frozen inputs.
- An OS ownership lock prevents simultaneous continuation. Execution segments
  retain prior observations; process death never automatically authorizes paid
  recovery. Unknown billing and unfinished paid work require reconciliation.
- Activity consumes historical configured `result` events and Inspect opens
  retained evidence. Activity still groups by task and competitor: the historical
  tier-simple run shows 70/70 groups, while Results retains all 106 attempts.
  Per-repetition presentation remains in the metrics backlog.

Implementation reuses the orchestrator, SQLite results store, budget ledger,
configuration repository client and existing UI controls. No new dependency,
worker service, task rewrite, result regrade or billing adjustment was introduced.

## Evidence

All benchmark execution during verification was offline and free.

| Check | Observed result |
|---|---|
| Expanded Python regressions | 234 passed; one recovery-script compatibility failure reproduced and corrected |
| Recovery script, reports and configured controls after correction | 18 passed |
| Final configured controls, safety and billing regressions | 15 passed |
| Orchestrator, retry, paid admission, evidence, world and config checks | 147 passed |
| Isolated upload tree integration | 114 passed; missing migration helper added, four follow-up checks passed |
| Real browser pause/drain/resume, repeated after final changes | Four attempts, two segments, zero cost; results match uninterrupted control |
| Browser editor checks | Desktop and 390px layout; validation, conflict and network-error draft retention passed with offline Git responses |
| Hosted source verification | All 19 selected source hashes match the reviewed upload tree |
| Historical data verification | All 28 recorded job/event/result files across 12 jobs remain byte-identical |

The process-termination test exits a real worker with code 73, reopens Studio,
requests continuation concurrently and checks finalized rows and retained raw
evidence. Additional checks cover cross-process ownership, cancellation races,
read-only preview, stale configuration, permission enforcement, precision and
unknown billing. Test groups overlap; their counts are not additive.

The hosted check exposed a configuration-version refusal incorrectly returned as
HTTP 500. A failing HTTP test reproduced it; the preview now catches the existing
configuration error and returns `resumable=false` with its reason. The world
guard itself remains unchanged.

Runnable checks from `monarch-benchmark/workflowbench`:

```powershell
uv run python -m pytest tests/test_configured_controls.py tests/test_configured_control_safety.py tests/test_configured_billing.py tests/test_orchestrator_controls.py tests/test_operational_resume.py -q
uv run python tests/browser/server.py --port 8779 --configured-controls
# In another terminal:
$env:BROWSER_PORT='8779'
node tests/browser/configured-controls.cjs
```

Graphify refreshed 19 changed source files using AST extraction only: 17,420
nodes, 42,015 edges, 1,144 communities; historical semantic nodes retained.
No provider calls or benchmark dependency changes. The complete 27-minute test
set was not rerun; validation was scoped to changed execution and UI paths.

## Hosted deployment

Service: `monarch-dev / production / ailabs-studio`.
Final deployment: `2f14a3ee-c5a0-429f-a6c5-88a52a1a0560`, Railway status SUCCESS.
Initial controls deployment: `7af486a9-3a7d-407b-9187-e52105377ec8`.
Previous deployment: `cafadef9-7a17-492a-a534-a92b0d0ad070`.

The upload was assembled from a source copy verified against all 2,526 hosted
files, then integrated with the 19 required feature/control files. This preserved
the already hosted report, SSE, HTTP and provider fixes that the feature branch
did not yet contain. `railway up --detach --no-gitignore` uploaded that reviewed
tree; it did not deploy from GitHub. Active-work checks before both uploads found
no queued, running, pausing or cancelling jobs. Runtime variables and the data
volume were preserved. No Monarch service was deployed.

Hosted browser and API checks confirmed:

- Settings displays 41 configuration files, frozen commit
  `cecb7e4f8291e02a43082fe8d67e9420b07347f4`, read-only editor and disabled Save.
- Run `f2799405-f9b3-4fb2-8e41-a517e9c39260` remains Completed with 106 results
  and USD 51.06925921. Terminal controls are hidden.
- Its report still shows Monarch 4/17 passed, 13 failed and USD 41.36; no task
  matrix cell incorrectly says Not evaluated. Activity and Inspect work after
  the retained event stream loads.
- Recovery preview returns HTTP 200 with an explicit world-version refusal.
  No run was launched by these hosted checks.

## Remaining external prerequisites

Git activation remains incomplete: the configured PAT authenticates, but GitHub
returns 404 for the repository and main ref. The integration is now deployed;
`WB_CONFIG_SNAPSHOT` remains active and read-only until restricted repository
access is verified. See [activation record](../../../specs/013-benchmark-config-repository/operational-follow-ups/git-activation.md).

The pre-existing hosted world is `1.0.6+evalrepair.10`; the frozen tier-simple
configuration requires upstream `1.0.6`. This deployment preserved the vendor
bytes and did not adopt or modify the alternative dataset. Version refusals remain
effective; restoring the matching upstream runtime is required before another
tier-simple launch. Historical results continue to carry their original world.

Evidence files and hash inventories are retained locally under temporary
`wb-config-controls-deploy-232hgfxt` and `wb-controls-read-j8wd0cx4` directories;
no credentials are stored in this record. Changes were committed locally at the
deployment checkpoint.

## Publication and current-main integration

Carlos subsequently requested push and a pull request. Integrated `main` at
`0d7a127` before publication. Resolved the two workspace conflicts by preserving
main's simplified Runs table and retaining the configured recovery dialog styles.
No additional service deployment accompanied this integration.

The integrated regression group finished with 131 passing tests and one stale
test assertion already present in main: it required an Actions column that main
had removed. Removed that obsolete assertion; all nine run-page tests then passed.
The real browser continuation journey again completed four free attempts in two
segments with unchanged finalized results. Editor journeys passed on desktop and
at 390px, including conflict handling, draft retention and pinned launch preview.

The PR workflow runs Python tests and corpus validation on Ubuntu, using pinned
upstream AutomationBench `4a8e106`. It contains no infrastructure deployment step.
