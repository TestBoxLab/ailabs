# WorkflowBench execution and cost history in Langfuse

Created: 2026-09-10. Status: Accepted for implementation by Carlos's request.
Branch: ailabs/collateral-judge. This feature supplements PR #3.

## Outcome and scope

Carlos wants every WorkflowBench activity represented in Langfuse so cost history
is available there, including CLI controls, native competitors, Studio workflows,
preparation, analysis and Genesis. Existing Monarch generations already live in
Langfuse; preserve them and link their WorkflowBench accounting without charging
them twice. This changes observability, not grading, tasks or budget policy.

## User stories and acceptance

1. See each dispatched paid request with its scope, model/provider when known,
   timestamps, outcome, token receipt when available and measured cost. Failed,
   interrupted and missing-receipt requests retain unknown billing, never zero.
2. See attempt completion and its evidence identity, including keyless attempts,
   without exporting host secrets, prompts, answer keys or world snapshots.
3. An unavailable Langfuse service cannot change a verdict, lose a paid receipt,
   release a reservation or trigger another model request. Durable pending exports
   survive restart. Definitively rejected exports can be retried; ambiguous
   delivery is reconciled by reading Langfuse, never blindly re-posted. V4 does
   not reliably deduplicate ingestion, so immutable billing spans send once.
4. The same configured Langfuse project receives local and hosted activity.
   Their source identities remain distinguishable. This does not merge ledgers
   or certify provider invoices; reservations remain separate from actual spend.

## Constraints

Use the supported OTLP HTTP/JSON endpoint and the existing Langfuse credentials.
No additional SDK is needed for the bounded metadata/usage export. Store pending
records durably next to existing evidence using SQLite, with atomic financial
recording. Send only allowlisted identifiers, numeric usage and safe outcomes.
Existing Monarch costs belong to the original generations; accounting summaries
must not be duplicate billable generations. Tests use a local fake receiver and
no provider keys. One real zero-cost telemetry delivery may verify connectivity.

All upstream benchmark data stays unchanged. Historical backfill is explicit,
idempotent and based on stored evidence, never fabricated generations or guesses.
Unknown historical scope/model/token details remain absent. Publication of the
PR is authorized; paid experiments and a main-branch merge are not needed here.

## Success criteria

Offline tests cover the dispatch paths above, unknown/zero distinctions, receipt
normalization, concurrent updates, restart/retry, partial receiver rejection,
secret exclusion and Monarch deduplication. The PR's Ubuntu CI passes on the
combined branch; the CI performs tests and corpus validation, no deployment.
