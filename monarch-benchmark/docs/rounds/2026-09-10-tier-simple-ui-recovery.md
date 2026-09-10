# Tier-simple: hosted launch and operational continuation

Status at 21:49 UTC: **running**, not a completed benchmark report.
Operator and continuation authorization: Carlos, 10 September 2026.

## Identity and original launch

- Run: `f2799405-f9b3-4fb2-8e41-a517e9c39260`.
- UI: <https://ailabs-studio-production.up.railway.app/#run/f2799405-f9b3-4fb2-8e41-a517e9c39260>.
- Launched through the hosted UI at 21:02:05 UTC; execution runs on Railway.
- Original full `tier-simple`: 10 tasks, seven competitors, one retry on failure.
  The launch disclosure was 70–140 attempts and USD 20–60; original ceiling USD 60.
- Config repository `TestBoxLab/ailabls-benchmark-config`, commit
  `cecb7e4f8291e02a43082fe8d67e9420b07347f4`, semantic hash `a3dbc30fc6d376b1`.
- Read-only source file `/data/studio/config-inputs/tier-simple-20260910.json`;
  SHA-256 `0d027fe8286ee9dc41ed7ac578bb88a1a7c26e28048468eb72e115ec3dbf5df1`.
- Original Studio deployment `a5b9b049-b126-4e45-8081-cb2ba52740ac`.
- Monarch build `monarch@0cf63a74e+feat/railway-dev-deploy*`.
- AutomationBench upstream `1.0.6`, source commit
  `4a8e1061254004d9dac807054eed33fad7d1ff14`. No tasks, seeds, routes or assertions changed.

## Interruption and retained observations

Railway lists replacement deployment `e558979f-dac0-44cd-965f-29186d03baf4`,
created 21:15:59 UTC with `cliCaller=claude_code`. The Studio marked this run
interrupted at 21:18 UTC. Carlos subsequently coordinated no further restarts.
The replacement omitted configured-plan support and installed
`automation-bench==1.0.6+evalrepair.10`. The world-version guard refused the first
read-only recovery preflight; the guard was not disabled.

There were 90 completed rows and USD 12.38083721 recorded before recovery. The
first Monarch attempt completed with one world change but failed the task. The
scripted reference failed all 20 attempts: its pilot implementation does not
cover these tasks' assertion types. These results remain unchanged.

Four Monarch journals had no committed result. Reconciliation evidence is in
the run's `recovery/` directory, including backend records, the complete Langfuse
trace listing for the relevant time window, detailed invoice observations, and
the frozen price table.

| Interrupted task | Reconciled USD | Evidence |
|---|---:|---|
| finance.invoice_reconciliation | 2.623683 | Backend authoring `4814c7f5-a03f-4780-beda-df0c64966028` ended `done` at 21:19:56 UTC; 28 generations in Langfuse trace `258b075f7bda3d73328e7cd9579cb23d`, priced with the original table. No benchmark execution result survived. |
| finance.audit_sample_selection | 0 | Reserved before acquiring the Monarch lock; no durable authoring row, tagged Monarch trace, front-door call or tool event. |
| marketing.featured_snippet | 0 | Same evidence of waiting before dispatch. |
| marketing.industry_event_tracking | 0 | Same evidence of waiting before dispatch. |

All four original reservations were settled using that evidence. This reconciles
these interruptions, **not the entire week's historical billing**. Existing
unrelated holds and historical verification status were preserved.

## Continuation

Carlos authorized operational continuation, with general UI Resume/Pause work
deferred to [the follow-up backlog](../STUDIO-FOLLOW-UPS.md).

The existing orchestrator continues the same SQLite run using a separate evidence
generation. A reviewed receipt binds the four uncommitted journals to their
hashes and settled reservations. They are recorded as ungraded infrastructure
interruptions before the normal infrastructure retry replaces their temporary
rows. Their original files and interruption records remain retained separately.
New request IDs have the `#recovery-1` suffix so no old dispatch can be reused.
Prior costs and tokens carry into the replacement rows.

The runner is isolated at
`/data/recovery-source-427ab78/monarch-benchmark/workflowbench`, using original
sources at `427ab78` plus the tested operational helper and upstream world 1.0.6.
The job's `recovery/execution-source.json` records the helper's exact hash.
No service restart or simulator replacement in the UI process was needed.

Preflight disclosed **10–19 remaining attempts, all Monarch**, estimated USD
25–45. Reconciled prior spending is approximately USD 15.00452; a shared-ledger
envelope reserves only the remaining USD 44.99548 from the original ceiling.
The continuation may stop before exhausting task retries if that envelope cannot
cover a further attempt's reservation. Unknown charges retain their holds.

Continuation began **21:47:52 UTC (18:47 São Paulo)**. At 21:49 UTC the job was
running with 94 rows: 90 completed originals and four documented interruptions.
New Drive API calls returned HTTP 200 through the hosted front door. The original
90 rows and all four interrupted evidence trees were verified byte-identical.

## Verification and access

- All six Monarch readiness checks passed, including front door and knowledge base.
- Recovery test first failed because the helper was absent, then passed on a real
  simulator interruption. A separate failing test verified the remaining-ceiling
  guard before it was added.
- Relevant recovery/retry/configuration/paid-dispatch checks: 47 passed. Recovery
  and shared-envelope checks after the added ceiling guard: 25 passed.
- Browser verified `running`, 94 Results entries and USD 15.00. The configured
  Results refresh asset from `427ab78` was restored without restarting the service.
  Activity's ordinary-run event mapping is still incomplete; use Results and the
  retained logs for this run.
- At 21:52 UTC the Langfuse delivery queues acknowledged all 1,300 billing/state
  records for this run (including four new recovery dispatch records) and all 94
  result summaries. This is delivery acknowledgement, not provider invoice
  reconciliation; ongoing calls have not yet settled.
- A detached local observer reads status every ten seconds, inspects front-door
  progress, periodically downloads consistent SQLite snapshots and exports all
  retained fields as CSV. It never dispatches model work.
- Local output: `monarch-benchmark/workflowbench/out/tier-simple-ui-20260910/`.
  `before-resume/` preserves the original interrupted export; current files are
  `attempts.csv`, `checks.csv`, `attempts.json`, and `results-live.sqlite3`.
  On termination the observer downloads the full evidence archive and final DB.
- Temporary Railway SSH key fingerprint:
  `SHA256:oOcCRXemhZ1lRn4hgVy8Fmbsp5jNyC6Ab+2Dp176+PQ`. Retain while the observer
  exports; remove this task-specific key after the final export is verified.
