# Contract: configuration files added or changed by feature 004

Extends `specs/001-declarative-benchmark-config/contracts/config-files.md` and
`specs/002-monarch-create-run/contracts/config-files.md`. Shipped examples are
the contract's executable form.

## products/simulated-apps.monarch-recipes.yaml (new, written by `wb monarch recipes`)

```yaml
product: simulated-apps
tasks: tasks
generated_at: 2026-09-04T12:00:00Z
kb_hash_file_sha: 9f2c1d0e…        # sha256 of simulated-apps.monarch-kb.yaml's bytes
monarch: monarch@1a2b3c4           # the build that authored these recipes
recipes:
  simple.sf_contact_email:
    workflow_id: 0b7e4f21-…
    recipe_version: 3
    authored_at: 2026-09-04T12:03:11Z
    attempts_used: 1
  simple.sf_opp_stage:
    workflow_id: 4c19a8b0-…
    recipe_version: 2
    authored_at: 2026-09-04T12:09:40Z
    attempts_used: 3
missing:
  simple.sf_opp_closed_won:
    reason: checker_failed
    attempts_used: 3
    detail: "invariant failed: is_closed, is_won changed"
```

Rules:

- Every key of `recipes` and `missing` is a task of `tasks`; no task appears in
  both. A task in neither has not been attempted, and a run-only run treats it as
  missing and refuses to include it.
- `reason` is one of `checker_failed`, `authoring_error`, `run_error`, `timeout`,
  `infra`.
- Hand edits are pointless and dangerous: the run re-reads Monarch and refuses on
  any difference in `recipe_version`, and `kb_hash_file_sha` is checked against
  the knowledge-base file's actual bytes.
- In the run's configuration hash: `product`, `tasks`, `kb_hash_file_sha`,
  `recipes`, and the keys of `missing`. Not `generated_at`, not `detail`.

## plans/pilot-monarch-run-only.yaml (new)

```yaml
name: pilot-monarch-run-only
description: >
  Paired pilot on the simulated apps in run-only mode. Monarch executes one
  known-correct workflow per task (its engine alone, nothing authored on the
  clock) beside five raw models doing the whole task and the answer key.
  Not a like-for-like race; the report says so. Internal.
tasks: tasks
mode: run-only
repetitions: 2
timeout_s: 900
concurrency: 4
competitors:
  - {harness: oracle}
  - {model: kimi-k3-fireworks, harness: api}
  - {model: glm-5.3-fireworks, harness: api}
  - {model: claude-opus-5, harness: api}
  - {model: gpt-5.6-terra, harness: api}
  - {model: gpt-5.6-sol, harness: api}
  - {harness: monarch}
baseline: claude-opus-5/api
audience: internal
cost_ceiling_usd: 40
approved_by: null          # Carlos approves the specific run before it starts
```

Rules: same competitors and baseline as `pilot-monarch-create-run`, so the two
modes can be read side by side on the same task set. `approved_by` stays empty
until Carlos approves the specific run (10 tasks × 2 repetitions × 7 competitors
= 140 attempts, above smoke scale).

## harnesses/monarch.yaml (changed: one line)

```yaml
modes: [create-run, run-only]            # full-flow returns in 003
```

Nothing else in the harness changes. The recipes file is found next to the
product file by name, as the knowledge-base file already is, so no new field is
needed.

## products/simulated-apps.yaml (unchanged)

Already declares `modes: [full-flow, create-run, run-only]`. Listed here only to
say it needs no edit: a plan whose mode is not in both the product's and the
harness's list already fails validation before any spend (feature 001).
