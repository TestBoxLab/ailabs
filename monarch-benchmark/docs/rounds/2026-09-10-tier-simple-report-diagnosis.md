# Tier-simple exported report diagnosis

Run: `f2799405-f9b3-4fb2-8e41-a517e9c39260`.
Input: Carlos's downloaded `report-f2799405-f9b3-4fb2-8e41-a517e9c39260.html`,
compared with the final SQLite export, `job-latest.json` and `evidence.tar.gz`.
This investigation ran offline. No paid attempts, regrading or data edits.

## Confirmed cause of “not evaluated”

The configured competitor ID in `job.settings.models` is `monarch`; all 17
retained Monarch results use `monarch@0cf63a74e+feat/railway-dev-deploy*`.
The configured launch stores competitor names in `wb_studio/benchmark_config.py:124`.
`wb_studio/measures.py:231` groups results by their saved model name, then looks
up the configured name with `groups.get(setup, [])`. This produces an empty list
for Monarch. `wb_studio/report_data.py:251` emits “not evaluated” for that empty
group; `wb_studio/static/charts.js:132` displays the null rate accordingly.

Reproduction: calling `run_measures(job, [])` on the saved job gives Monarch zero
attempts, null rate and zero total cost. In a deep copy only, replacing the
configured `monarch` name with the exact recorded version gives 17 attempts,
four passes and USD 41.357219. No result, grader or task was changed.

| Retained Monarch measurement | Value |
|---|---:|
| Attempts | 17: 10 initial attempts and 7 retries |
| Passed / all attempts | 4 / 17 (23.5%) |
| Failed attempts | 13: 10 normal finishes and 3 execution errors |
| First-attempt success | 3 / 10 tasks (30%) |
| Tasks solved within the configured retry allowance | 4 / 10 (40%) |
| Recorded cost | USD 41.357219 |
| Retained individual assertion checks | 122 |

The three execution errors are invoice reconciliation trials 0 and 1
(`fetch_xero`, `fetch_invoices`) and product adoption trial 0 (`contact_each`).
They have failed verdicts; none of the final 17 rows is an infrastructure refusal.

## Other confirmed report defects

- The HTML shows Monarch USD 0.00 and ten missing planned outcomes. Both follow
  from the identity mismatch. Actual final run size is 106 retained attempts.
- The general report reads the small job result summaries, which omit checks,
  timings, tokens and collateral-change details. Those fields are available in
  SQLite/evidence. `failure_analysis.py:112` assumes the summaries already carry
  them, and does not load SQLite. The HTML consequently classifies all 69 failures
  as insufficient evidence; absence from this report is not absence from storage.
  Missing timing and change fields also produce misleading zeros in `measures.py`.
- The HTML names `1.0.6+evalrepair.10`. All 106 archived evidence manifests record
  `provenance.automation_bench_version = 1.0.6`. `caveats.py:15` reads the report
  server's installed vendor, rather than the run's recorded provenance.
- The HTML says two repetitions per task and 106 recorded of 70 planned.
  `measures.py:231` counts planned task/competitor pairs without retry semantics
  and derives repetition count from observed groups. The frozen plan specifies
  one initial attempt plus one retry on failure, not two mandatory repetitions.
- “Not comparable” is a separate report-grade limitation: this template expects
  a Bare baseline. The frozen plan instead names `claude-opus-5/api` as baseline.
  The template's message does not mean the attempts were never evaluated.

Correct the shared report input adapter to preserve versioned competitor identity,
load full evidence by episode identity (including trial), and read provenance and
retry semantics from the frozen run. Existing HTML exports are static and must
be generated again after the reporting correction. No benchmark rerun is needed.

## Correction deployed and verified

Carlos authorized the application correction, including database adjustments if
needed. No historical database adjustment was needed: `report_inputs.py` reads
SQLite with `mode=ro`, projects full results into the Studio response, and keeps
each saved episode identity and versioned competitor. It loads recorded checks,
scope verdicts, tokens and timestamps, and reads world/grading provenance from
the saved manifests. The frozen configuration supplies the baseline and retry
allowance. The shared `Studio.job` read path serves both report endpoints.

The regression first failed because the configured name hid real simulator
outcomes. It then passed with distinct failed initial and successful retry rows,
including checks, cost, time, world version and unchanged database/job hashes.
The related report, measure, failure-analysis, configuration, collateral and CSP
checks finished with 63 passed.

Deployment `cafadef9-7a17-492a-a534-a92b0d0ad070` succeeded on `ailabs-studio`.
The upload was an isolated copy of the running service with only the reviewed
report patch applied. No task data, vendor source or configuration artifact was
changed. There were no active runs; before-state copies are retained under this
job's `report-fix-backup/` on the persistent volume.

Verified on the hosted report and its HTML export:

- Monarch: 4 / 17 passed, USD 41.357219, median recorded duration 544.148176 s.
- All 106 results counted; 37 passed and 69 failed. No missing outcomes.
- Failure categories: 44 scope failures, 25 unmet requirements, zero unclassified.
  These are evaluator outcome categories, not proven causes.
- World: AutomationBench 1.0.6; recorded grading source fingerprint present.
- One initial attempt plus up to one retry on failure; configured Claude baseline.
- No “not evaluated” or `evalrepair` label in the corrected exported HTML.
- All 106 stored result rows and the frozen job JSON match the before-state copy
  exactly; database integrity check returned `ok` after deployment.

Carlos's original downloaded HTML was preserved. The corrected file is
`Downloads/report-f2799405-f9b3-4fb2-8e41-a517e9c39260-corrected.html`, generated
through the hosted page's export function. The automation download command was
cancelled/timed out, so its generated HTML Blob was captured and saved locally.
Screenshots are in `out/tier-simple-ui-20260910/report-fixed*.png`.

Remaining limitations: model interpretation is still pending; a report is not a
provider invoice reconciliation. The original USD 0.248947 GLM hold remains
unresolved as documented in the run record. This correction does not recover
trajectory fields that were never recorded or change historical verdicts.
