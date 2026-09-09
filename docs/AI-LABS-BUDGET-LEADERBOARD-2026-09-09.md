# Budget and visual leaderboard

Budget owns shared weekly spending. Repeated capacity widgets were removed; per-action limits and over-budget errors remain.

Daily token/cost stacks support model and period filters and date-to-run drilldowns. Cached input is counted once. Scripted fixtures are excluded. Mixed architecture totals remain unattributed. Charts cover task attempts; the shared ledger also includes research, preparation and analysis.

The leaderboard combines leading observed setups, success intervals and a cost-per-attempt versus success plot. Chart selections open evidence. Green/red deltas require a selected native Bare result. Historical records remain provisional. Run history has readable configuration summaries and a JSON download.

Reference: https://github.com/junhoyeo/tokscale — model/time organization adapted to the existing light design; no code or telemetry integration.

## Verification

| Requirement | Evidence |
| --- | --- |
| Cached input and calendar dates | test_tokens_count_cached_input_once_and_use_sao_paulo_day |
| Missing usage remains unknown | test_missing_usage_and_unknown_billing_are_not_zero |
| Bound model attribution | test_comparison_uses_bound_model_instead_of_architecture_name |
| Unattributed usage | test_unattributed_enterprise_usage_does_not_invent_a_model |
| Offline checks | 42 passed: pytest tests/test_studio_usage.py tests/test_studio_leaderboard.py -q |
| Browser interactions | artifacts/studio-refactor/analytics-check.cjs: model/period filters, chart drilldowns, readable history, desktop/mobile overflow and page errors |

Computer use initialization failed in the Windows sandbox. Automated Chrome provided screenshots and interaction verification. Corrected CSP-blocked chart styles, overlapping date ticks and mobile filter widths. No paid runs were launched.

## Full-benchmark ranking and per-model chart correction

Public ranking now requires a server-recorded catalog-50 benchmark manifest,
matching frozen task hashes, completed run status, and exactly one result for
every task/setup pair. A completed pilot is not a full benchmark. Client-supplied
eligibility fields are ignored. The worker cannot alter the benchmark manifest.
Historic records are preserved, not retroactively rewritten to qualify.

The architecture selector uses architecture names only. Budget now uses one
vertical bar per model for the selected period, with a separate color legend
beneath each chart. Selecting a bar opens a compact run table, not large buttons.
Mixed model usage remains labelled where per-model evidence is unavailable.

| Requirement | Evidence |
| --- | --- |
| Full benchmark enters, pilot stays out | test_public_leaderboard_excludes_single_task_pilot_and_accepts_full_benchmark |
| Partial/cancelled/duplicate/changed/unpinned runs rejected | test_public_leaderboard_rejects_incomplete_or_changed_benchmark |
| Server owns eligibility | test_server_pins_full_reference_and_does_not_accept_client_eligibility |
| Regression checks | 50 passed across test_studio_benchmark_pins.py, test_studio_usage.py, test_studio_leaderboard.py |
| Rendered interactions | model-bars-check.cjs: two legends, bar per model, compact table, mobile fit, no pilot scores |
