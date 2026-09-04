# Research: Task Sets by Difficulty and the Scored AutomationBench Domains

Phase 0 of `/speckit-plan`. Every finding below was measured against the code in
this repo (`monarch-benchmark/workflowbench/`) and the vendored benchmark
(`workflowbench/vendor/automation-bench`) on 4 Sep 2026. Design decisions from
the brainstorm (design §3) are taken as given and not re-argued.

## R1. The scored domains carry exactly the fields the import already handles

**Finding**: all six hundred rows of `finance, hr, marketing, operations, sales,
support` have an `info` mapping with `zapier_tools`, `initial_state`,
`assertions` and `task_name`; some also carry `meta`. Measured over every row:
only two field shapes exist, `(assertions, initial_state, meta, task_name,
zapier_tools)` and the same without `meta`. **Not one** of the six hundred has
`expected_changes` or `allowed_changes`.

**Decision**: `wb corpus import-ab` needs no new reader. It already calls
`get_domain_dataset(domain)` and copies exactly those keys, defaulting the two
missing ones to empty lists. The six scored domains are a naming change, not a
parsing change.

**Consequence**: approval rules for the scored domains come from
`wb corpus declare`, exactly as they did for the two hundred baseline tasks
(`PLAN.md` F4/F5). No new derivation.

## R2. No difficulty label exists in the vendored benchmark

**Finding**: searching the whole package for `difficult`, `complexity`,
`hardness`, `tier` and `level` returns only business data inside task fixtures —
a customer's "Gold tier", an escalation "Tier 1", a contractor's "Rate Tier".
Nothing structural, on no task, in no domain.

**Decision**: the difficulty measure is ours, must be defined by us, and must be
written down and frozen with the drawn sets. The README's own hard-set method
(the ten hardest per domain) is on a private set we do not have, so it is not
reproducible here either.

## R3. The tasks are Python, not data files

**Finding**: `automationbench/domains/<domain>/tasks.py` is a list of builder
functions returning dicts; the module ends by moving the task name into
`info["task_name"]`, serialising `info` to a string and calling
`Dataset.from_list`. Sizes range from 11k lines (`simple`) to 57k (`support`).

**Decision**: never read those files directly. Go through
`get_domain_dataset(domain)`, as `import_ab` already does — it is the only place
the string-encoded `info` is decoded correctly.

`# ponytail: the import stays one function over the vendor's own loader; parsing
the vendor's Python would be a second, rotting reader of the same data.`

## R4. All the services the scored domains need are already declared

**Finding**: the six scored domains seed forty-two distinct services in their
starting data: `airtable, asana, bamboohr, buffer, calendly, canva, chatgpt,
confluence, docusign, facebook_pages, freshdesk, gmail, google_ads,
google_calendar, google_drive, google_sheets, gorgias, helpcrunch, helpscout,
hiver, hubspot, instagram, intercom, jira, linkedin, mailchimp, monday, notion,
pipefy, quickbooks, reamaze, recruitee, salesforce, slack, trello, twilio,
twitter, wave, xero, zendesk, zoho_desk, zoom`. The set difference against
`config/products/simulated-apps.yaml`'s forty-seven is **empty**.

**Decision**: neither the product file nor `config/side-effects.yaml` needs a new
service for this feature. The five never seeded by the scored domains
(`basecamp3, facebook_conversions, facebook_lead_ads, linkedin_ads,
linkedin_conversions`) are simply unused by them.

**Consequence**: the check still ships as a command output (FR-006), because the
answer is only true of today's vendored tree and a patch could change it.

## R5. The difficulty measure separates the domains, and that is also its weakness

**Finding**, measuring `services seeded + expected changes + tools needed` over
all eight hundred tasks after derivation:

| Domain | Tasks | Median score | Range |
|---|---|---|---|
| simple | 200 | 4 | 3 – 9 |
| finance | 100 | 10 | 6 – 16 |
| hr | 100 | 12 | 7 – 16 |
| marketing | 100 | 12 | 6 – 18 |
| operations | 100 | 12 | 5 – 23 |
| sales | 100 | 13 | 7 – 26 |
| support | 100 | 15 | 8 – 25 |

Terciles over the whole corpus fall at **9** and **12**.

**Decision**: use it as the default measure, and say plainly in the spec and the
manifest that the lower tercile is dominated by the baseline domain and the upper
by the scored ones. Stratifying the draw across domains within each tier is what
keeps "tier" from collapsing into "domain" — but only partly, and a reader must
be told.

**Alternative considered**: domain as the proxy (baseline = simple, {finance, hr}
= medium, the rest = complex). Simpler, and it is the vendor's own grouping.
Rejected as the default because the domains overlap heavily (marketing spans
6–18, sales 7–26) so the grouping would not be a difficulty grouping at all, and
because it makes tier and domain the same variable — a tier difference could
never be distinguished from a domain difference. Kept on the table as the
fallback if the measure does not survive review (spec Open Question 1).

