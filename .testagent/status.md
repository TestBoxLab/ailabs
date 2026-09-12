# Studio validation status

Relevant regression set:125passed9.86s. Gateway25 tests and app23tests included, plusbudget/evidence/CLIregressions. Initial newexecutionclaimtest expectedone completed attempt butfixturehas two runners; expectation corrected to two andrerunpassed.

Requirements mapped to test_studio_app.py: test_scripted_comparison_retains_real_verdicts_tool_nodes_and_verified_evidence; test_fake_api_control_streams_tool_output_and_final_text_with_usage; test_sse_reconnect_replays_only_events_after_cursor; test_execution_claim_prevents_second_dispatch; test_production_uses_one_ledger_even_with_custom_output; test_http_rejects_foreign_origin_host_and_missing_session_before_mutation; test_static_allowlist_never_exposes_secrets_or_evidence.

Gateway exacttests in test_studio_paid.py cover admission, maxima, unknownholds, usageincludingthinking, IDreplay, rateexpiry andsanitized HTTPdiagnostics. Reviewedpaidintegrationfindings fixed: function IDs, canonicalledger, admissionvsunknownbilling andthinkingcounts. Focused assertions exercise effects rather than implementation presence.

UI independentreview defects fixed; browser script confirms focusRetained,truncationDisclosed,staleOutputCleared,errors[],overflowfalse. Full native execution and successful realpaidgeneration remain blocked by runtime/credentials, not claimedtested.


## Feature 027 report validation — 2026-09-11

176 relevant checks passed in 41.48s. Exact command and requirement matrix:
specs/027-genesis-report-authoring/validation.md. Reviewed assertions cover saved
publication contents, absence after rejected/stale work, exact attempt identities,
100% partitions, batch coverage, call counts/forbidden calls, lossless paging,
ledger balances/unknown charges and read-only historical preservation. Independent
review findings were fixed and checked. Browser run/round checks pass at 1440 light,
390 light and 1440 dark, with zero overflow/errors. No live paid-model semantics
or full repository-suite claim.
