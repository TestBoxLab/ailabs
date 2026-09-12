# Live workflows and performance — implementation evidence

Implemented locally on 11 September 2026. No paid benchmark, model call,
deployment, frozen task change, grading change, or historical regrading occurred.

## Delivered behavior

Activity now presents persistent model lanes with recorded phase, model, tool,
workflow, and verdict nodes. Live deltas update previews in place; structured
records render as small tables. Newly received events trigger finite connection
and node feedback. Historical events do not replay as live. Pause, reduced
motion and document visibility suppress animation. Observed event order is
explicitly distinguished from recorded workflow dependencies, including branches
between nonadjacent nodes. Opening details retains the full existing inspector.

Current workflows precede supporting detail. Desktop places outcome and timing
charts alongside model lanes; phone places them below the horizontally scrollable
comparison. Latest activity selects the newest active task. Inspecting an earlier
node survives later arrivals. Initially long histories expose the last 18 nodes;
Show earlier reveals preceding nodes, and visible nodes remain while watching.

The live and permanent reports share one original-evidence projection:
per-attempt completion time; successful median/p90; separate failed and all-attempt
timing; pass rates; cost per successful task including failures and execution
issues; known/unknown recorded spend; tool calls and observed errors; model turns;
phase medians; and known unintended changes with coverage. Exact sample links
open attempt evidence. No fabricated interpolation of displayed numbers.

## Impeccable review and polish

Applied the canonical Impeccable context, animate, craft-floor, critique and polish
procedures. Independent assessment A preceded detector evidence: 25/40 initial
heuristic score. Strengths were honest comparisons, structured output inspection,
and restrained motion. Its two P1 findings were buried workflow activity and
Latest activity leaving the user on finished work. Both are corrected. P2 fixes:
ink selection outline (separate from failure red), labeled horizontal comparison,
44px main controls, labeled input/output previews and full-inspection cues.

Independent assessment B ran the detector once: zero findings, exit 0. Browser
inspection additionally found small touch targets, missing status announcements
and small labels; these were corrected with 44px controls, polite status-only
announcements and larger secondary labels. No claim is made that a regex detector
establishes accessibility. Sampled initial light-theme contrast passed (ink 16.42:1,
muted 6.18:1, success 5.18:1). Native browser profile collision and Windows ACL
startup issues required an isolated Playwright browser for independent reviews.
CSP prevented a detector overlay; no overlay is claimed.

Independent code review identified terminal-state regression on delayed events,
focused-node removal after long streams, and omitted nonadjacent dependencies.
All three were fixed and checked in the final offline scenarios. The reviewer
reported no additional blocker, but did not independently rerun the final fixes.
The final desktop, phone and dark screenshots were inspected by the implementer;
no final heuristic rescore was performed. Finished-output collapse/expand was also
corrected and exercised.

## Verification

| Requirement | Evidence |
|---|---|
| Graded normal finish, separate infra/ungraded | test_success_requires_normal_graded_finish_and_infrastructure_stays_in_operational_denominator |
| Missing durations and descriptive quantiles | test_timing_interpolates_quantiles_and_reports_missing_without_inventing_zero |
| Failed/infra spend included in cost per success | test_cost_per_success_includes_failure_and_infrastructure_spend |
| Missing telemetry and replay deduplication | test_missing_tool_telemetry_never_implies_zero_error_rate_or_known_calls; test_terminal_tool_errors_and_turns_are_observed_once_despite_event_replay |
| Immutable original operational evidence | test_permanent_report_keeps_original_spend_when_task_hash_is_stale |
| Partial unintended-change coverage | test_missing_collateral_detail_marks_known_counts_as_incomplete |
| Terminal states, duplicate events, exact outputs | node tests/browser/live-workflows-model.cjs — passed |
| Live SSE, 24-node focus retention, branching dependencies, active task shortcut | node tests/browser/live-workflows.cjs — passed |
| Metric refresh, report sample link, structured inspector | Same browser scenario — passed |
| Phone controls, reduced motion, light/dark, no page overflow/errors | Same browser scenario at 1440×1100 and 390×844 — passed |
| Focused Python regression set | uv run --python 3.13 python -m pytest tests/test_studio_performance.py tests/test_studio_measures.py tests/test_studio_reports.py tests/test_static_csp.py -q — 87 passed in 13.82s |

All commands above run from monarch-benchmark/workflowbench/. Browser checks use
a clearly labeled disposable synthetic fixture, with provider traffic disabled.
Final machine-readable checks and screenshots are generated in
.tmp/live-workflows/{checks.json,desktop.png,mobile.png,dark.png,report.png}.
Final browser process exited 0 and its dedicated server shut down. One intermediate
fixture start was blocked by a transient syntax error in another task's concurrent
edit; the subsequent run passed after that edit completed. Unrelated edits were
preserved. No full 27-minute repository suite was run for this scoped feature.

## Remaining limits

This is local implementation and offline acceptance, not deployed/live-model
validation. Timing excludes queueing and grading. Retry recovery rates and timing
to first useful output are not inferred from records lacking explicit attempt
identity or suitable events. Small-sample p90 values are descriptive. Original
records may have missing timing, billing, tool or change detail; coverage is shown.
Dependency arrows are authored only when the journal contains recipe edges;
other trajectories are labeled as observed event order. The global Genesis voice
strip remains part of the shared application shell. No new dependency was added.
