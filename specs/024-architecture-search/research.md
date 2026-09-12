# Phase 0 research: the search loop

**Feature**: 024-architecture-search | **Date**: 2026-09-11

The spec carries no unresolved clarifications — Lucas closed all four open questions on
11 September. This file resolves the *technical* unknowns: for each requirement, what
already exists, what is genuinely missing, and what the cheapest correct repair is.
Every finding was established by reading the code, not by inference from documents.

The governing bias is constitution *Additional Constraints*: reuse what is in-repo,
stdlib before dependencies, shortest working diff after full comprehension.

---

## R1 — The front door cannot simply be authenticated

**Decision**: Gate the proxy with an unguessable per-run path segment carried in the
seed URL. Do not add credentials.

**Rationale**: `/front-door` is deliberately open because **the competitor under test
calls it**. `wb_studio/app.py:848` documents it: "A hosted Studio is the only address
Monarch can reach, so the seeds name `https://<studio>/front-door`… Like the tunnel it
replaces there is no login and no origin check on this path."

The docstring then claims "the shim itself accepts only its episode's world calls." That
claim does not hold. `X-Bench-Episode-Id` is forwarded (`app.py:862`), but in
`wb_arms/http_shim.py` `episode_id` appears only at line 69 and line 78 — both inside
the access-log writer — and at line 233 in a manual-run constructor. **It is never
validated.** The shim serves one episode; it does not authenticate its caller.

So the reachable defect is real: `do_GET`/`do_POST` check `is_front_door()` at
`app.py:901` and `app.py:1171` *before* `authorised()` at `app.py:903` and `app.py:1173`,
and `do_PUT`/`do_PATCH`/`do_DELETE` (`app.py:882-889`) exist only to serve the front door
and never call `authorised()` at all. An anonymous `DELETE` lands in the running
attempt's world, and the approval rule scores it as the competitor failing.

Adding Basic Auth or a Studio token breaks every Monarch round, because Monarch has
neither. The seed URL is already per-round configurable —
`wb_orchestrator/monarch_setup.py:66` `public_front_door_url`, `monarch_setup.py:144`'s
`--front-door` argument, and `wb_world/seeds.py:2811` templating `front_door` into the
seeds — so a secret path segment is free on Monarch's side and unguessable from outside.

**Alternatives considered**:
- *Validate `X-Bench-Episode-Id` at the shim.* Rejected: episode ids appear in logs and
  reports and are not secrets.
- *Origin or IP allowlist.* Rejected: Monarch calls from Railway's egress, which is not
  a stable address the lab controls.
- *Bearer token in the `Authorization` header.* Workable — the header is already
  forwarded — but it changes what Monarch must send, and the seed URL does not.
- *Take the proxy off the public Studio entirely.* Rejected: the hosted Studio is the
  only address Monarch can reach, per the same docstring.

---

## R2 — Per-phase cost already exists; the measures layer discards it

**Decision**: Carry the existing `by_phase` breakdown onto the result row and teach
`measures` to read it. Build no new telemetry.

**Rationale**: `wb_arms/langfuse_cost.py:14` defines `PHASE_SPANS`, mapping
`recipe.triage`, `recipe.select`, `recipe.plan`, `recipe.critic` and `recipe.review` to
**authoring**; `engine.run` and `engine.step` to **execution**; `discovery.run` to
**discovery**. `_phase_of` (`langfuse_cost.py:95`) walks up `parentObservationId` to the
first named span, cycle-safe. `CostSummary.by_phase` (`langfuse_cost.py:48`) holds
phase → family → tokens and cost. `summarize` fills it (`langfuse_cost.py:219`) and
derives `total_usd` from it (`langfuse_cost.py:230`). `wb_arms/monarch.py:453` already
writes `cost.by_phase` into `res.turn_log`, and `monarch.py:463` and `:476` already
iterate it. Tests assert it (`tests/test_langfuse_cost.py:91-94`).

What is missing is downstream only: the result row exposes a single settled cost, and
`wb_studio/measures.py:127` `cost(rows)` sums that one number. Nothing splits, and
nothing builds a curve.

