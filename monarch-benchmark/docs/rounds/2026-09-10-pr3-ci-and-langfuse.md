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

## Final verification

Code commit `b8f3906cbe5089c6348392cf846ec9fcea860c24` passed
[GitHub run 34510275623](https://github.com/TestBoxLab/ailabs/actions/runs/34510275623):
**2,096 passed, nine skipped**, 537.89 seconds. Both corpus checks passed:
10 pilot tasks and 200 imported simple tasks, with no no-op failures, answer-key
failures or approval-rule hash drift. The imported corpus has 184 tasks without
a scripted answer key; validation reports that limitation rather than claiming
those positive examples were executed. The final focused group passed 51 tests.

The detached Windows run started before the final fixes and finished after
1,789.13 seconds: 2,092 passed, six failed, two skipped. Five failures are the
four Genesis cases and stale pilot hash corrected above and covered by the
final green checks. The sixth,
`test_http_rejects_foreign_origin_host_and_missing_session_before_mutation`,
reported `WinError 10053` while reading a local HTTP response; it also failed
one isolated check. It passes in the final Ubuntu CI. Carlos instructed that
the known Windows Studio transport issue not be pursued, so no production
security check or assertion was weakened to hide it.

The final exporter also passed a live zero-cost canary, trace
`a3381fc03a51e714f2bfb006ab6ed53a`, at `2026-09-10T17:48:19.326993Z`:
one accounting span, one billing generation with explicit total cost zero and
zero token buckets, and one summary span. All three were returned by the v2
Observations API. A simulated lost local acknowledgement was recovered through
the production read-side reconciliation function: three confirmed, zero
pending, zero uncertain, no additional POST or model request.

Graphify's code graph was refreshed: 14,070 nodes and 35,095 edges. The vendor
remains clean at upstream `4a8e106`. Main `290852f` is an ancestor of the branch;
PR #3 has no merge conflicts. PR #1 remains a separate draft. Commits and pushes
are complete; merge itself remains Carlos's action. The PR description and
GitHub checks carry the latest status of the documentation-only follow-up.

Local/hosted ledgers remain separate, and historical provider billing
verification remains pending; exporting telemetry does not certify invoices.
The hosted Studio must deploy this version to activate its exporter. No paid
round or infrastructure deployment was performed during this CI/telemetry task.
