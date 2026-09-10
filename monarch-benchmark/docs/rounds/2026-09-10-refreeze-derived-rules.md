# Re-derivation of the four frozen sets, 10 Sep 2026

Pre-registration record for a rule change made after results existed, as the
constitution (§III) requires. **Approved by Carlos, 9–10 Sep 2026.**

## Why

Six defects found on 9 Sep were in the approval rules — the half of the verdict
WorkflowBench derives itself — not in AutomationBench's data. Four of them made
a rule name a path the world can never produce, so **a correct answer could not
pass**:

| Defect | Frozen tasks affected |
|---|---|
| The rule named `google_sheets.spreadsheets[id=…]*`, a subtree the loader empties when it flattens rows into their own collection | 12 of 40 |
| `<service>.actions[*]`, a list-shaped glob against a dict-keyed action log | 1 |
| `zoom.actions.*` / `calendly.actions.*`, on services whose schema has no `actions` field | 1 |
| An added subtree collapsed to `"<object>"`, hiding the writes inside it | 12 |

Two more accepted a wrong answer: a whole-service wildcard took any number of
writes nobody asked for, and a `where` clause compared `1200000` against
`"1200000"` and rejected the write it had asked for.

The Hard round of 6 Sep scored 0% for every competitor on every task. Re-grading
the one task whose hash still matched turned **0 of 11 into 9 of 11** — that
round measured a broken grader, not competence.

## What changed

`wb corpus declare <set> --overwrite --product simulated-apps` over the four
sets. Task prompts and starting data are untouched; only `expected_changes` and
`allowed_changes` moved, and with them each task's `contract_sha256`.

**23 of 40 tasks changed. 17 were already correct and are byte-identical.**

| Set | Task | Before | After |
|---|---|---|---|
| random-10 | finance.employee_reimbursement | `399bb2ab889eee82` | `330daf21c2cdcece` |
| random-10 | operations.trello_vendor_hold_email | `db5d268deb582c28` | `0ea12e30313ef523` |
| random-10 | simple.jira_auth_improvements | `e31c21d9f9b8c8d7` | `9ca497a5aad33b2f` |
| random-10 | simple.new_lead_sf_jira | `7933c6465cc06d60` | `4201a4dc99441ae5` |
| random-10 | simple.trello_q1_marketing_budget | `63b8f8015da4e7f6` | `806ca51c6f164f0a` |
| random-10 | support.helpcrunch_trial_nurture | `acfd70ab4a14df34` | `61f75f01c8821680` |
| random-10 | support.reamaze_cross_platform_dedup | `f9b1fffe98a7d32c` | `4728cf1200294dbf` |
| tier-complex | hr.job_board_monitoring | `ce2a289253459bce` | `e737fe786d70920c` |
| tier-complex | hr.trello_recruiting_event_coordination | `098fcc08a8f978a9` | `b94ba1ad31622c2c` |
| tier-complex | marketing.trending_topic | `1413ba4fd0e04091` | `db3cd7d43ba1d851` |
| tier-complex | operations.docusign_prospect_nda | `432cd3b4f37c30b7` | `78baf927bc4a1e49` |
| tier-complex | operations.zoom_change_advisory | `3f4683d8410e9705` | `568a3058b8a6f34d` |
| tier-medium | hr.comp_adjustment_batch | `9ebf85d40fdc6e31` | `3564f231c451659f` |
| tier-medium | marketing.event_sponsorship_screen | `cace2254fd974e10` | `5eff77d3ed2dd0bb` |
| tier-medium | operations.invoice_shipping_trigger | `afcbaa6c977eb3b2` | `bb050aeb3fdb4766` |
| tier-medium | simple.invoice_airtable_slack | `eeb2e22aa27c8fcd` | `9facf7b9a9e82ad3` |
| tier-medium | support.freshdesk_auto_merge | `12218a5f54fcdde4` | `5b76d16cdc36545f` |
| tier-simple | finance.annual_budget_prep | `807735ad825316c4` | `d89264fc800c6a9e` |
| tier-simple | finance.audit_sample_selection | `3e16a74e152ee0aa` | `41dc134272c3e47f` |
| tier-simple | marketing.featured_snippet | `b58053ab8be5ce65` | `f1c46921ff672a62` |
| tier-simple | marketing.industry_event_tracking | `934923b18b1c6963` | `48271621c06bf1f9` |
| tier-simple | simple.airtable_find_update | `7dd1f0043ddc6e9a` | `c999452d6ddd0439` |
| tier-simple | simple.email_airtable_lead | `346081f31952dfea` | `a0efa54d18c6e06b` |

## What this costs

**Every stored attempt on those 23 tasks is now non-regradable.** `wb grade`
refuses a snapshot whose task hash has moved, deliberately: old snapshots are
never scored against an edited rule. The rounds affected are those of 5 and 6
September, which were already unusable for the reason above.

The task ids are unchanged, so the four sets still describe the same ten prompts
each; `wb corpus tiers` was **not** re-run, because a redraw over a different
usable pool would pick a different ten and the round sheets would stop describing
the sets that ran.

## Config hash

`CREATE_RUN_HASH` moved from `9e23c3dfb31f241a` to `41769e05aa5618a9` — a
separate change, from re-syncing the Monarch knowledge base against the deployed
instance and re-pointing it at the hosted front door. The frozen knowledge-base
hashes had drifted from what the discovery service reported and were refusing
every Monarch attempt at `prepare()`.

## What still needs Lucas

- `simple.invoice_airtable_slack` has a weak assertion: `airtable_record_exists`
  pins the table but not the vendor or the amount, so a wrong invoice satisfies
  the positive half. The vendor's handler supports `fields`; the task omits it.
  Adding it edits an assertion, not a derived rule, and needs his sign-off.
- The two Jira tasks stay collateral-blind: their assertions carry no content for
  a `where` clause to pin. That is a limit of the vendor's data, not of the
  derivation.
- The vendored AutomationBench here is plain `1.0.6` while `achievable-50`
  declares `1.0.6+evalrepair.10`; his patched tree is not on this machine.
