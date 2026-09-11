# Studio operational follow-ups

Requested by Carlos on 10 September 2026. This is a backlog, not a claim that
these capabilities already exist. Preserve AutomationBench inputs and historical
results. Current incident: run `f2799405-f9b3-4fb2-8e41-a517e9c39260`.

Approved by Carlos on September 11: [short brainstorm](../../specs/013-benchmark-config-repository/operational-follow-ups/brainstorm.md)
and [acceptance specification](../../specs/013-benchmark-config-repository/operational-follow-ups/spec.md).
These cover resume, pause and Git activation after PAT approval. Implementation
and verification are recorded [here](rounds/2026-09-11-studio-run-controls.md).

## Resume interrupted runs from the UI

- Connect the existing CLI continuation to the Studio job lifecycle and live
  results. Preserve the run ID, original configuration bytes, completed attempts,
  evidence, retry policy and cumulative spending.
- Reconcile interrupted requests before retrying them; retain unknown charges
  and partial observations. Never represent an observed snapshot as final.
- Make continuation an explicit, idempotent action with remaining work and cost
  shown before dispatch. Verify recovery after an actual process termination.
- Implemented September 11: configured runs use an explicit recovery preview,
  exclusive execution ownership and immutable configuration restore. Offline
  process-termination and concurrent-resume tests preserve finalized results.
  Unresolved paid requests still require reconciliation before continuation.

## Pause configured benchmark runs

- Stop admitting new attempts and allow active attempts to finish. Display
  Pausing and Paused accurately, then continue without replaying completed work.
- Keep cancellation distinct from pause, including Monarch authoring and workflow
  execution. Implemented September 11 for repository plans as well: active work
  drains; paused state persists; continuation reuses the recovery checks.

## Prevent deployments from interrupting paid work

- Surface active runs before deployment and coordinate a drain or planned stop.
- Record the deployment identity with every execution segment. On 10 September,
  deployment `e558979f-dac0-44cd-965f-29186d03baf4` replaced the active runner.
- Verify the installed world before shipping: that replacement also carried
  `1.0.6+evalrepair.10`, which cannot continue this run frozen on upstream `1.0.6`.
  Operational recovery uses an isolated original runner and world.
- Consider separating persistent execution workers from UI deployments after
  configured-plan worker support is implemented and verified.

## Finish configuration repository integration after PAT approval

- Repository: `TestBoxLab/ailabls-benchmark-config` (intentional spelling).
- Verify `WB_CONFIG_GITHUB_TOKEN` can read and write repository contents. Never
  put its value in this document, logs or commits.
- Restore Git-backed operation from the temporary `WB_CONFIG_SNAPSHOT` mode;
  confirm catalog, validation, direct saves to `main`, commit history, conflicts
  and immutable configuration snapshots on new runs.
- Keep schemas and validation in AI Labs; keep configuration artifacts in the
  configuration repository. Preserve configuration revisions on historical runs.
- Finish browser verification and the remaining feature-013 tasks. Do not remove
  the temporary source or change runtime configuration during an active run.
- September 11: the configured token authenticates, but the repository and main
  ref return HTTP 404. Keep snapshot mode read-only until actual repository
  access is verified. [Activation record](../../specs/013-benchmark-config-repository/operational-follow-ups/git-activation.md).

## Complete UI metrics and billing visibility

- Completed September 10: repaired configured-plan report inputs:
  align configured and versioned competitor identities, load complete stored
  results by episode identity, and use recorded world/version and retry semantics.
  The old tier-simple HTML reported Monarch as unevaluated despite 17 evaluated
  attempts, and named the server's vendor instead of the recorded world.
  Deployed and browser verified; re-export historical HTML to get the corrected
  report. No result or frozen metadata migration was needed.
  [Diagnosis and verification](rounds/2026-09-10-tier-simple-report-diagnosis.md).

- Distinguish a run-envelope refusal from exhaustion of the weekly budget. This
  continuation rejected an USD 8 attempt reservation while only USD 5.974484
  was unreserved and three other attempts still held capacity. It then drained
  those attempts and stopped at USD 40.39968721, below the original USD 60 ceiling.
  The current error incorrectly says the weekly budget was exhausted. Consider
  waiting for in-flight settlements before stopping for temporary reservation
  pressure; never release unknown charges or bypass an actual budget limit.
- Distinguish completed attempts from the maximum allowed attempts. The full
  tier-simple plan permits 140 only if every initial attempt fails and earns a
  retry; successful attempts remove that retry from the actual workload. At
  22:50 UTC, 95 rows were finalized, with 9 required and up to 4 conditional
  attempts remaining. Show the maximum separately, rather than implying that
  `95 / 140` means 45 attempts are still pending or that all runs must reach 140.
- Expose all retained attempt metrics and an Excel-compatible export from the UI,
  including timing, actions, tokens, retries and authoring/execution costs.
- Completed September 11: Activity consumes configured-plan `result` events,
  including retained historical events and continuation segments. Inspect now
  opens the selected task correctly. Detailed per-repetition presentation and
  the wider metrics/export backlog remain separate.
- Show known spending separately from unresolved charges and reserved capacity.
- Verify Langfuse delivery for interrupted work as well as completed attempts;
  summary telemetry must not duplicate generation costs.

Related backlog: [WorkflowBench deferred work](../workflowbench/deferred.md).
