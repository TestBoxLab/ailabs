# Blueprint, difficulty and runner regression matrix

Bounded extension of the repository test plan. Owned files: tests/test_studio_blueprints.py and this record. No production edits. All default baseline resolution and catalog pages use local mocks; no GitHub, provider or paid calls occur.

| Requirement | Exact test |
|---|---|
| Draft CAS and caller mutation isolation | test_draft_compare_and_swap_prevents_lost_edits_and_copies_graph |
| Immutable versions, fingerprint and idempotent publication | test_publish_is_idempotent_and_versions_are_immutable |
| Published Monarch baseline pin; draft unchanged | test_monarch_publication_pins_verified_baseline_without_mutating_draft |
| Unverifiable baseline leaves no partial version | test_unverifiable_monarch_baseline_cannot_publish_partial_version |
| Disconnected draft allowed, strict publication refused | test_disconnected_draft_is_allowed_but_cannot_publish |
| Cycle rejection | test_cycle_cannot_be_saved_even_as_draft |
| Enrichment field declaration and upstream dependency | test_enrichment_requires_an_upstream_declared_field |
| Invalid DAG node/edge configuration | test_strict_graph_rejects_invalid_node_or_edge_contract |
| Difficulty hash matching and exclusions; unrated output | test_difficulty_excludes_mismatched_hash_scripted_infra_and_incomplete_evidence |
| Difficulty thresholds, provisional boundary and uncertainty | test_difficulty_thresholds_and_uncertainty_are_explicit |
| Complete paginated multi-account Fireworks list and cache | test_fireworks_paginates_public_and_account_catalogs_deduplicates_and_caches |
| Repeated cursor or transport failure returns no partial catalog | test_fireworks_failure_never_returns_or_caches_partial_models |
| No network without credentials | test_unconfigured_fireworks_catalog_never_opens_network |
| Runner identity and effort configuration | test_runner_profiles_preserve_provider_model_and_effort_without_claiming_execution |
| Invalid runner configuration rejected | test_invalid_runner_profiles_are_rejected |

Validation: `uv run --project monarch-benchmark/workflowbench --frozen python -m pytest monarch-benchmark/workflowbench/tests/test_studio_blueprints.py -q` — 32 passed in 0.39s.

Assertions verify persisted versions byte for byte, deterministic graph fingerprint, stale revision failure, exact baseline resolver calls, exact catalog cursors/results, no partial files, numerical difficulty boundaries and confidence interval bounds. No confirmed production defect was found in these requested paths.