This corrects a claim made during the 11 September brainstorm that no per-phase cost
existed anywhere; the earlier search looked for `phase_cost` and `cost_by_phase` and
missed `by_phase`. The requirement is materially cheaper than it appeared.

**Alternatives considered**:
- *Split by timestamp at the authoring boundary.* Rejected as unnecessary — the span
  contract is more precise than a wall-clock cut and already handles interleaving.
- *New phase telemetry in Monarch.* Rejected: `PLAN.md:143` already records D10 as
  merged into feature 002 for exactly this reason.

**Open**: only Monarch reports phases. A raw-API or native-harness competitor has no
authoring phase at all, which is the point of the comparison — its cost is all
per-request. Those competitors report authoring cost as **not applicable**, distinct from
unknown, per `AI-LABS-DIRECTION.md:82`.

---

## R3 — Time has no phase split and needs one

**Decision**: Record authoring end as an explicit timestamp on the Monarch attempt and
derive the two durations from it.

**Rationale**: `wb_studio/measures.py:144` `time(rows)` computes quantiles over one
duration per attempt. Unlike cost, no phase-aware source exists: `_author`
(`wb_arms/monarch.py:660`) and `_start_run` (`monarch.py:773`) are separate calls with a
clean boundary between them, but nothing records when the first ended. This is the one
place in FR-024/FR-025 that needs a new recorded value, and it is a single timestamp.

**Alternatives considered**:
- *Derive from Langfuse span timings.* Rejected: it makes a local, certain fact depend
  on a remote service that `_add_cost` already treats as optionally unavailable.

---

## R4 — Stratification can use the existing structural measure

**Decision**: Stratify on the measure `wb corpus tiers` already uses, recorded in the
manifest with a version.

**Rationale**: `tasks/tiers-manifest.yaml` states the measure in its own words: seeded
services (`initial_state` keys except `meta`) + expected changes
(`info.expected_changes`) + tools needed (`info.zapier_tools`), computed from the task
file, with tiers as **the terciles of the whole corpus**. Because it is computed from
the task file it is available for all 800 corpus tasks across the seven imported domains
(finance, hr, marketing, operations, sales, simple, support), not only the 40 recorded
in the manifest. Domain is the corpus directory, already carried per task.

`AI-LABS-DIRECTION.md:102` calls this "only a structural proxy" and asks for a versioned
classification later, which is why FR-033 requires the manifest to name the measure and
its version.

Note that `wb_studio/difficulty.py` is a **different** measure — empirical failure rate
over comparable attempts, `unrated` with zero attempts. With nine runs it would leave
nearly the whole corpus unrated, so it cannot drive the split. It stays what it is.

**Alternatives considered**:
- *Stratify on empirical difficulty.* Rejected: insufficient data, and it would leak
  outcome information into the split, which is precisely what a held-out slate exists to
  prevent.

---

## R5 — Cohort keying already exists in a module nothing calls

**Decision**: Make `report_data` use `leaderboard`'s cohort key. Delete the weaker one.

**Rationale**: `wb_studio/report_data.py:408` keys a cohort on sorted task hashes plus
track. `wb_studio/leaderboard.py:50` keys the same idea on task hashes, track, judge,
assistance, world manifest and workflow contract, and `leaderboard.py:57` stamps an
unpinned cohort "Historical records lack a pinned judge; rankings are provisional."
The stricter partitioning is written and tested; the surface a person opens reimplements
a weaker one. FR-016 is a wiring job.

The same module holds `exclusion_reason()`, unused, which FR-012 needs.

**Alternatives considered**:
- *Strengthen `report_data`'s key in place.* Rejected: two implementations of one rule is
  how this defect arose.

---

## R6 — Rank and interval come from two different estimators

**Decision**: One estimator. Rank and the displayed interval both come from
`measures.pass_rate`'s Wilson bounds over attempts.

