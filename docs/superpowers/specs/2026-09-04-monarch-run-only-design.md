# Design · Monarch in run-only mode (feature 004)

Date: 4 Sep 2026 · Author: Carlos Mattos with Claude · Status: approved in brainstorm, awaiting `/speckit-specify`

This document records the design settled with Carlos on 4 Sep 2026. It feeds
`/speckit-specify` for feature 004. It changes none of the fixed rules in
`monarch-benchmark/PLAN.md` §1; it adds inputs (a recipes file, a plan, one new
mode on the product and the harness) and one new setup command. Feature 002
(create + run) is unchanged and is the machinery this feature reuses.

## 1. Goal

Measure **Monarch's engine alone**. `PLAN.md` §1.4 defines run-only as "a known-correct
workflow, engine measured alone": the workflow is not written on the clock, it is
handed to Monarch already built, and only the execution is timed, priced and graded.

Create + run answers "can Monarch turn this request into a working workflow and run
it?". Run-only answers the narrower question underneath it: "given a workflow that is
already correct, does the engine execute it correctly, how fast, and at what cost?" A
create + run failure can come from authoring or from execution; run-only separates the
two, and it is the mode a Monarch release-over-release comparison will use.

**Known-correct** has one meaning here and it is not "a human said so": a workflow that
Monarch itself authored once, off the clock, and that **passed the bench's checker** when
run against a fresh world. The answer key's approval rules decide; nothing grades itself
(rule 3). A workflow no attempt could get past the checker has no known-correct recipe
and its task leaves the run-only task set.

The deliverable is a paired pilot: the 10 pilot tasks × 2 repetitions ×
{answer key, five raw models, Monarch}, internal report — deliverable D9.

## 2. Decisions taken in the brainstorm

| Decision | Choice | Why |
|---|---|---|
| What "known-correct" means | A workflow Monarch authored once, off the clock, whose run **passed the checker** against a fresh world. Recorded per task. | Rule 3: the answer key's approval rules decide, not a person's opinion of the recipe. It also keeps run-only honest — the engine is measured on work the product itself produced. |
| How recipes are made | A new paid command `wb monarch recipes`, run once per task set and knowledge base. Up to N authoring attempts per task (default 3) through the **existing create + run flow**, each on a fresh world; the first that passes is kept. | The create + run attempt is already written, tested and correct. Reusing it is a branch, not a second implementation. |
| Where the recipe lives | Inside Monarch. The workflow is **not deleted**; `config/products/<product>.monarch-recipes.yaml` records `task_id → {workflow_id, recipe_version, kb_hash_file_sha, authored_at, attempts_used}`. | There is no HTTP route that creates a workflow from recipe JSON (`benchmark-access.md` §5): authoring is the only creation path, so the artefact has to be kept, not rebuilt. |
| Tasks with no passing recipe | Recorded as `missing` with the last reason, and **excluded from the run-only plan's task set for every competitor**. The report's source line says how many were excluded and why. | Rule 7: paired comparisons only on identical sets. Dropping a task for Monarch alone but not for the raw models would silently unpair the comparison. |
| Pinning the version | `POST /api/workflows/:id/versions` is **not used**. The `recipeVersion` returned by authoring is recorded and re-verified before each run. | That route is unverified, refuses v1 recipes and 409s on a stale `baseVersion` (§5 of the notes). Verifying a version we already have is cheaper and cannot corrupt the recipe. |
| Drift | The recipes file enters the run's config hash. Before the first run-only attempt the bench checks, per task, that `GET /api/workflows/:id` still answers with the same `recipeVersion`, and that the knowledge-base hash file is unchanged. Any drift refuses the run. | Rule 11: a different recipe or a different knowledge base is a different run, and a recipe that changed underneath us makes every earlier row non-comparable. |
| One attempt in run-only | Lock → front door → `POST /api/workflows/<workflow_id>/run {mode: live}` → poll → snapshot by the bench → **no delete**. Phase `authoring` absent; `execution` measured. | The recipe is reused across attempts and repetitions; deleting it would destroy the thing being measured. |
| `RUN_ALREADY_ACTIVE` | Infrastructure refusal, as in 002 — but handled first: one active run per workflow, so before starting, wait for any run in flight on that workflow to reach a terminal state, up to a bound; only then refuse. | The global lock already serialises attempts, so this can only be a leftover from a timed-out attempt. There is no run-cancel route, so waiting is the only cure. |
| Cost | Langfuse, as in 002, for the execution trace only. Trace ids come from the metadata fallback (`bench_episode_id`), because run-only has no SSE frames to read them from; the execution trace is `workflow.run`, tagged with the episode header. | Same rule 9 machinery, one fewer source. |
| Create + run | Unchanged. A new workflow per attempt, deleted at the end. | Two modes, two lifetimes; nothing in 002 moves. |
| Rule 2 in this mode | The raw models still get the OpenAPI tools; Monarch gets its fixed recipe. The spec states plainly that the comparison being made is "engine alone against models doing the whole task". | Rule 2 is "same knowledge **within a test mode**". Run-only's definition (§1.4) is exactly that asymmetry; the spec must say so rather than let a reader assume a like-for-like race. |

