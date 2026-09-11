# Feature: One readable report in Studio and HTML

Created: 2026-09-11. Branch: ailabs/report-template. Status: approved for implementation.
Carlos approved the diagnostic format for both Studio and standalone HTML, with technical evidence available on demand in Studio. This extends feature 006 and follows the reviewed REPORT-TEMPLATE-PROPOSAL.md.

## User scenarios and acceptance

### US1: Understand a run (P1)
The reader sees a concise evidence-backed opening, task success before/after retries, cost, a comparison, a direct explanation, error buckets, short task diagnoses/responsibility, next actions, task results, and one measurement disclosure.
Given stored results, counts distinguish tasks and attempts, unknown costs remain unknown, conditional retry ceilings are not missing work, and scripted controls are labeled separately.
Given no reviewed analysis, show Analysis pending and measured results; never manufacture causes.

### US2: Share the same report (P1)
Exporting the displayed report produces a standalone HTML with the same metrics and narrative. Internal anchors work offline. No ZIP links, dead Studio buttons, or visible HTTP/source dumps. Technical details remain reachable from Studio.

### US3: Read on a phone and in print (P2)
At 390px the opening, chart labels, and diagnosis/responsibility remain readable without horizontal page overflow. Numeric comparison tables may scroll locally. All status colors have text. Printing includes measurement limitations.

### US4: Download supporting material (P1)
Carlos approved separate authenticated downloads for report HTML, logs JSON and prompts JSON, to attach himself when publishing. Keep supporting downloads outside the standalone report. Export only retained run evidence, respect the displayed audience, redact credentials and make missing prompt coverage explicit. Do not reconstruct historical prompts from current configuration. No public hosting or automatic publication.
Carlos also requested direct prompt/log linkage and a simple view of task requests
and expected results. Provide a standalone human review guide with hash-verified
task definitions and recorded outcomes. The guide loads supporting files locally;
attempt IDs and log IDs link the evidence. Do not expose this reviewer material
to evaluated competitors or regrade historical results.

## Requirements

- FR01: One rendering path for UI and HTML; reuse report_data, measures, reports.js and existing charts.
- FR02: Summary at most 100 words; diagnosis concise, responsibility explicit or undetermined; original evidence/grades unchanged.
- FR03: Reviewed interpretation retains supplied event references, reviewer/model and revision; absent or invalid interpretation cannot become a supported diagnosis.
- FR04: Filter all added counts and narrative by audience; never leak hidden competitor prose through new fields.
- FR05: Conditional first attempt/retry task metrics complement existing attempt metrics; preserve missing evaluation and infrastructure states.
- FR06: Exports embed CSS/fonts/charts, neutralize unavailable links and remove app controls. Preserve useful internal navigation.
- FR07: Reuse existing analysis billing/dispatch; no paid analysis during implementation. No database migration required unless existing stored JSON cannot carry the fields.
- FR08: Keep run and round report navigation and evidence interactions working. Apply common presentation to both, preserve round-specific paired methods.
- FR09: Run report controls provide separate logs and prompts attachments. Retained event references identify their source; downloads preserve historical data and require the existing Studio authentication.
- FR10: Downloads version 2 provides attempt_id and stable log_id/log_ids. Uncertain linkage remains unavailable. A separate guide shows frozen requests, starting data, assertions, change rules and saved verdicts; missing or mismatched task hashes refuse generation.

## Edge cases and success criteria
Offline tests cover retry success, all failures, no failures, pending/failed analysis, unknown costs, hidden competitors, script-only runs, and partial runs. Browser checks cover live UI, offline export parity, desktop, mobile and print. No upstream benchmark mutation, new dependencies, deployment or publication in this implementation.
