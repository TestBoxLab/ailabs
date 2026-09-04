# Design · Task sets by difficulty and the scored AutomationBench domains (feature 005)

Date: 4 Sep 2026 · Author: Carlos Mattos with Claude · Status: approved in brainstorm, awaiting `/speckit-specify`

This document records the design settled with Carlos on 4 Sep 2026. It feeds
`/speckit-specify` for feature 005. It changes none of the fixed rules in
`monarch-benchmark/PLAN.md` §1; it adds inputs (six more domains in the corpus,
four frozen task sets, four plans, one manifest) and one new offline command.
No model money is spent by anything this feature builds; the money is in the
rounds that use its task sets, and each of those needs Carlos's approval of that
specific run with the number of attempts and a cost band.

## 1. Goal

Today every Monarch-versus-models figure is one blended number over ten easy
tasks. It cannot answer the question that actually decides where Monarch wins:
**does the gap change with difficulty?** A product that maps a platform and
compiles a workflow should pull ahead exactly where a raw model has to hold many
steps and many services in its head — and that claim is either visible in the
data or it is marketing.

So the benchmark gets three task sets — **simple**, **medium**, **complex** — of
ten prompts each, run as **separate rounds against the same competitors**, plus a
fourth set of **ten drawn at random from the whole corpus** as a self-check on
the blended average. Four numbers where there was one, each with its own error
bars, each on a set frozen by hash before anyone runs it.

AutomationBench's own way of making a hard set — take the ten hardest tasks per
domain — is **not** what we do. It concentrates on one end of the distribution
and gives no simple or medium comparison; three tiers over the whole corpus give
the shape of the curve, not one point on it.

The corpus this draws from grows first: the **six scored domains** (finance, hr,
marketing, operations, sales, support — 100 public tasks each) join the 200
`simple` tasks already imported, giving 800 tasks to classify and draw from.

## 2. What was found in the code before deciding

Checked on 4 Sep 2026 against `monarch-benchmark/workflowbench/` and the
vendored `vendor/automation-bench`:

- **The scored domains carry exactly the fields the `simple` import already
  handles.** Every one of the 600 rows has `info` with `zapier_tools`,
  `initial_state`, `assertions` and `task_name`; some also have `meta`. There is
  **no** `expected_changes` and **no** `allowed_changes` on any of the 600 — same
  as `simple`, so `wb corpus declare` is the path to approval rules for them too,
  unchanged.
