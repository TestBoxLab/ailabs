# Studio run controls and configuration integration

Date: 2026-09-10. Status: draft for Carlos's review; no feature implementation authorized by this document.

The three requested items are resume, pause, and finishing the configuration
repository connection after PAT approval. Deployment coordination supports the
first two; the remaining metrics backlog stays separate.

## Options

| Approach | Benefit | Cost / limitation |
|---|---|---|
| Extend the existing Studio controls and CLI continuation (recommended) | Same run, evidence and spending history; reuses the current execution path | Requires durable admission control and recovery after a process dies |
| Keep manual recovery scripts | No new application work | Operator-dependent, fragile after deployments, no reliable UI action |
| Move execution to an independent worker service now | UI deployments do not kill execution | More infrastructure; still needs the same recovery and billing rules |

## Proposed behavior

- **Resume:** show the remaining required attempts, conditional retries, known
  spending, unresolved charges and remaining ceiling; resume the original frozen
  run only after readiness and billing checks. Repeated clicks cannot dispatch twice.
- **Pause:** stop admitting work, let active attempts finish, then show Paused.
  Continue uses the same recovery path. Cancel remains a separate terminal action.
- **Configuration repository:** finish feature 013 rather than build another
  editor. Verify the PAT, switch new previews from the temporary snapshot to Git,
  and keep existing runs pinned. Saves continue directly to `main` with conflicts
  checked; changing configuration does not launch a benchmark.

Implement resume, then pause; finish the Git connection independently when the
credential is approved. Reuse the existing process and stores initially. Before
deployment, inspect active work and drain it; a crash still requires recovery.

## Data decision

Declarative YAML is configuration, SQLite is execution history, and snapshots /
JSONL are evidence. Feature 013 explicitly excludes results, ledger and Studio
architecture artifacts from its migration. Keep these until a verified migration
exists. Delete only verified duplicates or reproducible temporary output; never
infer obsolescence from a `.json` or `.sqlite3` extension.

See [acceptance specification](spec.md), the [existing configuration spec](../spec.md),
and [operational backlog](../../../monarch-benchmark/docs/STUDIO-FOLLOW-UPS.md).
