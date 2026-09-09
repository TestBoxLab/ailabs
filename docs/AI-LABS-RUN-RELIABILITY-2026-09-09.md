# Run reliability and comparison audit — 9 September 2026

## Changes

A parallel attempt could fail while the coordinator waited for an earlier, slower future. The failure now cancels sibling admission immediately inside the failing attempt; completion is consumed in completion order. Already dispatched requests remain subject to their provider timeouts and cancellation support, and their billing liabilities are retained.

Execution now refuses terminal records even when an execution marker is absent. The exclusive marker remains the guard against concurrent execution of the same queued record.

## Acceptance evidence

| Requirement | Evidence |
|---|---|
| Failure promptly stops siblings | `test_parallel_failure_cancels_slow_sibling_before_it_finishes` |
| Terminal results never replay | `test_terminal_run_without_claim_is_never_replayed` (completed, failed, cancelled, interrupted) |
| Duplicate requests do not dispatch twice | `test_duplicate_request_id_returns_original_without_dispatch_or_events` |
| Shared provider capacity | `test_provider_concurrency_is_shared_but_other_providers_can_progress` |
| No dispatch from cancelled provider waiters | `test_cancelled_provider_waiter_never_dispatches` |
| Recovery retains unknown billing | `test_local_restart_releases_unused_capacity_but_retains_dispatched_unknowns` |
| Partial or changed benchmark cannot rank | `test_public_leaderboard_rejects_incomplete_or_changed_benchmark` |
| Different evaluation contracts stay separate | `test_different_evaluation_contracts_never_share_a_cohort` |
| Full benchmark eligibility is server-derived | `test_server_pins_full_reference_and_does_not_accept_client_eligibility` |

The focused resilience, worker, runtime, leaderboard, benchmark pin, runner pin and comparison suite passed: 172 tests. New regressions use a forbidden provider factory and temporary data; they do not mutate historical runs or spend money.

Chrome acceptance (`artifacts/genesis-check/final-browser-check.cjs`) passed: navigation Back, direct run URL reload, saved architecture model selection, no JavaScript errors, responsive layout and persistent streaming DOM. Streaming animation assertions use explicitly synthetic events; historical workstreams were visually inspected. Native computer-use initialization failed due to the Windows sandbox ACL error, so real Chrome automation supplied rendered evidence.

## Scientific interpretation and limits

Public ranking requires all 50 frozen tasks for every setup. Task hashes, evaluation track, judge, assistance and world contract partition cohorts. Configuration and implementation changes create distinct entries. API controls are not native Bare. Green/red comparisons require a matching model and thinking baseline. Missing billing stays unavailable rather than zero; infrastructure issues remain visible and count against operational completion.

These checks establish tested software behavior, not flawless external providers or statistically proven superiority. Repeated attempts on the same tasks are dependent; the UI's attempt-level Wilson intervals are descriptive and must not be treated as independent-trial significance. Provider model aliases can change upstream despite recorded model identifiers. Historical Bare coverage is informational, and automatic reuse remains disabled pending complete identity verification.

Live cross-provider acceptance remains pending as documented in AI-LABS-GENESIS-IMPLEMENTATION.md. Earlier automatic approval review rejected further paid routing checks; none were retried in this audit. Existing unknown billing was not released. No paid experiments were launched.


## Final validation

- 172 tests passed in the focused resilience, worker, runtime, leaderboard, benchmark pin, runner pin and comparison suites.
- 221 tests passed in Studio app, paid execution, node execution, outcomes, native runtime, token quotas and shared budget suites. A stale native-runtime test expected a one-task pilot in public rankings; it now checks classification with `rank_records` and separately asserts public exclusion.
- Total: 393 targeted passing checks. The slower repository-wide sweep was stopped before completion and is not reported as passing.
- The idle preview was restarted to load the runtime fix; no active runs or Genesis turns were interrupted.

Commands (from `monarch-benchmark/workflowbench`):

```powershell
.venv/Scripts/python.exe -m pytest tests/test_studio_resilience.py tests/test_studio_workers.py tests/test_studio_runtime_controls.py tests/test_studio_leaderboard.py tests/test_studio_benchmark_pins.py tests/test_studio_runner_pins.py tests/test_studio_comparison_modes.py -q
.venv/Scripts/python.exe -m pytest tests/test_studio_app.py tests/test_studio_paid.py tests/test_studio_execution.py tests/test_studio_outcomes.py tests/test_studio_native_runtime.py tests/test_studio_token_limits.py tests/test_budget.py tests/test_budget_runs.py -q
```