- **No difficulty label exists anywhere in AutomationBench.** Grepping the whole
  package for `difficult`, `complexity`, `hardness`, `tier` and `level` returns
  only business data (a customer's "Gold tier", an escalation "Tier 1"). Any
  difficulty measure we use is ours, and has to be defined and frozen by us.
- **The tasks are Python, not JSON**: `automationbench/domains/<domain>/tasks.py`
  builds a list of dicts and calls `Dataset.from_list`. `wb corpus import-ab`
  already goes through `get_domain_dataset(domain)`, so the six scored domains
  need no new reader — only permission to name them.
- **The 42 services the six scored domains seed are already all among the
  product's 47.** Measured: `finance, hr, marketing, operations, sales, support`
  together touch 42 distinct services in their `initial_state`, and the set
  difference against `config/products/simulated-apps.yaml`'s `services` list is
  **empty**. So the product file and `config/side-effects.yaml` need no new
  service for this feature. (The five never seeded by the scored domains are
  `basecamp3`, `facebook_conversions`, `facebook_lead_ads`, `linkedin_ads`,
  `linkedin_conversions`.)
- **The difficulty measure separates the domains cleanly.** With
  score = services touched + expected changes + tools needed, the medians are:
  `simple` 4, finance 10, hr 12, marketing 12, operations 12, sales 13,
  support 15. Over all 800 tasks the terciles fall at **9** and **12**.

That last figure carries a warning that the spec must state: because `simple`
scores 3–9 and the scored domains score 5–26, the lower tercile is nearly all
`simple` and the upper tercile is nearly all scored-domain tasks. The stratified
draw (§5) is what stops "simple tier" from silently meaning "the `simple`
domain" — and the honest reading is that these tiers are *partly* a proxy for
domain. The alternative in §3 is exactly that objection made explicit.

## 3. Decisions taken in the brainstorm

| Decision | Choice | Why |
|---|---|---|
| How difficulty is split | **Three tiers of 10 prompts each, run as separate rounds** against the same competitors, plus a 10-prompt random draw. | Four numbers with error bars beat one blended number. Separate rounds keep every round at smoke scale and let Carlos approve them one at a time. |
| Why not AutomationBench's method | The official leaderboard's hard set is the ten hardest per domain, on a private set we do not have. We take terciles over our whole corpus instead. | Terciles give the shape of the difficulty curve; the top ten give one point on it, and we cannot reproduce their private set anyway. |
| The difficulty measure (**default**) | **score = number of services touched (`initial_state` keys, excluding `meta`) + number of expected changes + number of tools needed (`zapier_tools`)**, computed from the task JSON. Tiers = terciles over the whole corpus (200 `simple` + 600 scored). | Objective, computed from files that are already frozen by hash, reproducible by anyone with the repo, and it needs no judgment call per task. Every input is already in the task file. |
| The alternative considered | **Domain as the proxy**: `simple` = simple, {finance, hr} = medium, {marketing, operations, sales, support} = complex. | Simpler to explain and it is the vendor's own grouping. Rejected as the default because the domains overlap heavily on any real measure (marketing spans 6–18) and because it would make "tier" and "domain" the same variable, so a tier difference could never be told apart from a domain difference. It stays on the table as the fallback if the measure does not survive review. |
| Confirming the measure | **Open question, to be closed by Carlos and Lucas before the draw is made and frozen.** The command exists and is testable before it is answered; the drawn sets are not committed until it is. | Rule 5 (frozen by hash before any competitor runs) plus §IV pre-registration: the classification is part of the task set, so agreeing it after seeing results would be exactly the edit the constitution forbids. |
| How the sets are made | A new **offline** command `wb corpus tiers --seed N [--per-tier 10]` writes four task folders and one manifest. Same seed → identical bytes. | The draw has to be reproducible by a reader, not just by us. A recorded seed and a deterministic draw make the sets an artefact anyone can rebuild. |
| Stratification | The 10 prompts of each tier are spread **as evenly as possible across the seven domains** present in that tier, in a fixed domain order, then filled from the remaining tasks of the tier. | Without it the complex tier would be drawn overwhelmingly from `support` and the simple tier entirely from `simple`, and "difficulty" would just be "domain" under another name. |
| The random set | 10 prompts drawn from the **whole** corpus with the same seed, no stratification, no tier filter. | It is the control: if the blended average over these ten does not sit between the tiers, either the measure or the draw is wrong, and we want to see that. |
| Freezing | Every drawn task is **copied** into its folder exactly as it is in the corpus, with its `contract_sha256` unchanged; the manifest records every task's score, tier, domain and hash. No prompt, no starting data and no approval rule is edited. | Rule 5. A copy that changed one byte would be a different task with the same name — the worst possible failure mode. |
| What the tasks gain | `info.tier` and `info.domain`, added **to the copies in the drawn folders**, so a report can group by them. | Feature 006 (the HTML report) needs to group by tier and domain without re-reading the manifest. Two fields the grader ignores. |
| The hash question that raises | These two fields are **excluded from the contract hash**, so a drawn copy carries the same `contract_sha256` as its corpus original and rows stay comparable across sets. | Otherwise adding a label would make every drawn task a new task, and a corpus round and a tier round could never be compared. The hash covers what the competitor must do; a label is not that. |
| Approval rules for the new domains | Derived by the existing `wb corpus declare` with the existing reviewed side-effect list. No new machinery. | It is what F4/F5 already did for the 200 `simple` tasks, and the scored domains have the same field shape. Unmapped assertion types are reported loudly and are the review queue. |
| New services | **None needed.** All 42 services the scored domains seed are already in the product's list of 47. Measured, not assumed. | Nothing to add to `config/products/simulated-apps.yaml` or `config/side-effects.yaml` for this feature. Unmapped assertion types may still appear and are handled as F4 handles them. |
| The plans | One per set: `tier-simple`, `tier-medium`, `tier-complex`, `random-10`. Same competitors and baseline as `pilot-monarch-create-run`, **attempts per prompt and competitor: 2**, `mode: create-run` first. | Same competitors is what makes the four rounds comparable to each other and to the pilot. Run-only variants come after feature 004 lands. |
| Aggregating the four rounds | **Out of scope.** Each round gets the report it gets today. The view across the four sets is feature 006. | This feature's job is to produce comparable sets and the data to group by; drawing them together is a reporting feature. |
| Wording in every document | "attempts per prompt and competitor: 2; prompts: 10; **attempts per competitor: 20 = 10 × 2**". Never only the per-competitor total. | Carlos's rule: a bare "20 attempts" hides whether that is ten prompts twice or twenty prompts once, and the two mean different things for error bars. |

## 4. Importing the six scored domains

```
wb corpus import-ab --domains all --dest corpus/imported-<domain>
wb corpus declare corpus/imported-<domain> --overwrite --product simulated-apps
wb corpus validate corpus/imported-<domain>
```

`--domains` already accepts a comma list and goes through
`get_domain_dataset()`. It gains the word `all`, meaning the six scored domains
plus `simple` — the vendor's own `PUBLIC_DOMAINS` plus the baseline one — and it
gains a per-domain destination so the folders stay separate
(`corpus/imported-finance`, …). Nothing about the conversion changes: the rows
carry `zapier_tools`, `initial_state`, `assertions` and `task_name`, and no
`expected_changes`, exactly as `simple` did.

The declare step is where the approval rules come from. Expect unmapped
assertion types: the map in `wb_orchestrator/declare.py` was built for `simple`'s
assertion vocabulary, and the scored domains are broader. An unmapped type is
loud, blocks nothing else, and is the review queue for Lucas — the same
discipline F4 set. A task whose assertions are entirely unmapped has no derived
approval rule and **must not** enter any drawn task set.

## 5. The draw: `wb corpus tiers`

```
wb corpus tiers --seed N [--per-tier 10] [--corpus DIR ...] [--out DIR]
```

Offline, no keys, no model money. Deterministic: the same seed over the same
corpus produces byte-identical folders and manifest.

1. **Score** every task in the corpus:
   `len(initial_state keys except "meta") + len(expected_changes) + len(zapier_tools)`.
2. **Cut** at the terciles of the whole corpus's scores (measured today: 9 and
   12). Ties at a cut point go to the lower tier, so the cut is a rule, not a
   coin flip.