**Rationale**: `report_data.py:452` computes rank from `measures.pass_rate`'s Wilson
interval over attempts (`measures.py:60`), while `report_data.py:462` fills the
*displayed* interval from `leaderboard.uncertainty` (`leaderboard.py:140`), a Wald
interval over per-task shares that can return zero width. `static/reports.js:289` renders
the second beside a rank derived from the first. A zero-width 95% interval on a
benchmark page is the kind of error that ends trust in the page.

Wilson is correct for binary outcomes at small n, which is the lab's entire regime.
`wb_studio/difficulty.py` inlines a third copy of Wilson; it is deleted in favour of
`measures.wilson`.

---

## R7 — Two failure classifiers, one of which must go

**Decision**: `narrative.MODES` is the single classification. `failure_analysis` buckets
are derived from it or removed.

**Rationale**: `wb_studio/failure_analysis.py:36` `_bucket` and `wb_studio/narrative.py:174`'s
nine modes both classify every failed attempt, and `static/reports.js:168-193` renders
both inside the same section. On the lab's only ten-task run they disagree on all eight
failed attempts. `narrative` is the richer of the two — it carries the turning point and
the per-attempt evidence that `report_data.code_findings` already cites — so it is the
one that survives.

---

## R8 — The false-completion signal is computed from the lab's own prompt

**Decision**: Restrict the signal to competitor-produced output, and label it as inferred
from wording wherever it is shown.

**Rationale**: `measures.py:18` `DONE_CLAIM` matches `done|completed?|finished|success|
updated|created|sent|resolved|processed`; `measures.py:103` `false_completion` runs it
over `result["output"]`; `report_data.py:212` promotes the count to a top-five finding
with a flat assertion. When an agent hits its turn limit, `output` holds the request text,
so the match fires on the lab's own words. The phrase "wording heuristic" appears only at
`static/reports.js:191`, in a different section, under a chart — so the finding itself
reads as established fact.

This is the only finding in the report that accuses a competitor of dishonesty, which
sets the bar for how it must be sourced.

---

## R9 — The approval module is complete and unused

**Decision**: Wire `wb_orchestrator/approvals.py` into the Studio launch path. Write no
new approval logic.

**Rationale**: `approvals.py` implements decision D5 in full — operator, approvers,
pending requests, smoke-scale exemption. Nothing under `wb_studio/` imports it.
`POST /api/jobs` (`app.py:1285`) goes straight to `Studio.create` (`app.py:348`), which
accepts up to 800 tasks and 12 competitors at up to the whole weekly ceiling, and the
settings dict it builds (`app.py:433`) has no operator and no repetitions key.

`approvals.py:77` imports `wb_studio.enterprise`, so the benchmark currently depends on
the UI package. FR-007's wiring should invert that edge rather than deepen it.

---

## R10 — Run-only exists; recipes do not

**Decision**: Generate recipe data with the built command. Build no new mode.

**Rationale**: `wb_orchestrator/monarch_recipes.py` is 309 lines and complete;
`config/plans/pilot-monarch-run-only.yaml` declares `mode: run-only`;
`config/products/simulated-apps.yaml:14` lists all three modes. The only recipes file in
the repo is `tests/fixtures/monarch-recipes-sample.yaml`.
`STATE-OF-THE-PROGRAM.md` still lists feature 004 as "specified, not built" and is stale;
correcting that note is part of this feature's documentation work.

---

## R11 — The sizing formula and the test that settles disagree

**Decision**: Correct `genesis_hypotheses.smallest_plan` to size for the test that
actually decides the hypothesis — the paired sign test — and refuse below its floor.
Add no second sizing path.

**Rationale**: Two functions size and settle the same experiment, using different
statistics.

`smallest_plan` (`wb_studio/genesis_hypotheses.py:517`) computes
`n = ceil(4·p·(1−p)/d²)`, clamped to `max(10, …)` and capped at the population — a
two-proportion normal approximation for **independent** samples.

`settle` (`genesis_hypotheses.py:409`) and the round report both decide with
`measures.paired` (`measures.py:180`) → `measures.sign_test` (`measures.py:170`), a
two-sided sign test with **ties dropped**.

