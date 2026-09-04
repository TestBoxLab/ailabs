# Data Model: Monarch in Run-Only Mode

Plain names in files; code identifiers in parentheses where they differ. Only
what feature 004 adds or changes; everything else is feature 002's data model.

## 1. Recipes file `config/products/simulated-apps.monarch-recipes.yaml` (`MonarchRecipes`)

Written only by `wb monarch recipes`; read by `resolve()` when the plan's mode is
`run-only`.

```yaml
product: simulated-apps
tasks: tasks                       # the task set these recipes were made for
generated_at: 2026-09-04T12:00:00Z
kb_hash_file_sha: 9f2c…            # sha256 of simulated-apps.monarch-kb.yaml's content
monarch: monarch@1a2b3c4           # the build that authored them
recipes:
  simple.sf_contact_email:
    workflow_id: 0b7e…
    recipe_version: 3
    authored_at: 2026-09-04T12:03:11Z
    attempts_used: 1
  simple.sf_opp_stage:
    workflow_id: 4c19…
    recipe_version: 2
    authored_at: 2026-09-04T12:09:40Z
    attempts_used: 3
missing:
  simple.sf_opp_closed_won:
    reason: checker_failed
    attempts_used: 3
    detail: "invariant failed: is_closed, is_won changed"
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `product` | str | yes | must equal the product under test |
| `tasks` | str | yes | the task set; must equal the plan's |
| `generated_at` | str | yes | when the file was last written; **not** part of the run's hash |
| `kb_hash_file_sha` | str | yes | fingerprint of the knowledge-base file the recipes were made against |
| `monarch` | str | yes | the competitor name of the build that authored them, for provenance |
| `recipes` | map | yes | task id → recipe row; may be empty only if `missing` is not |
| `missing` | map | yes | task id → missing row; may be empty |

**Recipe row**: `workflow_id` (str), `recipe_version` (int), `authored_at` (str),
`attempts_used` (int ≥ 1).

**Missing row**: `reason` (one of `checker_failed`, `authoring_error`,
`run_error`, `timeout`, `infra`), `attempts_used` (int), `detail` (str).

Validation on load: every key in `recipes` and `missing` is a task of the task
set; no task appears in both; the union need not cover the task set (a task in
neither is simply not yet attempted, and the run refuses on it as missing).

In the run's configuration hash: `product`, `tasks`, `kb_hash_file_sha`,
`recipes` (whole rows) and the **keys** of `missing`. Not `generated_at`, and not
a missing row's `detail` — the reason text must not make a resume refuse.

## 2. Plan `config/plans/pilot-monarch-run-only.yaml` (`Plan`)

Same schema as feature 001. Values: `mode: run-only`, `tasks: tasks`,
`repetitions: 2`, `timeout_s: 900`, `concurrency: 4`, competitors
`[{harness: oracle}, {model: kimi-k3-fireworks, harness: api},
{model: glm-5.3-fireworks, harness: api}, {model: claude-opus-5, harness: api},
{model: gpt-5.6-terra, harness: api}, {model: gpt-5.6-sol, harness: api},
{harness: monarch}]`, `baseline: claude-opus-5/api`, `audience: internal`,
`cost_ceiling_usd: 40`, `approved_by: null`.

## 3. Harness and product `modes`

`config/harnesses/monarch.yaml`: `modes: [create-run, run-only]`.
`config/products/simulated-apps.yaml`: already `[full-flow, create-run,
run-only]`; unchanged. A plan naming a mode either does not support already fails
validation (feature 001).

## 4. Run configuration (`RunConfig`), additions

| Field | Meaning |
|---|---|
| `monarch_recipes` | the loaded recipes file; `None` unless the plan's mode is `run-only` and a Monarch competitor is present |
| `excluded_tasks` | task id → reason, for the tasks dropped because they have no recipe; empty otherwise |

`tasks` is already the resolved task set; in run-only it is the task set **minus**
`excluded_tasks`, for every competitor. `_hashed()` adds `monarch_recipes` as in
§1 when it is present.

## 5. Attempt result (`ArmResult` → `EpisodeRow`), run-only values

`EpisodeRow` is unchanged. Differences from a create + run row:

| Row field | Run-only value |
|---|---|
| `test_mode` | `run-only` |
| `phases` | `execution` only — **no `authoring` key**, absent rather than zero |
| `error` | the create + run details minus every authoring one, plus `workflow_gone`, `run_still_active` |
| `termination` | `completed`, `agent_error`, `timeout`, `infra:monarch_setup`, `infra:harness_crash` (`infra:monarch_llm` cannot occur: nothing authors) |
| `flags` | as create + run, minus `questions_asked` (nothing is asked) |
| `turn_log[0]["monarch"]` | `bench_episode_id`, `workflowId` (from the recipe row), `recipeVersion`, `runId`; no `recipeRunId` |
| `cost_usd`, `tokens` | engine cost only, from the execution trace |

## 6. Recipes command result (`RecipeOutcome`, in `wb_orchestrator/monarch_recipes.py`)

One per task, printed and then folded into the file:

| Field | Meaning |
|---|---|
| `task_id` | the task |
| `passed` | whether a recipe was kept |
| `workflow_id`, `recipe_version` | the kept workflow, when passed |
| `attempts_used` | how many authoring attempts were made |
| `reason`, `detail` | why it failed, when not passed |
| `cost_usd` | what the task's attempts cost, summed, so the command can report the total |
| `deleted` | the workflow ids of the attempts that did not pass |

## 7. Fake Monarch scenario additions (`tests/fake_monarch.py`, `Scenario`)

| Field | Meaning |
|---|---|
| `workflows` | workflow id → `{recipeVersion}` served by `GET /api/workflows/:id`; an id absent from it answers 404 |
| `active_run_for` | workflow id → how many run requests are refused with `RUN_ALREADY_ACTIVE` before one is accepted |
| `active_run_never_clears` | the workflow's run polls as running forever, so the bounded wait expires |

Existing fields (`frames`, `run_refusal`, `run_outcome`, `engine_calls`,
`delete_fails_once`, …) are unchanged and still drive the create + run path the
recipes command uses.

## 8. State transitions of one run-only attempt

```
acquire lock → start front door
→ (if a run is active on the recipe) poll it to terminal, bounded
      still active ──► infra:monarch_setup (retried)
→ execution: POST :id/run {mode: live}
     404 ──────────► infra:harness_crash, not retryable (workflow_gone)
     refused{code} ─► infra:monarch_setup | agent_error:run_refused
     accepted ─────► poll runs/:runId
         succeeded ──► completed
         failed ─────► agent_error:run_error
         (deadline) ─► timeout, run left in flight, recipe kept
→ always: stop front door → release lock            (NO delete: the recipe is reused)
→ cost: read the execution trace (never changes the termination)
```

## 9. State transitions of one task in `wb monarch recipes`

```
task has a recipe for this knowledge base ──► skip, no model call
otherwise, up to N times:
    fresh world → create + run attempt (authoring + execution)
      → snapshot → checker
          passed ──► keep the workflow, write the recipe row, stop
          failed ──► delete the workflow, next attempt
N exhausted ──► write a missing row with the last reason
```