3. **Draw** 10 per tier, stratified by domain: walk the domains present in the
   tier in a fixed order, taking one task at a time from each (each domain's
   candidates shuffled by the seed) until 10 are held.
4. **Draw** 10 more from the whole corpus, unstratified, with the same seed.
5. **Write** `tasks/tier-simple/`, `tasks/tier-medium/`, `tasks/tier-complex/`,
   `tasks/random-10/` as copies of the corpus files with `info.tier` and
   `info.domain` added and `contract_sha256` untouched, plus
   `tasks/tiers-manifest.yaml`.

A task with no derived approval rule, or whose embedded hash does not match its
content, is excluded from the candidate pool and named in the command's output.
Refusing to draw silently from a broken corpus is the point.

The manifest records the measure in words, the cut points, the seed, the corpus
folders and their task counts, and one row per **drawn** task with its score,
tier, domain and contract hash. Someone with the repo and the manifest can
rebuild the four folders and diff them.

## 6. The four rounds

Four plans, identical but for their task set:
`config/plans/tier-simple.yaml`, `tier-medium.yaml`, `tier-complex.yaml`,
`random-10.yaml`. Each: `mode: create-run`, the seven competitors of
`pilot-monarch-create-run`, baseline `claude-opus-5/api`, `audience: internal`,
a cost ceiling, `approved_by: null`.

