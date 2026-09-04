# Contract: CLI additions

Feature 001's `wb run / resume / status / grade / report / corpus` and feature
002's `wb monarch setup` and `wb doctor` additions are unchanged. This feature
adds one command to the `monarch` group and changes what `wb run` does in
run-only mode.

## `wb monarch recipes`

```
wb monarch recipes [--product NAME|PATH] [--harness NAME|PATH]
                   [--plan NAME|PATH | --tasks DIR] [--attempts N] [--yes]
```

- `--product` defaults to `simulated-apps`; `--harness` to `monarch`.
- The task set comes from `--tasks`, or from `--plan`'s `tasks` field. Exactly
  one of the two; `--plan` is the usual form because the plan also carries the
  approval.
- `--attempts` defaults to 3: the most authoring attempts per task.
- **This command spends model money.** It prints, before anything else:

  ```
  wb monarch recipes: 10 tasks, up to 3 authoring attempts each (max 30 attempts)
  cost band: US$ 2 – US$ 7 (create + run pilot measured US$ 0.22 per attempt)
  tasks already covered for this knowledge base: 0
  ```

  and then refuses with exit 5 unless `--yes` was given or `--plan`'s
  `approved_by` is set.
- Idempotent: a task with a recipe for the current knowledge base is skipped and
  costs nothing. A different knowledge base invalidates every recipe.
- Per task, one line per attempt and one verdict line:

  ```
  [..] simple.sf_contact_email attempt 1/3: authored wf 0b7e… v3, run succeeded
  [ok] simple.sf_contact_email: kept wf 0b7e… v3 (1 attempt, US$ 0.19)
  [..] simple.sf_opp_stage attempt 1/3: checker failed (assertion: stage)
  [ok] simple.sf_opp_stage: kept wf 4c19… v2 (3 attempts, US$ 0.61)
  [!!] simple.sf_opp_closed_won: no passing recipe after 3 attempts (checker_failed)
  ```

- Finally, the file and the totals:

  ```
  [ok] write: config/products/simulated-apps.monarch-recipes.yaml (changed)
       9 recipes, 1 missing, 13 attempts, US$ 2.84
  ```

- The name a kept workflow would carry inside Monarch is printed as
  `bench:<task_id>`, with the note that Monarch has no rename route today, so the
  name is recorded here only.
- Exit codes: 0 every task has a recipe; 1 at least one task is missing (the file
  is still written); 4 Monarch or the discovery service unreachable; 5 not
  approved; 6 the knowledge-base file is missing (run `wb monarch setup` first).

## `wb run` in run-only mode (behaviour, no new flags)

- Refuses before any attempt when: the recipes file is missing (naming
  `wb monarch recipes`); its product or task set does not match the plan's; every
  task in the set is missing a recipe.
- Before the first Monarch attempt (the same `prepare()` hook feature 002 added):
  - reads each recorded workflow and refuses on a missing one or on a different
    recipe version, naming the task, the recorded version and the live one;
  - refuses when the knowledge-base file's fingerprint differs from the one the
    recipes were made against, saying the recipes must be remade.
- Excludes the tasks recorded as missing from the task set of **every**
  competitor, and says so in the banner:

  ```
  monarch: monarch@1a2b3c4, mode run-only, 9 recipes, 1 task excluded (checker_failed)
  ```

- Never deletes a workflow.

## `wb report` in run-only mode

The source line of every run-only figure gains two sentences:

```
source: tasks · pilot-monarch-run-only · 9 of 10 tasks (1 excluded: no known-correct
recipe, checker_failed) · 2 repetitions · run 20260904-… · Monarch executed a fixed
known-correct workflow; the other competitors did the whole task from the request text.
```
