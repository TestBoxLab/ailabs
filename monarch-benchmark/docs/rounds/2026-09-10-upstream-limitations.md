# Upstream world preserved, 10 September 2026

Carlos's final decision in this session supersedes the original repair brief:
AutomationBench's world, routes, seeds and assertions remain upstream, including
known defects. WorkflowBench may repair its own approval-rule translation. A bad
task can be excluded with a recorded reason or reported upstream; it must not be
silently edited. Adoption of `1.0.6+evalrepair.10` is suspended pending clarity
about its changes, not an active request to replace the dataset.

The source on this machine is AutomationBench `1.0.6`, upstream commit
`4a8e1061254004d9dac807054eed33fad7d1ff14`. The vendor worktree is clean.
The dependency pin now accurately names `1.0.6`; `uv lock` and `uv sync` completed.
The four historical task sets remain on their original world. `achievable-50`
still declares `evalrepair.10` and must continue to fail the world-revision gate.

## Airtable: confirmed environment limitation

Parent evidence: `run-20260910-043028`, attempt `simple.airtable_find_update`,
competitor `monarch@3b81a02dd+feat_railway-dev-deploy`. Its local
`t0/attempt-000/events.jsonl` has two observations:

1. `{Email}='jordan@example.com'` returns Jordan with `Status: Active`.
2. `AND({Email}='jordan@example.com',{Status}='VIP')` returns the same Active
   contact. The saved workflow requires an empty VIP result to create the record.

The router forwards `filterByFormula`; `airtable_records_list` passes it as
opaque `searchCriteria`, and `AirtableState.find_actions` ignores filter keys
missing from seeded records. No formula is evaluated. This explains the observed
read-only completion. It is not evidence of a generally incapable Monarch writer.

The official [Airtable filtering documentation](https://support.airtable.com/articles/1941464361-airtable-web-api-using-filterbyformula-or-sort-parameters)
describes selecting records by formula result; the upstream simulator diverges.
The runnable, no-cost reproduction is
[`test_airtable_limitations.py`](../../workflowbench/tests/test_airtable_limitations.py).
It checks the exact two historical reads, unchanged state and failing verdict.

An experimental local implementation was tested during the session, then fully
reverted when Carlos fixed the comparability policy. Its temporary package
version, patch, diagnostic task copy and plan change were removed. No paid
attempt ran against that altered world. `diag-front-door` retains its original
task and configuration.

## Invoice: confirmed assertion limitation

`simple.invoice_airtable_slack` checks the Airtable table/base, but does not
assert vendor or amount. Real API writes with `Vendor: Wrong Vendor` or
`Amount: 1`, plus a matching finance notification, pass both judges.
[`test_frozen_invoice_jira.py`](../../workflowbench/tests/test_frozen_invoice_jira.py)
documents this behavior. The original assertion and task hash
`9facf7b9a9e82ad3` are restored; no `fields` constraint remains.

No task was removed or redrawn in this session. These cases remain explicit
limitations of any result using the current sets. Before a quality comparison,
choose a versioned exclusion set or obtain an upstream fix; do not quietly
substitute a private repair and label it the published Zapier benchmark.

## Upstream issue drafts (not submitted)

**Airtable list ignores filterByFormula.** On upstream commit above, load
`simple.airtable_find_update`, GET Contacts with the two formulas above, and
observe identical non-VIP records. Expected: the VIP formula excludes the Active
contact. Impact: a legitimate existence check can suppress the requested write.

**Invoice assertion accepts wrong vendor and amount.** Load
`simple.invoice_airtable_slack`; POST an Invoices record with an incorrect vendor
or amount and send the required Slack notification. Observe a passing positive
assertion. Expected: the assertion verifies the business values requested by the
task. Impact: materially incorrect work can score as successful.

These drafts contain reproducible facts for an upstream report. No external
issue or message was published by this session.

## Validation and next attempt

The focused command covering the upstream limitations and retained approval
translation repair passed **77 tests**. See
[the approval-rule record](2026-09-10-invoice-jira-corrections.md) for its command
and sole final task hash change. The full suite was restarted after restoration;
the superseded partial execution is not final validation evidence.

The requested post-deploy diagnostic remains one Monarch attempt, no task retry,
estimated US$ 2–3 from the runbook. Its purpose is wiring verification, not a
publishable quality estimate. A completed attempt with application calls proves
the execution path, not correctness on this known-limited task. Historical usage
was checked against Langfuse and its observed gap reserved before the attempt.
[The diagnostic](2026-09-10-post-deploy-diagnostic.md) reproduced the same filter
trap. Monarch's workflow finished successfully, but WorkflowBench refused its
cost closure because the merged product used an unpriced model. It is not a
successful benchmark result, and it was not repeated.
