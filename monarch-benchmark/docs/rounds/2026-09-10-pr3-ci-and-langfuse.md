# PR #3 integration, CI and Langfuse history

Carlos explicitly authorized correcting, committing and pushing the CI fixes,
and requested WorkflowBench activity and spending history in Langfuse. This does
not authorize changing upstream benchmark data or merging main automatically.

## Remote and CI findings

PR #3 is `ailabs/collateral-judge`; PR #1 remains a separate draft with conflicts.
Remote main through `290852f` was merged locally without conflicts as `6fabaee`.
The earlier governance, approval-rule and pricing corrections are commit `713d46c`.

The `.github/workflows/ci.yml` job runs on Ubuntu with Python 3.13. It clones
the pinned upstream AutomationBench revision, syncs the frozen dependency lock,
runs `pytest tests -q`, then validates the pilot tasks and imported simple corpus.
It deploys no infrastructure and makes no paid model calls. Pull-request
synchronize events trigger it after a push; the old comment saying otherwise
was corrected.

Run `34494819813` failed with 13 failures, 2,035 passes and five skips. Four
installed-Codex acceptance tests tried to launch an absent executable; eight
socket-release assertions treated POSIX TIME_WAIT as a leaked server; one Studio
work-now test left the real credential-dependent route check unmocked. Changes
in `7d60d32` make the installed-CLI requirement explicit, reuse the existing
port-release helper with POSIX address reuse, and provide an available route in
the Studio fixture. Product gates remain intact. Focused CI reproduction checks
passed before that commit was pushed; run `34508574017` tests that revision.

## Langfuse implementation

Feature specification: `specs/012-langfuse-history/`. Ledger transitions and
attempt summaries atomically queue metadata-only OTLP records. Dispatch paths
add canonical usage and outcomes; unknown billing retains its hold. A previously
estimated embedding receipt fallback is removed: absent usage stays unknown.
Studio Monarch also respects the existing unknown-price state when settling.
Monarch generations remain the sole owners of their model costs; summaries
link trace IDs without adding those costs again.

Stable source identities and revision-aware acknowledgements preserve local
history. V4 requires immutable observations: final receipts own one billing
generation, while accounting state changes use separate metadata-only spans.
Before POST, a durable dispatch claim prevents concurrent or restarted processes
from sending that record again. Definitive rejection permits retry; ambiguous
or partial delivery stays uncertain. `telemetry reconcile` confirms remotely
observed IDs through the read API and never treats absence as proof of rejection.
A coalescing background worker captures its environment
before starting and sends outside database transactions; shutdown has a bounded
grace. `wb telemetry status|flush|backfill|reconcile` exposes recovery without model calls.
Tests disable live telemetry and use local receivers.

The live zero-cost telemetry probe was accepted by the US Langfuse project and
subsequently returned by Observations API v2. Trace:
`99274eab8d7258eb169b6e99b9cfb4e5`; observation `547e217d4dc261c5`;
start `2026-09-10T17:27:23.365Z`. The span has `purpose=telemetry-check`,
`termination=completed`, metadata cost zero, and no billable generation cost.
The diagnostic replay used the same observation identity and was visible as one
row when read. Subsequent review of the official v4 migration guide established
that this is not a reliable deduplication guarantee; production code therefore
does not replay ambiguous sends. No model was called.

The [v4 migration guide](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4)
requires complete immutable observations. A regression test first reproduced
the previous exported-ID update; the corrected exporter separates immutable
receipt cost from subsequent accounting events. Lost-acknowledgement tests
verify one POST only, with read-side confirmation or a retained uncertain state.

Initial focused integration checks: 31 passed. The detached full run exposed
four Genesis fixture/handler failures after the settlement interface gained
usage/outcome arguments. Updated receipt assertions still verify rounding and
receipt-before-outcome ordering. The handler now records unknown failures only
after dispatch and before settlement, preserving already settled amounts and
avoiding any lookup for a refused request. All 38 affected Genesis/activity
checks passed after this correction.

The first new CI run completed with 2,059 passed, nine skipped and one stale
pilot-plan hash assertion. Offline resolution with the archived harness/table
reproduces `41769e05aa5618a9`; the documented successor price table produces
`1912201bfea8a62a`. Only the expected hash was corrected, and the omitted pilot
row was added to the existing pricing transition record. No input was changed
to make CI pass.

Final full-test and GitHub CI results will be recorded before merge readiness is
claimed. Local/hosted ledgers remain separate, and historical provider billing
verification remains pending; exporting telemetry does not certify invoices.
