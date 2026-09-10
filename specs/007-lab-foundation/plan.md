# Foundation implementation plan

Current step: validating ledger, evidence integrity and dependency candidate; native execution and billing integration remain pending.
Trello: https://trello.com/b/ntJfbkLx/ai-labs-research-experiments

## Order of work

1. Reproduce untouched main with its pinned upstream dependency. Save baseline
   results. Compare the repaired ApplicationBench dependency separately; freeze
   the selected revision with migration evidence before changing scored tasks.
2. Implement private evaluator storage and isolated native harness adapters.
   Unsafe host execution has been removed; ClaudeCodeArm refuses launch until
   an independently verified isolated runtime is available.
3. Implement shared weekly spend reservations and reconciliation. Existing
   orchestrator.py checks the ceiling after completed attempts; account for
   concurrent in-flight costs, retries and paid analysis before enabling runs.
4. Normalize traces and artifact manifests, including events on timeout,
   interrupted streams and tool errors. Existing EpisodeRow provides a useful
   summary but is not a complete trajectory contract.
5. Add the one-off Monarch adapter and explicit two-track comparison. Verify
   Monarch release and API contract. Preserve native model harness behavior.
6. Audit corpus executability and grading; define reproducible difficulty and
   held-out task splits. Do not infer validity from no-op checks alone.
7. Build report interaction around real stored evidence: overview, comparison,
   task traces, state diffs and linked findings. Use calibrated semantic analysis
   where deterministic checks are insufficient.
8. Connect the experiment runner to the ledger and Trello. Add controlled
   replications and combination experiments; promote conclusions only after
   held-out checks. Keep research automation useful before paid execution exists.

## Reuse

Retain the world server, results store, grader separation, configuration hashes,
report metric functions and useful existing tests. Reconcile stale documentation
rather than rewriting the benchmark wholesale.

## Validation

Offline unit/integration suite; oracle and no-action/near-miss checks; seeded
world-reset checks; adversarial harness isolation; replay from recorded artifacts;
concurrent budget/interrupt/resume tests; comparison denominator checks; visual
verification of charts and drilldowns at desktop and mobile widths.

Paid pilot follows those checks and reserves a bounded portion of the weekly
budget. A large run is not evidence that the plumbing is valid.

## Delivery status

Atomic budget reservations and durable attempt evidence are implemented. The
repaired dependency passes validation in a separate candidate copy. Native
Codex execution, native isolation, provider-enforced budget/billing integration,
new difficulty classes and visual reporting remain implementation work.
See [implementation evidence](implementation.md).