## 3. Setup, once per task set and knowledge base: `wb monarch recipes`

```
wb monarch recipes [--product] [--harness] [--plan|--tasks] [--attempts N] [--yes]
```

**This command spends model money.** It prints the number of tasks and a cost band and
refuses to start without `--yes` (or a plan whose `approved_by` is set). Idempotent: a
task that already has a recipe for the current knowledge base is skipped, so a rerun
after a partial failure costs only the missing tasks.

For each task, up to N attempts (default 3):

1. A fresh world and a front door, exactly as a create + run attempt.
2. The create + run flow authors a workflow from the task's request text.
3. The workflow runs; the bench snapshots the world.
4. The **bench's checker** grades that snapshot against the task's approval rules.
5. Passed → keep. The workflow stays in Monarch; the row is written to the recipes file.
   Failed → **delete the workflow** and try again, up to N.

After N failures the task is recorded as `missing` with the last reason
(`checker_failed`, `authoring_error: …`, `run_error: …`, `timeout`).

Naming: a kept workflow is renamed to `bench:<task_id>` if a rename route exists.
It does not (see §7): `PATCH /api/workflows/:id` accepts status, trigger, schedule,
overlap policy and approval only. So the name lives on the bench side, in the recipes
file, and the command says so rather than pretending.

## 4. One run-only attempt, step by step (`wb_arms/monarch.py`, mode branch)

Input: the task, a fresh world, a deadline, and the task's recipe row. Steps:

1. Take the global Monarch lock; start the front door on the fixed port, as in 002.
2. **No authoring.** `res.phases["authoring"]` is not set at all — an absent phase, not
   a zero one, so no report averages a phase that did not happen.
3. If a run is in flight on this workflow, poll it to a terminal state up to a bound
   (the leftover of a timed-out attempt). Still active after the bound →
   `infra:monarch_setup`, retried.
4. Execution clock starts. `POST /api/workflows/<workflow_id>/run {"mode":"live"}` with
   the episode header; poll `GET /api/workflows/runs/:runId` to a terminal status. The
   engine's REST calls land on the front door and mutate the attempt's world in
   process, so the final snapshot is the `Episode` itself, as in 002.
5. **No delete.** Stop the front door, release the lock, read cost from Langfuse.

Result mapping: the 002 table, minus every authoring row, plus:

| Outcome | Termination | Detail recorded |
|---|---|---|
| Run terminal normal | `completed` | `workflowId`, `runId`, `recipeVersion` |
| `RUN_ALREADY_ACTIVE` still active after the wait | `infra:monarch_setup` | how long it waited |
| The workflow is gone (404 on run) | `infra:harness_crash`, not retryable | names the task and the recipes file; rerun `wb monarch recipes` |
| Deadline hit during the run | `timeout` | the run is left in flight; there is no run-cancel route, and the workflow must not be deleted |

