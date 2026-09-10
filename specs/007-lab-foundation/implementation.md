# Foundation implementation — 2026-09-08

Work is on branch `007-benchmark-foundations`, based on `88cddf6e172a4c39f0b32fa49eb2e98b8fa8cd28`. This is a tested offline foundation increment; paid benchmarking and the complete reporting product are not ready.

## Budget

`wb_orchestrator/budget.py` provides a SQLite ledger using exact micro-USD arithmetic, atomic admission across processes, immutable reservation identities, single-use dispatch claims and settlement. The default is USD 300 per calendar week beginning Monday 00:00 America/Sao_Paulo, with no rollover. Unknown costs keep their full hold; late settlement and overruns retain liabilities.

A settlement spanning weeks conservatively occupies capacity in every week from dispatch to settlement (reservation to settlement if dispatch is unknown). These weekly capacity figures are not invoice attribution and must not be summed as lifetime paid spend. Historical bills have not been imported.

From `monarch-benchmark/workflowbench`:

```powershell
uv run --frozen wb budget status
```

The canonical local ledger is `research/budget.sqlite3`. Ledger tests use isolated temporary databases. Since milestone M3 (8 September) the CLI's API loop, `wb resume` and the doctor's provider probes reserve through this ledger (see "Paid dispatch" below); Monarch competitors, `wb monarch recipes` and the doctor's Monarch probe stay refused until milestone M5 verifies an instance, native competitors until M7. Calling low-level Python adapters directly is not protected by the CLI gate.

## Paid dispatch

Milestone M3 of the unblock plan (8 September 2026), tasks T3.1 to T3.6. What executes now:

