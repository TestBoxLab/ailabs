# Genesis report upgrade validation

Date: 2026-09-11. Local implementation; no deployment or live model-quality claim.

## Acceptance evidence

| User requirement | Exact evidence |
|---|---|
| "concise opening, full analysis below" | tests/browser/report-authoring.cjs verifies the reviewed opening, complete attempt details and visible limitations at desktop/narrow widths; test_long_analysis_pages_shrink_without_crediting_unreturned_attempts verifies readable complete analysis pages. |
| "complete and fill the analysis properly with a subagent of his own, then review, fix and publish" | test_real_genesis_loop_publishes_with_bounded_receipts_and_restricted_tools (2 and 106 attempts); test_reviewer_revision_is_fixed_and_reviewed_again; test_missing_attempt_blocks_authoring. |
| "Needs deeper commentary as to why Monarch is winning or losing, clearly with proven data" | test_foreign_attempt_citation_is_rejected; test_analysis_tampering_invalidates_the_review_digest; test_snapshot_access_reads_exact_before_after_values_and_not_foreign_files; test_report_capture_isolates_repetitions_without_opening_mutable_store. Editorial depth is a reviewed model obligation, not something these fixtures prove semantically. |
| "clear error buckets, the error patterns in vertical slices of %" | test_percentage_columns_use_each_setups_all_attempts_and_round_to_one_hundred; test_checker_partition_includes_both_failure_types_normal_finish_infra_and_unknown; test_domain_slices_use_domain_denominators_and_preserve_liveness_and_inputs; browser keyboard drilldowns. |
| "Genesis should be fully aware" | test_report_procedures_are_injected_into_native_worker_prompts; test_report_contains_the_same_narrative_and_authoring_state_as_studio; test_workers_receive_the_same_computed_chart_slices. |
| "Use inspirations from skills like … humanizer … and structured writing, reporting, graph presentation" | Versioned report_procedures/editorial.md and figures.md, alongside analysis/author/review procedures. test_real_genesis_loop_publishes_with_bounded_receipts_and_restricted_tools checks injection into the real native prompts. |

Readable long records: test_long_analysis_pages_shrink_without_crediting_unreturned_attempts
and test_oversized_attempt_pages_losslessly_and_requires_every_fragment prove
that returned pages retain evidence and do not credit an unread fragment.

## Final offline command

From monarch-benchmark/workflowbench:

```powershell
uv run python -m pytest tests/test_genesis_reports.py tests/test_genesis_report_loop.py tests/test_report_state.py tests/test_report_budget.py tests/test_report_recovery.py tests/test_report_patterns.py tests/test_genesis_loop.py tests/test_genesis_tools.py tests/test_genesis_pause.py tests/test_genesis_allowance.py tests/test_genesis_reviewer.py tests/test_studio_reports.py tests/test_report_lab_gate.py tests/test_narrative.py tests/test_static_csp.py tests/test_reasoning_review_retry.py tests/test_studio_outcomes.py -q
```

Result: **176 passed in 41.48s**, exit 0. The native 106-attempt fixture uses 14
analysis turns, then author and reviewer, with real budget-ledger receipts and
restricted tools; provider responses are deterministic doubles. No provider
request or benchmark round was sent. The full repository suite was not run by
this task.

Scoped git diff --check passed. Existing unrelated shared-checkout changes were
preserved, including active feature 026 in .specify/feature.json.

## Browser acceptance

tests/browser/report-authoring-server.py provides stored scripted-run fixtures;
tests/browser/report-authoring.cjs inserts explicitly synthetic publication text
into the report API response. It checks 1440px light, 390px light and 1440px dark:
run and round pages; authored opening; legacy suppression; full analysis and
limitations; keyboard selection; exact counts and event references; safe text
rendering; read-only refresh. All passed with zero page errors and zero overflow.
Root also visually inspected desktop and narrow chart screenshots.

Artifacts under workflowbench/.tmp/report-authoring-browser:
- evidence.json
- desktop.png, desktop-patterns.png, desktop-round.png
- narrow.png, narrow-patterns.png, narrow-round.png
- dark.png, dark-patterns.png, dark-round.png

The synthetic browser publication is injected after the fixture API computes
its caveats, so screenshots may retain an old no-model-analysis caveat. Production
publication/work precedence is separately covered by narrative_status regressions.

## Review findings fixed

- Every saved result, including success/infra/unknown, must be analyzed.
- Event reads, attempt citations and complete analysis reads are checked.
- Snapshot reads are frozen and confined to the run; missing state is explicit.
- Repetitions use their own completion-bounded trace; no mutable Store read.
- Native tools are restricted by report role and assigned run/batch.
- Large analysis is split into fresh contexts (up to 8 attempts or 100k source
  characters per batch; a larger single attempt uses lossless packet pages).
- All stage envelopes are reserved before dispatch; underfunded stage startup
  is refused before any reservation. The displayed amount is a startup floor,
  not an estimate or guarantee of completing the report.
- Review binds the exact evidence, draft and full attempt analysis hashes;
  only one repair/re-review is allowed and prior publications are preserved.
- Startup-only reconciliation handles missing turns and lost completion
  callbacks, enabling explicit retry while retaining unknown charges.
- Synthesis/attempt/review sizes are bounded so draft pages remain readable.
  Page size shrinks without marking omitted analyses as read.
- Genesis tools and UI share the published prose and computed chart values.

## Limits and next evidence

Live prose quality, causal correctness and cost to complete a real report remain
unmeasured. The reviewer supplies a retained model judgment, not human proof.
Instructions separate observed behavior, grader outcomes, causal hypotheses and
controlled findings. Missing evidence cannot be repaired by fluent prose.

The existing automatic ceiling is not raised. A larger report on an expensive
route may be refused until its configured allowance is sufficient; full reading
costs more than merely admitting the first request. No task, simulator, grader,
frozen record or historical analysis was changed by this report feature.
