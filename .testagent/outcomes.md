# Studio outcome regression requirement matrix

Scope: reports.py, setups.py, analysis.py and app.py reasoning configuration only. Existing project .testagent/research.md and plan.md retain the broader test plan. This addendum records the bounded outcomes work; production files were not edited.

| Requirement | Exact test |
|---|---|
| 800 public categorized briefs; evaluator fields omitted | test_complete_public_catalog_has_800_categorized_briefs_without_evaluator_data |
| Frozen configurations and real gateway thinking payload | test_effort_variants_freeze_settings_and_reach_actual_gateway_payload |
| Invalid effort and execution configuration rejected | test_invalid_reasoning_or_execution_settings_never_create_job |
| Immutable distinct drafts; unavailable adapter disclosed | test_setup_drafts_are_distinct_immutable_records_and_honest_about_execution |
| Invalid draft cannot overwrite or launch | test_invalid_setup_cannot_write_an_executable_or_replace_a_draft |
| Infrastructure, scope and actions remain distinct | test_outcome_report_separates_infrastructure_scope_and_observed_actions |
| Analyzer blinds labels, preserves citations, charges shared ledger once | test_analysis_uses_blinded_citations_real_budget_and_single_dispatch |
| Bad schema and citations rejected without retries | test_analysis_rejects_invalid_schema_or_citations_without_retry |
| Exhausted budget prevents generation | test_analysis_does_not_dispatch_when_shared_budget_cannot_admit |
| Incomplete run cannot start analysis | test_analysis_rejects_running_jobs_before_reserving_or_dispatch |
| Interrupted analysis cannot replay | test_interrupted_analysis_claim_is_never_automatically_replayed |

Validation: `uv run --project monarch-benchmark/workflowbench --frozen python -m pytest monarch-benchmark/workflowbench/tests/test_studio_outcomes.py -q` — 25 passed in 1.59s.

All generation and token counting used fake in-process transport, with isolated temporary SQLite ledgers. No provider network calls. Assertion review checks exact outcomes, exact request payloads, nonzero settled costs, retained evidence, and absence of dispatch on failure. One frozen task (simple.partner_hubspot_asana) has an empty initial state and therefore truthfully has no listed applications; the corpus was not changed.
