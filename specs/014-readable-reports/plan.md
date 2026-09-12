# Implementation plan: readable reports

Approved design: spec.md and Carlos's selection on 2026-09-11. Execute with test-driven-development, task-scoped agents and browser verification.

## Architecture and constitution check
Reuse stored results and measures; expose a `reading` presentation object from report_data.run_report. Existing fields remain for technical drilldowns and round views. Rendering and export share the same article. Analysis JSON may carry optional evidence-grounded headline, why, responsibility and next-action fields; older files remain supported with honest pending/undetermined states. No new dependency or database migration. No benchmark data, frozen hashes or historical verdict changes. Public filtering must cover every new field.

## Ownership and sequence
1. Data task: measures.py/report_data.py plus focused Python tests. Add first/retry task measures, subject selection grounded in configured Monarch identity where present, labeled comparison rows, subject failure buckets/cases with evidence references, and explicit pending state. Expose a documented reading object for renderer.
2. Analysis task (independent): analysis.py plus focused tests. Extend optional narrative schema/rubric to support concise responsibility and explanatory fields with valid event citations. Preserve billing and old-file compatibility. No paid calls.
3. UI task: reports.js/report.css and browser report-template check. Use reading fields to render approved order, responsive diagnosis blocks, comparison and retained Studio evidence access; reuse HTML export while fixing offline links/disclosures. Apply shared presentation to round reports without changing their statistics.
4. Integrate: focused offline report/analysis tests, browser UI/export/mobile/print checks; review; update design template, feature tasks and graph record. Commit locally only if useful; no push/deploy.
5. Approved sharing extension: reuse retained events and attempt journals for authenticated JSON attachments, with audience filtering and credential redaction. Add separate logs/prompts links next to the existing HTML download. Browser checks cover links and actual attachment responses; offline HTML remains free of supporting download controls.
6. Approved review extension: stable recorded attempt IDs and observation IDs connect prompt records with logs. Reuse the task hash function and stored result rows to generate a small offline guide; load large attachments with browser file inputs and native gzip decompression. Reuse the guide template from an authenticated download route. Hash mismatches refuse generation, and no evaluation is rerun.

## Validation
First run relevant existing report tests on the clean branch. For each behavioral change run a failing test for the intended reason before implementation. Then run relevant Python report/measures/analysis tests and browser checks with scripted/frozen evidence only. Confirm source database hash unchanged where real evidence is used. Browser preview must not start a paid run. Review missing analysis, unknown cost, audience filtering and retry denominators. Record exact commands and outcomes in quickstart.md.
