# Research: Monarch in Run-Only Mode

Phase 0 of `/speckit-plan`. Every decision below was checked against the code in
this repo (`monarch-benchmark/workflowbench/`), the Monarch checkout
(`C:\Users\cgmat\Desktop\TestBox\monarch`) and its notes in
`local-docs/benchmark/benchmark-access.md`. Design decisions from the brainstorm
(design §2) are taken as given and not re-argued.

## R1. There is no way to create a workflow from recipe data

**Finding**: `benchmark-access.md` §5 states it plainly and the controller
confirms it: workflow creation happens only inside the recipe-agent job.
`POST /api/workflows/:id/versions` saves a **new version of an existing**
workflow, is marked unverified, refuses version-1-shaped recipes, requires
exactly one report node last, and 409s on a stale base version.

**Decision**: authoring is the only creation path, so a known-correct workflow is
made once by authoring and then **kept**. The versions route is not used at all.

**Rationale**: using an unverified write route to pin a recipe risks corrupting
the one artefact the whole mode depends on, to solve a problem — "is this still
the recipe we froze?" — that a read answers.

**Alternatives considered**: the database-direct seed script
(`apps/backend/scripts/seed-workflow-runs.ts`) — rejected: it writes a
version-1-shaped demo recipe that the run route refuses, and reaching into
Monarch's database from the bench would break the "drive the product through its
own API" premise of feature 002.

## R2. Where the recipes come from

**Decision**: `wb monarch recipes` drives the **existing create + run attempt**
(`MonarchArm` in `create-run` mode) up to three times per task, on a fresh
`Episode` each time, and grades each result with the bench's own checker. First
pass wins; the rest are deleted.

**Rationale**: FR-002 requires the checker to decide, and the checker only reads
snapshots the bench took (rule 3). The create + run arm already produces exactly
that. Writing a second authoring path would duplicate the lock, the front door,
the SSE reading, the cost read and the cleanup — and would be the thing that
rots when create + run changes.

`# ponytail: the command drives the arm as-is rather than factoring out an
"author one workflow" helper; the ceiling is that a change to the create + run
lifecycle is felt here too, which is the intent.`

**Alternatives considered**: hand-writing recipes from each task's answer key
actions (`PLAN.md` §1.4 mentions converting the oracle) — rejected: a recipe a
person wrote is not the product's work, so measuring the engine on it measures
something Monarch never produces. It would also need a creation route that does
not exist (R1).

## R3. Verifying a recipe is still the one that was frozen

**Decision**: `GET /api/workflows/:id` per recorded recipe, comparing
`recipeVersion`. A 404 means the workflow is gone.

