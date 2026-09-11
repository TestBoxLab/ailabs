# Streaming Studio test research

Scope: new paid request gateway, local Studio job manager/API, graph streaming and rich output UI. Existing pytest style, temporary SQLite and mocked provider transports.

Requirements: bounded paid admission before every request; unknown billing retains hold; credentials never emitted; model comparison with task drilldowns; restart-safe job history; cancellation; SSE reconnect; rich outputs escape untrusted content; native unavailability disclosed.


## Feature 027 report scope — 2026-09-11

Report-specific research/requirements were recorded in
specs/027-genesis-report-authoring/{spec,research,plan}.md before implementation.
Bounded targets: genesis_reports lifecycle, report_patterns projections,
report_state frozen sources, report_budget admission, report_recovery startup,
native tool integration and rendered report. Existing pytest tmp_path/Mock
conventions and scripted browser fixtures were reused. Acceptance: complete
attempt analysis, concise/full report, review/fix/publication, exact percentages,
source identities, role restrictions, budget and recovery.
