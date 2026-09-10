# Studio operational follow-ups

Requested by Carlos on 10 September 2026. This is a backlog, not a claim that
these capabilities already exist. Preserve AutomationBench inputs and historical
results. Current incident: run `f2799405-f9b3-4fb2-8e41-a517e9c39260`.

## Resume interrupted runs from the UI

- Connect the existing CLI continuation to the Studio job lifecycle and live
  results. Preserve the run ID, original configuration bytes, completed attempts,
  evidence, retry policy and cumulative spending.
- Reconcile interrupted requests before retrying them; retain unknown charges
  and partial observations. Never represent an observed snapshot as final.
- Make continuation an explicit, idempotent action with remaining work and cost
  shown before dispatch. Verify recovery after an actual process termination.
- The current incident is being handled operationally; that does not constitute
  a general-purpose Resume feature in the UI.

## Pause configured benchmark runs

- Stop admitting new attempts and allow active attempts to finish. Display
  Pausing and Paused accurately, then continue without replaying completed work.
- Keep cancellation distinct from pause, including Monarch authoring and workflow
  execution. Ordinary Studio runs already have pause controls; repository plans
  currently refuse pause.

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

## Complete UI metrics and billing visibility

- Expose all retained attempt metrics and an Excel-compatible export from the UI,
  including timing, actions, tokens, retries and authoring/execution costs.
- Connect configured-plan activity events: the Results count and run status can
  update while Activity still says it is waiting for the first task. Do not infer
  execution inactivity from that panel until its event mapping is implemented.
- Show known spending separately from unresolved charges and reserved capacity.
- Verify Langfuse delivery for interrupted work as well as completed attempts;
  summary telemetry must not duplicate generation costs.

Related backlog: [WorkflowBench deferred work](../workflowbench/deferred.md).