That last row is the one real difference from 002: a timed-out create + run attempt
deletes its workflow to stop the engine, and a run-only attempt cannot. It is what
step 3 exists to clean up.

## 5. Configuration

- `config/products/simulated-apps.monarch-recipes.yaml`, written by `wb monarch recipes`:
  one row per task with `workflow_id`, `recipe_version`, `kb_hash_file_sha` (the sha256 of
  the knowledge-base hash file's content, so a knowledge base change invalidates every
  recipe at once), `authored_at`, `attempts_used`; `missing` tasks with their reason.
  Enters the run's config hash.
- New plan `config/plans/pilot-monarch-run-only.yaml`: `mode: run-only`, the same
  competitors as `pilot-monarch-create-run` (oracle, kimi-k3-fireworks/api,
  glm-5.3-fireworks/api, claude-opus-5/api, gpt-5.6-terra/api, gpt-5.6-sol/api, monarch),
  baseline `claude-opus-5/api`, 10 pilot tasks × 2 repetitions, a cost ceiling,
  `approved_by: null`.
- `config/harnesses/monarch.yaml`: `modes` gains `run-only`. The product already lists it.

## 6. Testing and verification

Offline, against the existing fakes extended with the routes this mode needs
(`GET /api/workflows/:id`, a run already active, a workflow that is gone):

- The mode branch: no authoring request is ever sent in run-only, and `phases` has no
  `authoring` key.
- `wb monarch recipes`: a task that passes on the first attempt, one that passes on the
  third, one that never passes; the file's rows; a rerun skips what is present; the
  cost gate refuses without `--yes`.
- Drift: a changed `recipeVersion`, a changed knowledge-base hash file, a deleted
  workflow — each refuses before the first attempt, naming the task.
- Excluded tasks: a `missing` row removes the task from every competitor's set, and the
  report's source line states the count and the reason.
- `RUN_ALREADY_ACTIVE`: a run in flight is waited out, then the attempt proceeds; one
  that never ends becomes `infra:monarch_setup`.

Live, in order: `wb monarch recipes` for the 10 pilot tasks (**paid; needs Carlos's yes
with a cost band**), then the run-only pilot.

## 7. Open questions

1. **Rename route** — settled by reading the code, not left open: none exists.
   `PATCH /api/workflows/:id` accepts status, trigger kind, schedule, overlap policy and
   approval only (`workflows.controller.ts`). The `bench:<task_id>` name is bench-side.
   Worth asking Deyton whether adding `name` to that patch is acceptable, so a person
   opening Monarch can tell the benchmark's workflows apart.
2. **Pinning a version** — decided not to use `POST /api/workflows/:id/versions`;
   `recipeVersion` is verified instead. Still worth confirming with Deyton that a
   workflow's recipe cannot change under an org without an explicit save.
3. **Cancelling a run in flight** — there is no run-cancel route today. A timed-out
   run-only attempt leaves the engine working; the next attempt waits it out. If Deyton
   adds one, step 3 becomes a cancel and the bound goes away.

## 8. Documents that change

- `monarch-benchmark/PLAN.md`: B6 → feature 004; D9's definition of done; the decisions
  table gains "known-correct means a Monarch-authored workflow that passed the checker"
  and "run-only reuses one recipe per task; tasks without one leave the set"; the open
  questions above.
- Project `CLAUDE.md`: the "What lives where" table and the status paragraph.
- `workflowbench/config/README.md`: the recipes file and the new plan.

## 9. Out of scope

Full flow (feature 003), a Monarch-versus-Monarch release comparison (the mode makes it
possible; choosing and running it is a later plan), a scripted executor as a run-only
competitor (§1.4 names it; nothing here builds one), the second product under test, and
the Monarch-side changes of §7 (each its own pull request in the Monarch repository).
