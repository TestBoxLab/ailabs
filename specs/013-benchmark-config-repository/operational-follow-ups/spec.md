# Specification: configured run controls and Git activation

Date: 2026-09-10. Status: approved by Carlos for implementation on 2026-09-11. Parent: [feature 013](../spec.md).
Scope: three follow-ups requested by Carlos; this document does not implement them.

## US1: Resume an interrupted run (P1)

Carlos resumes an interrupted configured run from its Studio page, preserving its
identity, completed results and full costs.

- **FR-01:** offer recovery for an interrupted or recoverable failed run with
  remaining work; completed and explicitly cancelled runs are terminal. A paused
  run continues through the same admission path. Show the reason when blocked.
- **FR-02:** preview required attempts separately from possible conditional
  retries, known costs, unresolved charges, reservations and remaining original
  ceiling before dispatch. Recheck these at dispatch using existing operator,
  approval, run and weekly budget rules. Never increase the frozen ceiling.
- **FR-03:** use the original run ID, configuration bytes/revision, task hashes,
  world and recorded versions. Refuse drift; never replace them with current main.
- **FR-04:** persist exclusive execution ownership. Concurrent clicks or workers
  admit at most one continuation; a stale claim is recoverable only after proving
  the previous worker is no longer active. Reconcile unfinished provider requests
  before retrying; preserve unknown billing and partial observations separately.
- **FR-05:** never replay finalized attempts or omit earned conditional retries.
  Preserve old result rows and append new execution segment identity, events and
  spending. Reuse existing result/Langfuse delivery identities to avoid duplicates.

Acceptance: terminate a real local test worker mid-run using an offline scripted
competitor; restart Studio and resume twice concurrently. Final rows must match an
uninterrupted control, earlier finalized rows remain byte-identical, dispatch is
unique, and UI activity, totals and exports include the continuation. An unresolved
paid request, mismatched world or exhausted ceiling refuses unsafe dispatch.

## US2: Pause a configured run (P1)

- **FR-06:** Pause persists the request and stops new admissions atomically,
  including retries; admitted attempts finish normally. Show Pausing while active
  attempts drain and Paused only when none remain. Do not cancel Monarch phases.
- **FR-07:** pause survives restart. An interrupted active attempt requires US1
  reconciliation before continuation; a restart never clears the pause request.
  Continue is explicit, uses FR-02 through FR-05 and works without replay.
- **FR-08:** Cancel while pausing/paused remains terminal and never resumes work.
  If all work finishes while pausing, show Completed rather than an empty Paused run.

Acceptance: with two offline attempts active and another pending, Pause admits no
further attempt, drains both, survives process restart, then Continue finishes the
pending work exactly once. Also verify retry admission and cancellation races.

## US3: Activate the approved Git configuration source (P2)

- **FR-09:** after external PAT approval, verify restricted read/write access to
  `TestBoxLab/ailabls-benchmark-config` through `WB_CONFIG_GITHUB_TOKEN`. Never expose
  the token to browser responses, logs or commits.
- **FR-10:** complete the existing feature-013 editor/validation/conflict behavior,
  including direct saves to `main`. New previews read a complete Git revision;
  historical runs and previews retain their frozen source bytes and revision.
- **FR-11:** switch off `WB_CONFIG_SNAPSHOT` only with no active work and a verified
  Git catalog. Keep the fallback file for rollback; failures are explicit and never
  silently substitute defaults. Switching sources does not change tasks or seeds.

Acceptance: browser verification of read, edit, validation, diff, save, refresh and
concurrent-edit refusal; verify the resulting commit. CLI and Studio resolve equal
configuration at that commit. A remote update cannot change an existing preview or
run. Token/network failures preserve drafts and clearly report the failure.

## Limits and verification

Use the existing orchestrator, Studio lifecycle, configuration repository client,
results store and spending ledger. No new database, worker service, configuration
schema, automatic paid recovery or automatic deployment system is required.
Record deployment identity per execution segment and require an active-run/drain
check in the deployment procedure. Full deployment prevention is a separate backlog.
Preserve AutomationBench, old verdicts, raw evidence, frozen configuration and
unknown charges. Config migration does not delete `out/wb.sqlite3`, Studio state or
set/architecture creator artifacts. UI metric enhancements remain separate.

Implementation must use failing-first offline tests, then browser checks for the
three journeys. Drafting, saving and verification do not launch paid benchmarks.
Plan and tasks follow review; current implementation touchpoints are
`wb_studio/app.py`, `wb_studio/benchmark_config.py`,
`wb_orchestrator/orchestrator.py` and `wb_orchestrator/config_repository.py`.
