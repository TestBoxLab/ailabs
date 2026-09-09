# Run creation and runtime completion — September 8, 2026

## Run creation

The previous launcher exposed overlapping implementation choices: architecture,
Bare/direct toggle, model/harness, saved runner, and every reasoning variant.
The replacement presents concrete setups once. It uses the existing light visual
identity and a dedicated workspace instead of a scrolling modal.

- Tasks: choose a compatible frozen set or the deterministic, category-balanced
  50-task catalog sample; individual task browsing stays available.
- Setups: add a model or published architecture. Each selected model has one
  reasoning dropdown. Duplicate configurations are rejected; different reasoning
  settings can be added explicitly.
- Review: task count × setup count, exact setup identities, maximum spend and
  concurrency. Component versions and instruction overrides are advanced settings.
- Save for later stores the draft in the current browser; the draft restores after
  reload. This is not a shared server draft or a queued run.

Chrome interaction checks exercised duplicate rejection, backward navigation,
mobile layout, draft reload and a 50-task/two-setup request. The submit request was
intercepted: no paid job was created. Captures and result JSON are under
`artifacts/studio-refactor/launcher-*`. The initial mobile footer overlap was fixed.
The Impeccable detector ran in degraded regex mode; its zero findings do not prove
computed contrast or full accessibility compliance.

## Runtime work

The shared ledger now reserves a complete run envelope before dispatch. Per-request
reservations draw from that envelope without double counting. Closing a run releases
unused capacity while retaining uncertain request costs. Cross-ledger and rollover
verification: 75 tests passed.

Remote-worker and native-container integration verification is in progress. Do not
interpret the new modules as evidence that Docker or Monarch deployment is working.

## Final launcher verification

The live preview was restarted with the project virtual environment and the
canonical shared weekly ledger (STUDIO_LEDGER_PATH), rather than the preview
ledger. Fresh Chrome checks passed for duplicate prevention, navigation, draft
restoration and an intercepted 50-task/two-setup submission. Desktop and mobile
screenshots were inspected; no paid run was created.

The final focused suite passed 118 tests, covering outcomes, coordinator workers,
workflow controls and leaderboard cohorts. Workflow controls now require a saved
artifact and its execution; the pinned workflow contract participates in cohort
identity and cannot be changed by a worker. Paid analysis also uses token admission.

The preview runs in local execution mode. Native acceptance and the complete
Monarch deployment/activation path remain unfinished; unavailable setups must
remain disabled until their actual verification succeeds. The launcher changes
do not imply production multi-tenant isolation or high availability.

## Architecture-first correction

The current flow is Setup & models → Tasks → Review. Choose one published
architecture, then model/thinking configurations. Every experimental agent node
uses the chosen model for that competitor. Each override has a distinct immutable
execution identity; the published source remains unchanged. Monarch retains its
own configuration and does not accept this experimental model substitution.

The optional Bare toggle schedules native harness attempts with matching model
and thinking. Missing native runtimes block this option rather than substituting
API controls. Historical coverage checks task hashes, model, thinking, track and
recorded native identity. It warns about missing task/model results. This is a
coverage check, not automatic evidence reuse; selecting Bare schedules fresh runs.

New workflow architectures end at Result Output. The runtime records and executes
the workflow there. Legacy published workflow nodes remain executable for history,
but new publication requires removal of the obsolete intermediate node.

| Requirement | Evidence |
| --- | --- |
| Per-model architecture binding and immutable source | `test_comparison_freezes_each_model_without_mutating_published_graph` |
| Roles and connections preserved | `test_binding_changes_every_agent_but_preserves_roles_and_edges` |
| Fixed workflow result executes its artifact | `test_workflow_result_output_saves_and_executes_without_workflow_node` |
| Exact task/model/thinking coverage | `test_bare_coverage_requires_matching_task_model_and_thinking` |
| Offline checks | `pytest tests/test_studio_execution.py tests/test_studio_blueprints.py tests/test_studio_comparison_modes.py -q`: 65 passed |
| Browser journey | `artifacts/studio-refactor/setup-models-check.cjs`: passed, paid POST intercepted |
| Workflow canvas | `artifacts/studio-refactor/workflow-output-check.cjs`: fixed output, no execution node |
