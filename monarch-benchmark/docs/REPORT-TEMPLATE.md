# WorkflowBench report template

Approved by Carlos on 2026-09-11: the same readable format in Studio and the
standalone HTML export, with technical details available on demand in Studio.
Implementation record: [feature 014](../../specs/014-readable-reports/spec.md).

## Reading order

1. **Finding and summary.** Run identity and status, a specific supported
   headline, and at most 100 words explaining the outcome. Without a reviewed
   opening, use the measured task counts and say analysis is pending.
2. **Key results.** Initially solved tasks, tasks solved including retries,
   recorded USD, and recorded attempts. Every count names its denominator.
3. **Comparison.** Task success with uncertainty, recorded cost, and typical
   attempt duration. Execution kinds appear in the comparison table. Say beside
   the chart that API controls, native agents and workflow builders differ.
   Scripted controls remain visible in the table but outside these charts.
4. **Why these results?** A direct explanation grounded in cited evidence, with
   the analysis basis, model and revision. A model interpretation is not human
   review and does not establish causation.
5. **Error buckets.** One primary recorded-outcome category per failed attempt
   for the report's subject. Show count, share and cost. Repetitions count as
   attempts; categories are not automatically root causes.
6. **What actually went wrong.** Four columns: task; failed attempts and cost;
   diagnosis; responsibility. Keep prose concise. On mobile use labeled blocks
   so diagnosis and responsibility do not require sideways scrolling.
7. **What to change first.** Up to three cited actions, each with an observable
   acceptance condition. With no supported action, omit the section.
8. **Comparison and retry value.** Initial and retry-inclusive task counts,
   uncertainty, attempts, total and retry USD, and typical duration. Preserve
   missing evaluations, infrastructure-only tasks, and unpriced attempts.
9. **Results by task.** Text labels distinguish initial pass, retry pass,
   failure, infrastructure interruption, and no recorded evaluation.
10. **Measurement definitions and limitations.** One disclosure for caveats,
    definitions, identities and measurement details. Material qualifications
    also appear next to the claim they qualify. This content prints even when
    collapsed on screen.

Studio adds an expandable evidence section with recorded findings, attempt
checks, category comparisons and detailed cost metrics. Those metrics use
attempts as their denominator and retain their own definitions. Round reports
reuse the visual treatment, export and consolidated disclosure while preserving
pooled statistics, paired comparisons, trends and links to constituent runs.

## Content and evidence

- Compute metrics in the shared Python reporting layer; the browser formats
  them. Do not copy this run's particular findings into future runs.
- Keep tasks and attempts separate. Conditional retry ceilings are not missing
  work. Initial repetitions and conditional retries retain their recorded
  identities, rather than being guessed from completion order.
- Missing receipts make totals unknown, never zero. Unpriced counts remain
  visible, and missing-cost competitors are omitted from cost charts.
- Every diagnosis retains the exact supporting event and attempt references.
  Responsibility may be Monarch, WorkflowBench, AutomationBench, shared or
  undetermined. A grader failure alone does not assign responsibility.
- Preserve old analysis files and immutable verdicts. New interpretation uses
  the existing separately billed analysis lifecycle; viewing/exporting a report
  does not launch analysis or another benchmark attempt.
- If no usable interpretation exists, show measured results plus an explicit
  pending or failed analysis state. Do not invent a cause to fill a template.
- If a public audience excludes competitors used as analysis inputs, suppress
  that interpretation. Citations alone cannot prove prose omits hidden data.
- All report prose is English. Explain unfamiliar application names when useful.

## Visual and export behavior

Reuse Studio's existing typography and semantic color tokens with the diagnostic
report's spacious reading order. Keep prose around 65-75 characters per line.
Charts fit their own columns, stack on narrow screens, and include text data.
Tables use explicit labels; status is never conveyed by color alone.

The export snapshots the displayed article and embeds CSS, fonts and charts.
Remove Studio-only controls and chart downloads; preserve valid local section
links and remove links whose destination is unavailable offline. No ZIP links,
HTTP evidence dump or separate sourcing/reproducibility section is required for
sharing. The original evidence remains available in Studio and retained records.

The run report offers three separate downloads: report (HTML), logs (JSON), and
prompts (JSON). Supporting files use retained evidence and the displayed audience;
missing input messages are disclosed rather than reconstructed from current
configuration. These authenticated controls are omitted from exported HTML.
The person publishing attaches the files; downloading does not publish them.
An additional review guide shows hash-verified task requests, initial data,
expected assertions/change rules and saved outcomes. It loads the supporting
JSON/GZ files locally and links a prompt to its exact log IDs within a recorded
attempt. Missing linkage or system context stays explicit. The bucket explanation
uses normal body text size, matching the explanation of the results.

## Generation path

- `wb_studio/measures.py`: shared numeric definitions and task progress.
- `wb_studio/report_data.py`: audience-filtered `reading` view and evidence refs.
- `wb_studio/analysis.py`: optional cited interpretation, responsibility and
  actions, summary length, schema/rubric revision and citation validation.
- `wb_studio/static/reports.js`: shared presentation and standalone export.
- `wb_studio/static/report.css`: desktop, mobile and print composition.

Keep this document and feature 014 acceptance checks aligned when changing the
structure. Do not create a second reporting engine or a separate metric source
for exported reports.