Each round is **prompts: 10; attempts per prompt and competitor: 2; attempts per
competitor: 20 = 10 × 2; competitors: 7; attempts in the round: 140.** Every one
of the four needs Carlos's approval of that specific run, with the attempt count
and a cost band, as §IV requires. Nothing in this feature runs them.

## 7. Testing and verification

Offline, no keys:

- Scoring: a hand-built task with two services, three expected changes and four
  tools scores 9; `meta` in `initial_state` is not counted.
- Terciles: a synthetic corpus with known scores cuts where arithmetic says, and
  a tie at a cut point lands in the lower tier.
- Determinism: two runs with the same seed produce byte-identical folders and
  manifest; a different seed produces a different draw.
- Freezing: every drawn file's `contract_sha256` equals its corpus original's,
  and adding `info.tier` / `info.domain` does not move the hash.
- Stratification: over a corpus with seven domains in a tier, the drawn ten cover
  as many domains as the counts allow, and the shortfall is filled from the rest.
- Exclusion: a task with no approval rule, and a task whose embedded hash does
  not match, are both left out and named.
- Import: a fake dataset for a scored domain converts with the same field
  handling as `simple`, and `--domains all` names the seven.
- Plans: the four load and validate; the mode is supported by product and
  harness; the attempt arithmetic printed by `wb run`'s banner reads
  "10 prompts × 2 attempts per prompt and competitor × 7 competitors = 140".

No live gate belongs to this feature. The rounds that use its output are gated
one at a time, and the import and the draw cost nothing.

## 8. Open questions

1. **Confirm the difficulty measure** (services + expected changes + tools, with
   terciles at 9 and 12) with Carlos and Lucas **before the draw is frozen and
   committed**. The alternative on the table is domain-as-proxy. Owner: Carlos
   and Lucas. Blocks committing the drawn sets, not the code.
2. **Lucas's AutomationBench patches** (`1.0.6+evalrepair.10`) are not upstream
   and may change scored-domain tasks. If they land after the draw, the affected
   tasks' hashes change and the drawn sets must be redrawn — old rows would not
   regrade. Better to get them from Lucas first. Owner: Lucas. Already open in
   `PLAN.md`; this feature raises its cost.
3. **Which services the scored domains need beyond the 47** — measured today as
   **none**: all 42 services they seed are already listed. Worth re-checking
   after Lucas's patches, since a patched task could seed a new service. Owner:
   Carlos, re-run the check.
4. **Unmapped assertion types in the six scored domains** — how many, and does
   `declare.py`'s map need extending before the draw. Answerable offline by
   running the import and the declare; a task with no rule is excluded from the
   pool either way. Owner: Carlos, then Lucas signs off on any map extension.
5. **The pilot tasks' manual approval rules** (`PLAN.md` F6) are still not the
   derived ones. The drawn sets use derived rules throughout, so a tier round and
   the pilot round are not rule-identical until F6 lands. Owner: Lucas. Existing
   open question; noted here because it now affects comparability.

## 9. Documents that change

- `monarch-benchmark/PLAN.md`: WS-F gains the import and the draw; a new
  deliverable for the tiered rounds; the decisions log gains the measure and the
  separate-rounds choice; the open questions above.
- Project `CLAUDE.md`: the "What lives where" table and the status paragraph.
- `workflowbench/config/README.md`: the four plans and the manifest.

## 10. Out of scope

The aggregate view across the four rounds (feature 006, the HTML report), the
rounds themselves (each needs its own approval), run-only variants of the four
plans (after feature 004), extending the scripted answer key to the scored
domains' assertion types (`PLAN.md` F7), the second product under test, and any
change to a task's prompt, starting data or approval rule.
