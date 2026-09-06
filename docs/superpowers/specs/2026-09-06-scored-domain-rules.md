# Approval rules for the six scored domains

6 September 2026 · Carlos · **needs Lucas's sign-off before the next round**

## What was wrong

The benchmark derives each task's approval rule from its assertions: what must
change (`expected_changes`) and what else may change without failing the
attempt (`allowed_changes`). The derivation, in `wb_orchestrator/declare.py`,
was written for the `simple` domain and its hand-listed table of assertion
types covered that domain only.

The six scored AutomationBench domains (finance, hr, marketing, operations,
sales, support; 600 tasks) use 335 assertion types, 203 of them positive. The
table mapped almost none of them, so the "nothing else changed" half of the
rule was wrong in two ways at once:

- **218 of the 600 tasks derived no rule at all.** With `expected_changes`
  empty the grader falls back to a wildcard, and those tasks were excluded from
  the tier draw entirely.
- **Worse, where a task had a partial rule, every real change failed it.** A
  change the assertions demanded but the rule never named landed in
  `unexpected_changes`, which fails the attempt.

`tasks/tier-complex/finance.qb_void_stale_invoices.json` is the case that found
it. The task asks for two stale QuickBooks invoices to be voided and the
assigned reps e-mailed, and it carries twelve assertions. The old derivation
produced exactly **one** matcher, from the Slack summary assertion. Claude Opus
5 did the job — every assertion passed — and the checker still failed the
attempt with unexpected changes `quickbooks.invoices[id=qi_601].voided`,
`.balance` and the Gmail messages it had been asked to send. In the Hard round
every competitor scored 0% for this reason; the Easy and Average rounds were
depressed by the same defect.

## What changed

Hand-listing 203 assertion types would rot the moment the vendor adds one, so
the mapping is derived instead, from sources that are already ground truth in
the vendored `automation-bench`:

- **Service and collection** come from the vendor's own world model. Each
  assertion type is named `<service>_<noun>_<verb>`, matched against
  `WorldState`'s fields and each service's collections. 179 of the 203 resolve
  by name alone; `_COLLECTION_ALIAS` names the other 24, each read off the
  handler's source (`gmail_email_*` reads `gmail.messages`,
  `zoom_action_exists` reads `zoom.meetings`, and so on).
- **Whether an assertion demands a change at all** comes from the vendor's own
  `negative_assertion` marker. A "not sent to" / "not exists" assertion is
  satisfied by doing nothing, so it grants nothing.

Four narrower corrections came out of running the result against the real
tasks, each one a case where the old matcher named a path the world never
produces:

1. **An assertion the initial state already satisfies demands no change.**
   `quickbooks_invoice_field_equals(qi_603, voided, "false")` on an invoice
   that starts unvoided asks for that invoice to be *left alone*. Requiring it
   would fail every correct competitor. Such matchers are now granted as
   allowed, never required. Where the seed omits the field, the vendor's schema
   default settles what the world starts with.
2. **Action logs are a dict keyed by `action_key`,** not a list, so a flat
   `<service>.actions[*]` matcher could never match. The matcher now names the
   one action key the assertion asks for.
3. **Google Sheets rows are nested** under
   `spreadsheets[].worksheets[].rows[]`, not a flat `google_sheets.rows`, and
   these seeds key the spreadsheet under `spreadsheet_id` about as often as
   under `id` — in which case the diff addresses it positionally. The matcher
   now names the spreadsheet only when the seed really keys it that way.
4. **An id key only anchors the matcher when it names a record the world
   carries.** `slack_dm_sent_to`'s `user_id` is the recipient of a new message,
   not a record id; `row_id` is a sheet coordinate. The seed settles which is
   which, so no second list has to be kept in step with the vendor's.

One entry was added to `config/side-effects.yaml`: voiding a QuickBooks invoice
zeroes its balance in the same call (`quickbooks_invoice_void` sets `voided` and
`balance` together), so a competitor that voids exactly what was asked is not
charged with a collateral write.

Two long-standing quirks in the `simple`-domain path were corrected by the same
reasoning, both of which had demanded an op or a path the diff never emits: a
field the seed omits diffs as `added`, not `changed`; and `object_type:
"Opportunity"` names the collection `opportunities` where the assertion carries
no `collection` key.

## Counts

Re-derived with `wb corpus declare --overwrite` on the six scored folders.

| Domain | Tasks | Rule changed | No rule before | No rule after |
|---|---:|---:|---:|---:|
| finance | 100 | 99 | 74 | 0 |
| hr | 100 | 97 | 59 | 0 |
| marketing | 100 | 74 | 39 | 0 |
| operations | 100 | 85 | 8 | 0 |
| sales | 100 | 86 | 23 | 0 |
| support | 100 | 100 | 15 | 0 |
| **Total** | **600** | **541** | **218** | **0** |

**Nothing could not be mapped.** Every positive assertion type in the six
domains now derives a matcher; the only tasks with an empty `expected_changes`
are those whose assertions are all negative, which legitimately require no
change.

A residue worth naming: 27 matchers across the corpus are still whole-service
wildcards (`salesforce.*` 13, `jira.*` 10, `slack.*` 2, `mailchimp.*` 1,
`airtable.*` 1), inherited from the old hand-written table for assertions that
name no collection. They are permissive — they will not fail a collateral write
within that one service — but they no longer fail correct work. Narrowing them
is a separate change.

## The four sets

Every scored task's hash changed, so the frozen copies under `tasks/` went
stale. Redrawing would have been the wrong repair: fixing the rules also made
the 218 excluded tasks usable, so the same seed over a larger pool picks a
different ten and the round sheets would stop describing the sets that ran.

`wb corpus tiers --refreeze` was added for this: it rewrites the four sets from
the corpus keeping the task ids the manifest already records, and refuses
rather than silently dropping a task that is no longer usable. Same seed
(20260904), same forty prompts, new hashes.

The usable corpus went from 582 to 800 of 800, which moved the tier cut points
from 9 and 12 to **10 and 15**. The drawn sets keep their exact membership and
domain mix; `tasks/tiers-manifest.yaml` records `refrozen_at` and why.

## Pre-registration

The constitution's pre-registration rule applies: changing a task's approval
rule changes its hash, and rows graded under the old rule are not regradable
against the new one. The eight round sheets say so.

**Lucas must sign off on this change before the next round runs.** No round has
been run since; the four sets are frozen and waiting.

## Verification

`uv run python -m pytest tests -q` on the final code: **679 passed, 0 failed**
(651 before this change, plus the 28 added here). The targeted suites:

```
uv run python -m pytest tests/test_declare*.py tests/test_corpus*.py \
    tests/test_m4.py tests/test_tiers*.py -q -p no:cacheprovider
```

Tests added in `tests/test_declare_scored.py`: the reported task passes when
its assertions are satisfied and still fails on a collateral write; one test
per newly mapped assertion shape (gmail sent-to, sheets row exists, quickbooks
field equals, action exists, slack message exists, ticket has tag, calendar
event exists, salesforce field equals) where the oracle-like change passes and
an extra change fails; a negative assertion grants nothing; every positive
assertion type in the 600 scored tasks maps; and a regression over all forty
drawn tasks that applies each task's own expected changes to its initial state
and asserts the invariant passes.

`tests/test_tiers_refreeze.py` pins that a refreeze keeps every task id, writes
the hash the corpus now carries, records the same seed, refuses when a drawn
task left the corpus, and that `tasks/` and `corpus/` do not drift.