**Rationale**: the route exists and returns what is needed — verified in
`monarch-enterprise/apps/backend/src/workflows/workflows.controller.ts`:
`@Get(':id')` returns the workflow detail plus `productAccess`, and the detail
carries `recipeVersion: number | null` (the latest version's number). This
settles the open question the design carried: `GET /api/workflows/runs/...` is
indeed not enough (it describes a past run, not the current recipe), but the
workflow read route makes that irrelevant.

**Alternatives considered**: `GET /api/workflows/:id/versions` (a list; more data
than needed) and comparing the recipe body itself (needs a canonical form and
would fail on harmless reformatting).

## R4. `RUN_ALREADY_ACTIVE`

**Finding**: Monarch allows one active run per workflow and refuses a second with
`409 RUN_ALREADY_ACTIVE` (`benchmark-access.md` §5). There is **no run-cancel
route**; `DELETE /api/workflows/:id` is what feature 002 uses to stop a run in
flight, and run-only must not delete.

**Decision**: before starting a run, and on a refusal, poll the workflow's runs to
a terminal state for a bounded time (60 s, one poll every 2 s, reusing the
existing poll interval), then start. Still active after the bound →
`InfraError("infra:monarch_setup", retryable=True)`, which the orchestrator
already retries and excludes from the denominator.

**Rationale**: the global lock means the only way to meet an active run is a
leftover from a previous attempt that hit its deadline (FR-021). Waiting is the
only cure available, and a bounded wait cannot hang the run.

`# ponytail: a fixed 60 s bound, not a configurable one; the upgrade is a
harness field if a real workflow ever legitimately runs longer than a bench
attempt's deadline.`

## R5. Renaming the kept workflow

**Finding**: no rename route exists. `@Patch(':id')` in
`workflows.controller.ts` builds its patch from `status`, `triggerKind`,
`scheduleCron`, `scheduleTz`, `overlapPolicy` and `requiresApproval` only; a
`name` in the body is ignored.

**Decision**: the `bench:<task_id>` name is recorded on the bench side, in the
recipes file, and the command says so. No rename call is made — an ignored call
that prints "renamed" would be a lie in the log.

**Open**: whether Deyton would accept `name` on that patch, so a person opening
Monarch can tell the benchmark's workflows apart (spec Open Question 1).

## R6. Excluding tasks with no recipe

**Decision**: `resolve()` drops them from `RunConfig.tasks` when the plan's mode
is run-only, before any competitor is built, and records the dropped tasks with
their reasons on the `RunConfig` so the banner and the report can state them.

**Rationale**: rule 7 (paired comparisons only on identical sets). Dropping per
competitor is the bug this prevents by construction: it would leave Monarch on
eight tasks and the raw models on ten, and every pairwise figure would be wrong
without any error appearing.

`# ponytail: exclusion in one place, at the top; per-competitor filtering is
what rule 7 forbids, not an optimisation left undone.`

**Alternatives considered**: refusing the run whenever any task is missing —
rejected: a single stubborn task would block the pilot indefinitely, and a stated
exclusion is honest and comparable. A run with *every* task missing still refuses
(FR-031), because there is nothing left to compare.

## R7. The absent authoring phase

**Decision**: run-only does not set `res.phases["authoring"]` at all.

**Rationale**: `PhaseMetrics` with zeros would be averaged by the report as a
real phase that took no time, which is a different claim from "this mode has no
authoring". `EpisodeRow.phases` is a mapping and every consumer iterates over
what is present, so an absent key needs no downstream change — confirmed by
reading `runner/schema.py` and `wb_report/report.py`.

## R8. Cost for a run-only attempt

**Decision**: the same `langfuse_cost` reader, called the same way, with the
attempt identifier the bench sends on the run request. The trace-id shortcut
feature 002 uses — collecting `traceId` from the authoring stream's frames — has
no source here, so run-only relies on the metadata fallback
(`bench_episode_id`), which the reader already supports as its primary filter.

**Rationale**: `MonarchArm._add_cost` already passes `trace_ids=self._trace_ids
or None`, so an empty list falls back with no code change. The execution trace is
`workflow.run`, tagged from the `x-bench-episode-id` header on
`POST /api/workflows/:id/run`, which the telemetry contract of feature 002
already requires.

**Consequence for the pilot**: a run-only attempt's cost is engine cost only.
The report's source line must not present it beside a create + run cost as if
they measured the same thing.

## R9. Configuration and hashing

**Decision**: `MonarchRecipes` mirrors `MonarchKb`: a dataclass, a loader that
validates against the product and the task set, a field on `RunConfig`, and an
entry in `_hashed()` added **only when the plan's mode is run-only**, so existing
plans' hashes do not move and the earlier runs stay resumable.

**Rationale**: the same discipline feature 002 used for the knowledge base, for
the same reason (rule 11 without breaking resume of what already ran).

The recorded `kb_hash_file_sha` is the sha256 of the knowledge-base file's
content, not of its parsed mapping: it is a fingerprint for "were these recipes
made against this file", and the file's own loader already validates the
mapping's shape.

## Unknowns carried as open questions (not blocking offline work)

1. A `name` field on the workflow patch route (cosmetic; owner Deyton).
2. Confirmation that a recipe cannot change without an explicit save (would close
   the drift question for good; owner Deyton).
3. A run-cancel route (would replace the bounded wait of R4; owner Deyton).

Carried from feature 002, blocking the live steps only: the model-provider
permission for Monarch's authoring account, which `wb monarch recipes` needs, and
the product grant mechanism.
