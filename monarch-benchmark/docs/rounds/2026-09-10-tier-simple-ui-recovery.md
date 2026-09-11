# Tier-simple: hosted launch and operational continuation

Final operational status: **completed**, 106 results, September 11 00:45:27 UTC.
All seven remaining Monarch retries finished after the earlier budget refusal.
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

At **21:54:39 UTC**, the first resumed attempt, `finance.audit_sample_selection`,
finished `completed` and **passed**, with six world changes and USD 2.159729 in
additional spend. Its evidence manifest verified without errors. Total recorded
run spending became USD 17.16424921. The invoice task had already started next.
The UI refreshed the existing row and total automatically; the row count remained
94 because the recovered result replaced its temporary interruption record.
The local CSV and SQLite copies were explicitly refreshed after this success.

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

## Terminal accounting and remaining work

At 22:52:18 UTC, `finance.annual_budget_prep` trial 1 was refused before dispatch.
The recovery envelope was USD 44.995480, of which USD 39.020996 was committed at
that instant, leaving USD 5.974484 against a required USD 8 reservation. Three
already-admitted attempts still held capacity: Airtable find/update, email lead,
and calendar product review. The orchestrator stopped admitting work and drained
these attempts, finally ending at 23:16 UTC with 100 result rows and recorded cost
USD 40.39968721. The error incorrectly calls this exhaustion of the shared weekly
budget; inspection confirmed that the run envelope caused the refusal.

The 100 rows comprise 99 executed attempts and one zero-cost budget refusal.
All ten initial Monarch tasks ran; three passed. Seven failed tasks still have
their configured retry pending, including the refused retry. Completing all
seven would yield 106 result rows, because one replaces the refusal row. No new
paid continuation was launched during the subsequent counter investigation.

Final export verification: SQLite integrity check `ok`, 100 rows in the database
and CSV, and 1,882 archive entries including the recovery receipt. One original
GLM request reservation remains unresolved; it was not released or treated as a
verified zero. The display's USD 40.40 is recorded spending, not a declaration
that every provider charge has been reconciled.

## Seven-retry continuation

Carlos requested completion of the seven pending retries. At September 11
00:04:14 UTC (September 10 21:04 Sao Paulo), the same hosted run resumed using
the isolated original runtime and world. Configuration hash remains
`a3dbc30fc6d376b1`; the original USD 60 ceiling is unchanged. The operational
concurrency override is one, avoiding simultaneous reservations for Monarch
work that the backend already serializes.

The shared ledger reserved a new, immutable `#recovery-2` envelope of USD
19.351117: USD 60 minus USD 40.399936 settled and the unresolved original GLM
hold of USD 0.248947. The earlier closed envelope was not reopened. Expected
additional cost was disclosed as USD 15–25; execution remains constrained by
the smaller remaining ceiling and may stop before every retry if needed.

Before dispatch, all 100 evidence manifests were verified and the exact seven
pending identities checked. The 99 final rows are checked for equality during
the continuation. The budget-refused trial receives `attempt-001`, preserving
its refused attempt's files. New request reservations use `#recovery-2` IDs.
The operational receipt and before-state database are under the hosted job's
`recovery-2/`; local exports retain the previous terminal state in
`out/tier-simple-ui-20260910/before-retries/`.

Two operational corrections were reproduced before applying fixes:

- Retry scheduling used row existence, incorrectly skipping an infrastructure
  refusal on a retry trial. It now uses the store's final-identity definition,
  including the existing rule that `infra:attempt_cap` remains final. The real
  simulator regression failed at the missing retry, then passed. Recovery,
  retry and envelope checks: 41 passed.
- Replayed historical `finished` SSE closed a resumed run's live connection.
  The frontend ignores terminal events older than `resumed_at`. The real HTTP
  browser fixture failed before the change and passed afterward; seven static
  CSP checks also passed. The served asset was replaced without a restart.
  Browser inspection confirmed `running`, an open stream, and retained history.

The operational launcher is retained on the host as
`/data/recovery-source-427ab78/monarch-benchmark/workflowbench/scripts/finish_retries.py`,
SHA-256 `7e5bdc799bf10733891a07fe4806b1c477e8a675db7494f6d947f8fd7c33e365`.
The frontend asset SHA-256 is
`76494bc012021a8daf004bf5234dd6c92dacd2d3df56e6431d88a16d80f4e548`.
The detached local observer continues status, call inspection and metric exports.
The first resumed task made two Google Drive GET requests with HTTP 200. This
confirms application access, not a successful task verdict.

### Final verification

The continuation finished at September 11 00:45:27 UTC (September 10 21:45
Sao Paulo). All seven retries executed; no pending retry remains. The hosted UI
updated without reloading to `completed`, 106 results, USD 51.06925921. Additional
recorded spending was USD 10.669572, within the original USD 60 ceiling.

| Retried task | Termination | Passed | Added USD |
|---|---|---|---:|
| finance.annual_budget_prep | completed | No | 2.248709 |
| finance.invoice_reconciliation | agent_error | No | 1.177159 |
| marketing.featured_snippet | completed | No | 1.600151 |
| marketing.industry_event_tracking | completed | No | 1.182546 |
| marketing.product_adoption | completed | No | 1.833166 |
| sales.update_contact_phone | completed | No | 1.933144 |
| simple.airtable_find_update | completed | Yes | 0.694697 |

The successful Airtable retry performed metadata discovery, a Contacts lookup
and `POST /airtable/base_crm/Contacts`, all HTTP 200. The unchanged world's two
judges accepted the final state. This demonstrates a successful write in this
attempt; it does not establish that the ignored formula problem is repaired.
Invoice reconciliation failed at `fetch_invoices`. The other five failed
retries finished normally but did not satisfy the task's complete approval rule.

All 106 evidence manifests verified. The 99 already-final rows match the
before-continuation database exactly. Both remote and exported SQLite integrity
checks returned `ok`; the CSV has 106 rows and 83 columns. The local final archive
has 2,008 entries, including both recovery receipts and the operational source:
SHA-256 `18787051251a2a70d88243ed6afd47b52641a15a113e55761cdc2b9f5287e1cd`.
The observer finished exporting and exited. Local `verification-final.json`
records the checks under `out/tier-simple-ui-20260910/`.

Langfuse acknowledged all 106 result summaries and all 1,312 billing/state
records for the run. The continuation envelope is closed. The original GLM
reservation of USD 0.248947 remains unresolved and retained; delivery to Langfuse
does not by itself reconcile that historical provider charge.
