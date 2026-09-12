# Readable report UI release

Carlos authorized a hosted preview, followed by a PR to `main` and a merge
after his browser acceptance, passing checks and a conflict-free merge.
No benchmark attempts or paid analysis are part of this release.

## Source and deployment scope

The feature commit is `d02a350` on `ailabs/report-template`, based on
`aa53ffb`, followed by presentation fixes `122be23` and `f94d043`.
The hosted service already contained additional unpublished changes.
Uploading this worktree directly would have removed those changes.

The deployment tree therefore starts with captured hosted source, with only
the report feature integrated. The first captured deployment was
`351a703d-195f-455e-a58b-fcf495058449`. During preparation another session
published `daa9e553-acbc-46b5-85bf-e55e0e1c663f`; its three changed files
(`genesis-orb.js`, `genesis-orb.css`, `genesis-voice.cjs`) were retained exactly.
That newer deployment is the rollback baseline.

The integration preserves Genesis, performance analysis, task-version
liveness, the break-even curve, and the current single report view. Existing
lab-build export restrictions also apply to the three new download routes.
Downloads always use public-safe redaction. The hosted source is not identical
to the feature commit; this release must not be reproduced by uploading the
older Git worktree over production.

The captured runtime uses AutomationBench `1.0.6` and Codex `0.154.0`.
The deployment retains the captured vendor and pins that installed Codex
version in the reconstructed Dockerfile. No task requests, seeds, assertions,
world routes, service variables or stored results are intentionally changed.

## Verification

- The integrated report retains 106 recorded attempts and USD 51.06925921
  for run `f2799405-f9b3-4fb2-8e41-a517e9c39260`.
- Monarch retains 3/10 tasks solved initially, 4/10 including retries, and
  USD 41.357219 recorded cost.
- Six HTTP checks cover all three attachment routes: lab reports return 403;
  eligible reports return downloadable attachments with public redaction.
- Browser checks cover the readable report, retained Genesis and performance
  details, populated break-even curves, lab export restrictions, standalone
  HTML parity and a narrow viewport without page overflow.
- Deployment-specific review found and corrected two additional regressions:
  historical excluded attempts entering comparable failure buckets, and
  ungraded outcomes being labeled infrastructure failures. Both checks failed
  before the correction and passed afterward. Original result-index mappings
  remain intact; task states now distinguish ungraded, missing and infrastructure.
- The full offline feature test run finished in 37m 02s: **2,315 passed,
  5 skipped, 3 failed**. The three failures were static-policy checks for
  embedded guide styles/colors and `!important` print rules. Those defects
  were corrected; the affected static-policy, guide and download group then
  passed **16/16**. The full run was not repeated after these scoped fixes.
- The guide template was moved outside the served static directory. A browser
  regression also reproduced the note's blocked inline font styling. The
  shared stylesheet now gives both the note and explanatory prose 16px text.
- Printed HTML retains the measurement definitions with the disclosure closed;
  normalized PDF text extraction confirmed the definitions and Wilson limits.

## Hosted result

Final deployment: `c822b12d-d7a0-44d8-b0ea-995776424331`, Railway **SUCCESS**,
`monarch-dev / production / ailabs-studio`.
The [verification receipt](2026-09-11-readable-report-ui-verification.json)
records file hashes, attachment checks, source provenance and unchanged data.
The temporary deployment inspection key was revoked and its local files removed.

[Open the report](https://ailabs-studio-production.up.railway.app/#report/f2799405-f9b3-4fb2-8e41-a517e9c39260).
The intermediate deployment `c1409559-6919-4f3d-9ccb-ea78f58d31d4` supplied
the retained large-download verification; the final release changes only
presentation and the guide template location relative to that deployment.

Final runtime verification matched all **2,942** expected application files,
with no mismatches or extra files. The upload manifest, including the two
build files outside the runtime application tree, has SHA256
`27ff84fbb34aa1933882cac4b8abdd44b7eb1dce3f1cc4e2d02fceae26f6b4db`.
The run's `job.json`, `results.sqlite3` and `events.jsonl` remained byte-identical.

Hosted browser checks confirmed 16px note/body typography, unchanged Monarch
metrics, three download links, a working relocated guide endpoint, and a
380px document inside a 390px viewport. Standalone HTML retains the displayed
metrics and embedded styles without dead Studio controls.

The downloads contain **16,530 log records**, **662 prompts** and **10,118
prompt-to-log references**. All references resolve to the same attempt, task,
competitor and trial. The guide contains ten frozen task definitions and 106
retained attempt results; task hashes, assertions, allowed changes, observed
checks and verdicts match the retained source. Its final endpoint returned
HTTP 200 with the same 192,026-byte attachment after the template move.

The run's previous editorial authoring state remains interrupted. The UI
discloses pending interpretation; this deployment does not run paid analysis
or replace that state with invented diagnoses.

## Integration gate

The PR workflow runs Python tests and corpus validation on Ubuntu. It does
not deploy infrastructure. The separate manual smoke workflow spends money
and is not part of this release's checks.

Hosted deployment and agent verification are complete. Carlos's browser
acceptance remains pending; no push, PR or merge has been performed for this
feature release yet.