**Why these three inputs and not others**: they are the only three counts present
on every task, already frozen by the task hash, and requiring no judgment. Number
of assertions was considered and dropped — after derivation, expected changes is
one per mapped assertion, so counting both would double-weight the same thing.
Prompt length was considered and dropped: it measures how wordy the author was.

## R6. Freezing a drawn task, and where the label may live

**Finding**: `contract_hash(task)` in `wb_orchestrator/orchestrator.py` is what
`import_ab` and `declare_dir` embed as `contract_sha256`, and what
`validate_corpus` re-computes to detect drift.

**Decision**: a drawn task is a **byte copy** of its corpus file plus
`info.tier` and `info.domain`, and those two keys are **excluded from the
hash**, so a drawn copy carries the same `contract_sha256` as its original.

**Rationale**: the hash exists to say "this is the same work under the same
approval rule". A label naming which set the copy sits in is not that. If the
label moved the hash, a corpus round and a tier round could never be compared,
and adding a report grouping would retroactively invalidate every stored row —
the opposite of what rule 5 protects.

**Verification**: a test asserts the drawn copy's `contract_sha256` equals the
original's and that `validate_corpus` reports no drift on the drawn folders.

`# ponytail: two ignored keys in the hash function, not a separate metadata
sidecar file; the ceiling is that every future label must be added to the same
ignore list deliberately.`

## R7. Determinism of the draw

**Decision**: one `random.Random(seed)` for the whole draw, consumed in a fixed
order: tiers in the order simple, medium, complex, then the random set; within a
tier, domains in a fixed alphabetical order; within a domain, the candidate list
sorted by task id and then shuffled. Files written with sorted keys and a
trailing newline; the manifest written with sorted task rows.

**Rationale**: byte-identical output for the same seed (FR-015) needs a fixed
consumption order and a fixed serialisation, not just a seeded generator. Sorting
before shuffling is what makes the input order irrelevant to the result — the
filesystem's iteration order must not be able to change a draw.

**Alternative considered**: a hash-based deterministic selection (take the tasks
whose `hash(seed + task_id)` is lowest). Rejected: harder to explain in the
manifest, and it makes "spread across domains" awkward to express.

## R8. Stratification within a tier

**Decision**: round-robin over the domains present in the tier, in alphabetical
order, taking one shuffled candidate from each in turn until the size is reached;
a domain that runs out is skipped on later passes.

**Rationale**: it is the shortest rule that gives "as even as the counts allow",
it is one loop, and it is trivially reproducible. It also degrades gracefully:
a tier with one domain simply yields ten from that domain, and the manifest's
per-domain counts show it.

**Alternative considered**: exact proportional allocation to each domain's share
of the tier. Rejected: with ten slots and seven domains, proportional allocation
is mostly rounding, and the rounding rule would be more code than the round-robin
it replaces.

## R9. Where the draw's exclusions come from

**Decision**: a task enters the candidate pool only if it has a non-empty
approval rule (`info.expected_changes`) and its embedded hash matches its content.
Everything else is excluded and named.

**Rationale**: a task with no approval rule cannot be graded — the grader already
flags it — and a task whose hash does not match is not the task anyone froze. Both
are corpus problems, and drawing over them would push a corpus problem into a
round nobody would suspect. This reuses exactly the two checks
`validate_corpus` already performs.

## R10. Command placement and naming

**Finding**: `wb corpus` already has `import-ab`, `validate` and `declare`, and
`import-ab` takes `--domains` (a comma list) with `--dest`.

**Decision**: the draw is `wb corpus tiers`, a fourth subcommand of the same
group. `import-ab` keeps its existing `--domains` flag and gains the word `all`
plus a `--dest` that may name a pattern with the domain in it, so six domains can
land in six folders from one call.

**Note on the design's wording**: the design writes the import as
`wb corpus import-ab --domain <name>`. The flag that exists is `--domains`
(plural, comma list). The spec and this plan use the existing flag rather than
adding a singular alias for one call site — a singular alias would be a second
name for the same thing.

## R11. What this feature deliberately does not build

- No aggregation across the four rounds: that is feature 006, and pooling four
  separate rounds into one figure is precisely what rule 7 forbids doing casually.
- No new grading, no new approval-rule machinery, no change to `declare.py`'s map.
  If the scored domains need map entries, that is its own reviewed change with
  Lucas's sign-off (spec Open Question 4).
- No round. The four plans ship unapproved and this feature spends nothing.

## Unknowns carried as open questions (none blocking the offline work)

1. Confirming the measure with Carlos and Lucas before the drawn sets are frozen
   and committed — the only one that blocks a deliverable (the committed sets).
2. Lucas's patches to the vendored benchmark, which could change scored-domain
   tasks and force a redraw.
3. Services beyond the product's list — none today; re-check after those patches.
4. How many assertion types in the six scored domains the derivation cannot map.
5. The pilot task set's hand-written approval rules versus the derived ones.
