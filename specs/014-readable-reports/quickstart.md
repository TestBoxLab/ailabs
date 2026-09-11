# Verification: readable reports and supporting downloads

All checks are offline. No provider request, paid run, database regrading or
deployment is part of this feature verification.

## Report data and analysis

From `monarch-benchmark/workflowbench`:

```powershell
uv run python -m pytest tests/test_readable_report_data.py tests/test_reading_analysis.py tests/test_report_definitions.py tests/test_studio_measures.py tests/test_studio_reports.py tests/test_studio_report_baseline.py tests/test_configured_report_inputs.py tests/test_studio_failure_analysis.py tests/test_reasoning_review_retry.py tests/test_studio_outcomes.py tests/test_narrative.py tests/test_html_report.py -q
```

Recorded result: **205 passed, 2 skipped**. New data/schema/definition checks
were first observed failing for the behavior being corrected. Independent review
covered denominators, audience filtering, interpretation labels and citations.

## Browser

Start the free fixture in a detached process with logs on Windows:

```powershell
uv run python tests/browser/server.py --port 8774 --keep
```

Then:

```powershell
node tests/browser/report-template.cjs
```

The browser check passed for the live report, separate download attachment
responses, public audience, identical standalone metrics/narrative, no dead
export controls, 390px layout, chart readability, legacy navigation, round
standings and a standalone file reload without network. The new download-link
check first failed with `Separate download link required: logs`.

Print was checked by creating a PDF of the exported file with the measurement
disclosure closed, then finding its actual definitions in extracted PDF text.
These are labeled fixture reports, not new benchmark results.

## Retained evidence

Supporting files are prepared from an isolated copy of run
`f2799405-f9b3-4fb2-8e41-a517e9c39260`, including resumed attempts. Only artifact
locations in that copy are remapped for Windows; the original results database
retains SHA256 `910dfba5a4057a84b299648297e1e62ede7feec18b316951da84d5372e4f5f3d`.
The original approved diagnostic HTML remains a separate historical artifact.
Preparing attachments does not replace its editorial interpretation.

Download/backend verification:

```powershell
uv run python -m pytest tests/test_report_downloads.py tests/test_studio_app.py tests/test_configured_report_inputs.py -q
```

Recorded result: **41 passed**. Regression checks first exposed missing root
HTTP journals, duplicated prompt observations, and provider-specific reasoning
and credential fields; all were corrected before preparing attachments.

The combined run of both command groups recorded **244 passed, 2 skipped and
1 failure**: `test_front_door_path_relays_to_the_shim_without_login` encountered
Windows socket error 10053. This is outside the report/download changes; the
same HTTP group had passed immediately before. The failure is retained here
rather than reported as a fully green combined run.
The failing HTTP test then passed in isolation (1 passed in 1.37s); no product
or timeout changes were made to chase this known Windows timing issue.

Scoped Graphify refresh: 243 nodes, 577 edges, 12 communities across the seven
changed Python/JavaScript files, AST extraction only with no provider tokens.
This is not a full-repository semantic graph refresh.

The download export discloses missing context, preserves source references and
does not substitute current task definitions. Public exports exclude recorded
provider reasoning and redact credential patterns. They do not claim that
arbitrary secrets in prose can be recognized exhaustively.

## Linked evidence guide extension

`tests/test_evidence_guide.py` and `tests/test_report_downloads.py`: **9 passed**.
Red checks first demonstrated absent guide route, missing repetition metadata
and the guide retaining another task's result when selecting an empty task.
The latter also has a browser regression check.

```powershell
node tests/browser/evidence-guide.cjs <guide.html> <logs-v2.json.gz> <prompts-v2.json.gz>
```

Verified against the actual 106-attempt run: native local gzip loading, ten
hash-verified tasks, expected VIP assertion, recorded Monarch retry pass and
exact prompt-to-log linkage. Mobile containment and empty-task clearing passed.
The report note was measured at 12px before correction and 16px afterward,
matching its explanatory paragraph. No report metric or editorial text changed.
Final graph scope requested nine files; eight produced AST nodes (HTML parsing
unavailable), 247 nodes and 588 edges. The scoped report discloses that limit.
