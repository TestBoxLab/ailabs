# Performance projection contract

Add `performance` to GET /api/jobs/<id>/report and permanent run report data.
Computed by `wb_studio.performance.performance_report(job, events)`, entirely
from stored rows/events. Shape:

```
{version: 1, run, order: [model], planned_attempts, recorded_attempts,
 source, setups: {model: {
   id, name, recorded, planned, passed, failed, infrastructure, ungraded,
   success_rate, operational_success_rate,
   timing: {successful: Distribution, failed: Distribution,
            all: Distribution},
   cost: {total, known_subtotal, unknown_attempts, per_success},
   tools: {calls, errors, observed_calls, error_rate},
   turns: {total, observed_attempts},
   collateral: {attempts, changes, complete_attempts, missing_attempts},
   phases: {phase: Distribution},
   attempts: [{task, model, passed, infrastructure, ungraded, seconds, cost_usd,
               tool_calls, termination}]
 }}}
Distribution = {count, missing, median, p90, max, values}
```

Timing uses linear interpolation for quantiles and explicitly recorded seconds;
successful means pass plus normal termination; failure timing excludes infra.
Operational success denominator includes every recorded attempt, including infra.
The separate valid success rate excludes infra and ungraded rows. Both use null when empty.
Cost total and ratio are null if any row is unpriced; known subtotal is labeled
partial. Ratio denominator is successful attempts. Tool errors are only known
from observed terminal tool events; missing telemetry is not a zero error rate.
Deduplicate replayed event IDs. Never pool repeated task/model events into a
fictitious retry success rate. Deferred retry metrics need explicit attempt IDs.

The UI displays literal measured numbers, updates graphs from this member on
each attempt completion, and links samples to the existing attempt inspector.

Ungraded attempts have their own outcome segment. Collateral counts are labeled
as known lower bounds whenever either change-detail field is absent.