- **One request, one reservation.** `wb_arms/reservations.py` reserves every provider request of the CLI's API loop (`ApiLoopArm` with a ledger) for its rate-card maximum (`wb_studio.gateways.ceiling_cost` over `input_upper_bound` and the adapter's output cap), claims the single right to dispatch, sends, and settles from the usage receipt; an unreadable receipt settles as unknown and keeps the hold, a provider failure or a crash after the claim never settles. Reservation ids are `<episode id>#<attempt-NNN>#r<turn>`, the attempt index being the evidence directory the orchestrator derives from disk, so an infra retry or a resume runs under new ids and never reserves a settled request again. Each reservation's metadata carries `billing_provider` (the model file's provider), the model, the operator and the token ceilings.
- **Attempt cap.** Plan key `attempt_cap_usd` (default US$ 3.00; in the config hash only when set, like `track`): before every request the loop adds the request's maximum to what the attempt already settled or holds across its invocations (the ledger scope is the episode id) and ends the attempt as `infra:attempt_cap` when the sum would pass the cap. Not a pass, not the model's failure; final for resume (`Store.completed_identities`). Monarch attempts reserve `MONARCH_ATTEMPT_CEILING_USD` (default US$ 25.00, now defined in `wb_arms.monarch` and re-imported by the Studio's Enterprise adapter) per attempt and settle from the Langfuse total; a cost that cannot be read keeps the hold and flags `billing=unknown`.
- **Round admission.** `Orchestrator.run` and `resume` compute the maximum liability (API attempts x cap + Monarch attempts x ceiling, capped by what `cost_ceiling_usd` still allows) before the run row exists and raise `RoundAdmissionError` naming the shortfall when the week cannot cover it (exit 2 in the CLI). Nothing is held for the round itself; the per-request reservations enforce during the run. A `BudgetExceeded` under a request ends the attempt as `infra:weekly_budget` and stops the run with `stop_reason: weekly_budget`, resumable when the week has room; resume counts only the attempts left and never resets spend.
- **Reconciliation.** `wb budget reconcile --week --provider --csv` (`wb_orchestrator/reconcile.py`) compares one week's normalized usage rows (`date,provider,usd`; export recipe per provider in `config/README.md`) with the ledger's settled total for that provider (reservations attributed to their dispatch week), writes `research/reconciliation/<week>.md` and `.json`, and marks `historical_billing_verified` for that week only when every provider with spend is within 5 %. `wb budget status` reports the flag per week and the capability matrix.
- **Approvals (decision D5).** `wb_orchestrator/approvals.py`: the launcher is `WB_OPERATOR` (required for any paid launch); approvers default to `lucas` (`WB_APPROVERS` overrides). Above smoke scale an approver's `wb run` runs at once under an approved record in the results store (table `approval_requests`); anyone else's writes a pending request, prints `<id> awaiting approval` and exits 0; `wb approve` / `wb deny` (approvers only), `wb approvals`, `wb run --request <id>` (any operator, config hash must match, single use). `approved_by` in plan files is optional and ignored with a one-line notice; the resolve-time gate is gone.
- **Capability checks** replace the blanket refusal: `approvals.launch_readiness` lets API-loop competitors launch with an operator and the ledger; Monarch competitors, `wb monarch recipes` and `wb doctor --monarch-probe` are refused with `Monarch instance not verified: milestone M5`; `claude-code` and other native competitors with `native runtime not verified: milestone M7`; the doctor's provider probes reserve every request through the ledger.

Exact tests, all offline (mock provider, fake Monarch and Langfuse, temporary ledgers):

- `tests/test_paid_dispatch.py`: `test_api_loop_reserves_claims_and_settles_every_request`, `test_an_unreadable_receipt_settles_as_unknown_and_keeps_the_hold`, `test_a_provider_failure_after_the_claim_keeps_the_hold`, `test_a_crash_inside_the_provider_call_keeps_the_hold`, `test_a_second_invocation_of_the_same_attempt_gets_new_reservation_ids`, `test_attempt_cap_refuses_the_request_before_any_reservation`, `test_attempt_cap_counts_what_the_attempt_already_settled`, `test_attempt_cap_defaults_to_three_dollars_and_moves_the_hash_only_when_set`, `test_attempt_cap_ends_the_attempt_as_infra_and_the_round_goes_on`, `test_weekly_budget_exhausted_mid_run_stops_the_run_and_resume_continues_it`, `test_the_second_round_of_an_oversubscribed_week_is_refused_naming_the_shortfall`, `test_admission_caps_the_liability_by_the_plans_cost_ceiling`, `test_admission_counts_monarch_attempts_at_the_monarch_ceiling`, `test_resume_admits_the_remaining_attempts_only_and_never_resets_spend`, `test_a_monarch_attempt_reserves_the_ceiling_and_settles_from_langfuse`, `test_a_monarch_attempt_whose_cost_cannot_be_read_keeps_the_hold`.
- `tests/test_approvals.py`: `test_an_approver_launch_runs_at_once_under_an_approved_record`, `test_a_non_approver_launch_creates_a_pending_request_and_waits`, `test_approve_then_run_with_the_request`, `test_a_request_whose_config_drifted_is_refused`, `test_deny_and_unknown_and_pending_requests_are_refused`, `test_smoke_scale_runs_without_a_record_but_through_the_ledger`, `test_approved_by_in_the_plan_file_is_ignored_with_a_notice`, `test_resume_of_a_paid_run_needs_the_operator_and_keeps_the_ledger`, `test_a_monarch_competitor_is_refused_with_the_m5_reason`, `test_a_claude_code_competitor_is_refused_with_the_m7_reason`, `test_monarch_recipes_stays_refused_with_the_m5_reason`, `test_the_doctor_monarch_probe_is_refused_with_the_m5_reason`, `test_doctor_probes_need_the_operator_and_reserve_every_request`.
- `tests/test_reconcile.py`: `test_a_provider_within_five_percent_verifies_the_week`, `test_a_difference_above_five_percent_is_recorded_and_leaves_the_week_unverified`, `test_every_provider_with_spend_must_be_reconciled_and_the_week_can_be_finished_later`, `test_unsettled_holds_and_rows_outside_the_week_are_reported_not_counted`.
- `tests/test_budget.py`: `test_reservations_are_readable_with_their_metadata_and_scope`, `test_scope_committed_counts_settled_actuals_and_open_holds`, `test_week_of_uses_the_ledger_calendar`; `tests/test_foundation_cli.py` for the refusals and `wb budget status`.

Not done here: the first paid CLI pilot (T3.7's two tasks x two models, under US$ 1) has not been run; no provider export has been reconciled yet, so no week is verified; the Studio's own launches still reserve per request through `wb_studio.gateways` without the approval record (milestone M4 joins the two front doors).

## Evidence and grading

Each new attempt retains initial/final world snapshots, exact tool arguments and returned values, normalized observable API messages, usage, termination and grading artifacts. Manifests bind episode/contract identity and file hashes; provenance hashes the working grader/world sources and records Python plus installed dependency version. Dependency version alone is not a complete editable-tree identity.

Tool start/completion/error and supplied agent observations are appended and fsynced while execution is running. Atomic snapshots preserve the last observed world. Hard-process-exit tests exercise both mid-tool and after-tool failures. Private reasoning is unavailable, and native message coverage is unavailable until the native adapters exist.

A hard crash can leave incomplete observations, a partial final JSONL line or a finalized attempt without the row/manifest commit. Resume quarantines these files in place: it raises before dispatch and preserves the evidence. Automatic recovery is pending; the last observed snapshot is never represented as a verified final state. Episodes marked evidence_incomplete and episodes with selected regrade revisions also refuse resume, preserving their history until generation-aware recovery exists.

Resume verifies existing evidence before rewriting aggregate artifacts and retains previous costs/tokens. The run phase aggregates invocations; detailed authoring/execution phases describe the latest invocation, with earlier values retained in attempt artifacts. Exhausting the tool-turn budget is an agent error, not normal completion.

Reports and regrading reject manifest corruption and evidence_incomplete attempts. Journal storage failures stop further model requests as nonretryable infrastructure errors while retaining known usage.

Offline regrading writes an immutable revision with complete grading, prior/current verdicts, source provenance and hashes of its snapshots/original artifacts. The row selects a revision by hash; reports validate the selected chain and expose its exact evidence. The original evidence is preserved during regrading. File publication precedes database selection, so interrupted publication can leave an unselected orphan rather than an unsupported verdict. Hashes detect accidental corruption, not deliberate replacement by an attacker with evaluator-storage access. Files and the result database are not one atomic transaction; failures are handled conservatively.

## Native harness boundary

The previous Claude Code adapter exposed full tasks/snapshots through host execution. That path has been removed. The adapter now refuses before reading task data, writing files, inheriting credentials or spawning a process. Strict offline result parsing rejects malformed/non-success exits and marks absent billing as unknown.

This is a verified prohibition, not a working sandbox. Native Codex execution, real Claude Code isolation, credential scoping, network policy and native trace parity remain engineering work. Docker is installed but its daemon was unavailable during setup.

## Dependency candidate

The active pinned AutomationBench dependency and existing task sets remain unchanged. The repaired ApplicationBench candidate changes all 600 initial worlds, 369 assertion sets, 48 prompts and 20 tool lists; therefore it cannot silently inherit historical comparability.

The untouched repaired import had two provenance-hash failures and stale lockfile package metadata. A separate derived candidate repairs four metadata files with eight precise edits; all 607 other source files, including runtime, tasks and tests, are byte-identical. Strict locked installation, locked Ruff and 1,940 tests pass. The unrecoverable original parent raw hash remains explicitly unverified.

See [dependency audit](dependency-audit.md), [candidate validation](candidate-validation.md) and [provenance reconciliation](repair-provenance-reconciliation.json). Adoption still requires a versioned migration decision and integration checks against the selected task corpus.

## Validation

Focused final evidence/CLI/integration checks: **54 passed in 16.93s** using:

```powershell
uv run --frozen python -m pytest tests/test_evidence.py tests/test_evidence_journal.py tests/test_journal_failures.py tests/test_regrade_evidence.py tests/test_foundation_cli.py tests/test_m1.py::test_mock_e2e_full_matrix -q
```

Run from `monarch-benchmark/workflowbench`. Budget tests: **51 passed**; HTML reporting regression: **72 passed, 2 skipped**.

Focused offline checks cover ledger concurrency/rollover, native launch refusal, exact evidence, crash journals, corrupt resume/report rejection, SDK message serialization and cumulative spend. The untouched baseline is recorded separately in [baseline.md](baseline.md). Full integration command: `uv run --frozen python -m pytest tests -q` from `monarch-benchmark/workflowbench`: **832 passed, 3 skipped, 1 failed in 703.64s**. The sole failure was the old three-artifact expectation in `test_mock_e2e_full_matrix`; the new contract contains seven artifacts. That expectation was corrected, and the complete test passed in the final 54-test focused rerun above. No remaining failing case is known.

The full run began before the last journal/regrade fixes landed; those changes and their regressions are covered by the final focused rerun and the 72-pass HTML report regression. This is not represented as a clean full-suite run on the final snapshot. Final collection: **857 tests**. `git diff --check` passed. Final independent review confirmed the partial-usage flags and regraded-resume preservation fixes, with no remaining P1/P2 findings within its scope.

No paid evaluation, provider probe, repository push or Slack post was performed. Graphify was unavailable, so no graph refresh is claimed.

## Next implementation

1. Adopt an explicitly versioned repaired dependency after corpus integration validation.
2. Implement isolated native execution and provider billing/dispatch reconciliation.
3. Verify current Monarch stock one-off API and introduce distinct track contracts.
4. Rank task difficulty, build visual evidence drilldowns and connect duplicate-aware experiment records to the research pipeline.


| Requirement | Evidence |
|---|---|
| USD 300/week reservation foundation | `tests/test_budget.py`: 51 passed; concurrency, single-use claims, unknown holds and rollover |
| Observable traces survive failure | `test_process_exit_preserves_completed_observations_without_final_world`, `test_journal_failure_stops_requests_and_retains_known_usage` |
| Resume cannot erase evidence or spend | `test_resume_keeps_prior_reported_spend_without_double_counting`, `test_resume_does_not_replace_inputs_of_a_selected_regrade` |
| Grader revisions explain changed verdicts | `test_regrade_preserves_original_and_report_selects_hash_bound_revision`, `test_repeated_regrade_retains_and_validates_previous_chain` |
| Native task secrecy before isolation exists | `tests/test_native_sandbox.py` and paid CLI refusal cases |