A paired sign test's power depends on discordant pairs, not on task count. Evaluating
`sign_test(n, 0)` over candidate n gives the minimum discordant pairs that can reach
p < 0.05: **six**, and below six no win count can. `smallest_plan`'s floor of ten tasks
therefore permits — and in practice recommends — experiments whose settling test can
never conclude, because ten tasks typically yield three or four discordant pairs.

The repair is to size against the sign test and state the assumed flip rate in the
refusal. It needs no new statistics; both functions already exist.

| Discordant pairs | Minimum wins for p < 0.05 |
|---|---|
| 2–5 | unreachable |
| 6 | 6 |
| 8 | 8 |
| 10 | 9 |
| 15 | 12 |

**Alternatives considered**:
- *Settle with a two-proportion test instead, matching the sizing.* Rejected: the lab's
  comparisons are paired on identical task sets by rule (`PLAN.md` §1.1), and a paired
  test is the stronger one. The sizing is what is wrong, not the test.
- *Add a separate power check beside `smallest_plan`.* Rejected: that is how the
  two-classifier and two-interval defects in R6 and R7 arose.

**Open**: the refusal needs an assumed flip rate to turn a task count into an expected
discordant-pair count. A conservative default stated in the refusal text is sufficient;
`smallest_plan` already derives an observed pass rate from coverage when one exists, and
the same source serves here.

---

## R13 — The experiment record already exists

**Decision**: Extend `genesis_hypotheses`' record with slate, repetitions, lineage and
power. Do not introduce a parallel experiment entity.

**Rationale**: The spec's "experiment record" is already implemented.
`check_hypothesis` (`genesis_hypotheses.py:41`) validates claim, population, a comparison
of two setups, measure, direction, minimum effect and an optional prior — and its
docstring states the governing rule, "The Studio computes every number; the model writes
none of them." `settle` (`:409`) produces `supported` with a certainty sentence.
`population_tasks` (`:226`), `coverage` (`:277`) and `measure_certainty` (`:384`) are the
surrounding machinery. `smallest_plan` (`:517`) already turns a record into a launch
payload with a priced ceiling, and already asks `genesis_autonomy.plan_lines` whether the
Studio would accept it.

What the record lacks is exactly the four fields this feature needs: which slate it runs
on, an explicit repetitions count, the lineage that enforces the once-only held-out rule,
and the power figures.

`TRACK.md` reports seven hypotheses proposed and zero tested, so the record has never
completed a cycle. That is a reason to finish it, not to replace it.

**Alternatives considered**:
- *A new `wb experiment` record.* Rejected — it would be the third parallel
  implementation pattern in this codebase, after the two failure classifiers and the two
  interval estimators. A CLI surface over the existing record is still worth adding,
  because today the record is reachable only through Genesis's tools.

| Discordant pairs | Minimum wins for p < 0.05 |
|---|---|
| 2–5 | unreachable |
| 6 | 6 | 
| 8 | 8 |
| 10 | 9 |
| 15 | 12 |

**Open**: the refusal needs an assumed flip rate to turn a task count into an expected
discordant-pair count. A conservative default stated in the refusal text is sufficient;
this does not need a prior.

---

## R12 — The research envelope must not be built before its accounting is correct

**Decision**: FR-005 lands and is verified before FR-035. This ordering is a hard
dependency in the plan, not a preference.

**Rationale**: FR-035 makes a standing weekly envelope the thing that admits paid
experiments without a person. Today that envelope cannot refuse: `genesis.py:548` tags
every conversation turn `by='person'`; `usage.py:23` maps `by=='person'` to "Studio
user"; `genesis_access.py:146` counts only lines whose author is Genesis — so
person-initiated Genesis turns are invisible to the envelope entirely. `usage.py:34`
sets the actual cost as soon as any child settles, so a running hold counts as its
settled pennies. Building a standing envelope on that accounting authorises unattended
spending against a gate that essentially never refuses.

---

## Dependencies

No new runtime dependencies. Everything above is stdlib or existing in-repo modules,
consistent with the constitution's stack constraint.
