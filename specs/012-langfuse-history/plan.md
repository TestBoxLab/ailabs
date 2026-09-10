# Implementation plan

1. Preserve and commit the already-verified upstream-integrity corrections;
   integrate current main. Diagnose the actual failed GitHub job before changing
   anything. Correct only the missing test dependencies and faulty test setup.
2. Add one small stdlib Langfuse OTLP exporter with a durable SQLite outbox,
   immutable receipt/state identities, allowlisted attributes and durable
   delivery. Record financial state in the same transaction as ledger changes;
   perform HTTP after commit, outside the spending lock. Automatic export when
   configured; explicit status/flush/backfill/reconcile commands for recovery.
   Claim delivery before POST. Retry definitive rejections only; confirm
   ambiguous sends through read-side lookup to avoid v4 cost duplication.
3. Reuse the shared reservation paths to record dispatch/outcome/usage for API,
   native, Studio paid/preparation/analysis/Genesis and Monarch calls. Add thin
   attempt summary hooks at CLI and Studio's final evidence boundaries. Preserve
   original Monarch generation ownership; exported links carry no duplicate cost.
4. Run focused offline tests, then the full suite detached and the exact CI
   corpus checks. Verify a real telemetry-only record without any model request.
   Inspect coverage and independent review before committing and pushing.

Constitution check: unchanged methodology, world, requests and assertions; no
paid experiment; existing scientific evidence retained. Stdlib and existing
SQLite ownership avoid a separate service/dependency. Source-specific traces
make the two storage locations visible without inventing a shared ledger.

Sources checked 10 September:
- https://langfuse.com/integrations/native/opentelemetry
- https://langfuse.com/docs/observability/features/token-and-cost-tracking
- https://langfuse.com/docs/api-and-data-platform/features/public-api
- https://langfuse.com/integrations/native/opentelemetry/migration-to-v4

The old ingestion API is being retired; use /api/public/otel/v1/traces with
application/json and x-langfuse-ingestion-version: 4. Usage buckets are disjoint;
explicit known cost takes precedence over Langfuse-inferred pricing.
