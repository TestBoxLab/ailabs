# Workflow builder prototype testing

Use the existing Monarch competitor with optional `builder_experiment` in its harness YAML: `current`, `compiled`, `sections-serial`, `sections-parallel`, or `sections-parallel-current`. This selection changes the frozen configuration hash. Leaving it unset preserves the existing request body, stream behavior, and hashes.

An explicit selection uses the persisted authoring status endpoint, checks that the server selected the requested experiment, and records raw snapshots and cursor event pages in the attempt log. It waits for `complete: true`, which means the server's terminal state and final event writes are durable. Expired history remains an explicit HTTP 410 failure, including its original response; it never becomes an empty successful export. Existing server payload truncation markers stay visible. Prototype failures retain raw failure fields and are not classified from provider names in prose.

`MonarchClient.cancel_execution(run_id)` uses `/api/engine/runs/:id/cancel` and the existing session header. Prototype execution timeouts call it before cleanup. Authoring cancellation continues using its existing route. A failed cancellation is recorded and requires checking that no paid work remains active.

## Reserve the campaign budget before calls

`CampaignBudget(path)` creates a local SQLite ledger with atomic reservations across processes. Its ceiling is $1,000 across the campaign, including at most $200 of development work. An ordinary measured attempt reserves $12. All concurrent in-flight reservations count against the ceilings. Values are rounded upward to integer millionths of a dollar.

1. Use one ledger path for every development call and measured attempt in the campaign.
2. Call `reserve(stable_attempt_id, 'measured')`, or `reserve(stable_call_id, 'development', amount_usd)` before development work.
3. Dispatch paid work only when the returned `created` field is true. A repeated reservation ID returns false and never authorizes another dispatch; inspect/recover the prior attempt instead.
4. Reconcile once with the complete actual provider cost using `reconcile(id, actual_usd)`. Repeating the same final cost is harmless; changing an already reconciled cost is refused. Retries that make additional paid calls need distinct reservation IDs. Each charge belongs to exactly one reservation; do not also reconcile child calls separately when an attempt total includes them.
5. If cost cannot be established, call `reconcile(id, None)`. Its reserved liability remains charged and every later reservation is blocked until known cost replaces the unknown. Any actual cost exceeding its reservation is recorded honestly and also blocks later work for review.

The helper does not dispatch calls, meter a provider, or cancel a running request. The campaign runner must enforce per-attempt runtime/model limits, reconcile exceptions and crashes, and wait for cancellation to settle before reporting final usage. A reservation alone cannot guarantee that an external call stays within its allocated amount. Existing benchmark grading, task freezes, and report eligibility are unchanged. No campaign is started by these additions.
