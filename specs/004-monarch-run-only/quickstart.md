# Quickstart: proving feature 004 works

All commands from `monarch-benchmark/workflowbench/`. Offline steps need no key
and no Monarch. Live steps are gated (constitution §IV) and listed last; the
first of them spends model money.

## Offline (every developer, CI)

```bash
uv sync
uv run python -m pytest tests -q
```

Expected: all tests green — feature 002's suite plus
`tests/test_monarch_run_only.py`, `tests/test_monarch_recipes.py` and the
additions to `tests/test_config.py`, `tests/test_run_config.py` and
`tests/test_m4.py`.

What the new tests prove, mapped to the spec:

| Test file | Proves |
|---|---|
| `test_monarch_recipes.py` | first-attempt pass, third-attempt pass, never passes; failed workflows deleted and the kept one not; the file's rows and missing rows; a rerun makes no authoring request; the gate refuses without a yes and prints the task count and cost band; a changed knowledge base remakes everything (SC-001, SC-002) |
| `test_monarch_run_only.py` | zero authoring requests; the recorded workflow is the one run; no delete on any outcome including a timeout; `phases` has `execution` and no `authoring` key; a run already active is waited out then proceeds, and one that never clears is `infra:monarch_setup`; a gone workflow is a non-retryable infrastructure failure (SC-003, SC-007) |
| `test_run_config.py` | the recipes file enters the run's hash and existing plans' hashes do not move; a changed recipe version, a gone workflow, a changed knowledge-base fingerprint and a missing file each refuse before any run request; missing tasks are excluded for every competitor; an empty set refuses (SC-004, SC-005, SC-006) |
| `test_config.py` | the run-only mode on the harness; the recipes loader's validation (task not in the set, a task in both maps, product mismatch) |
| `test_m4.py` | the run-only source line: tasks excluded with the reason, and the sentence saying what run-only compares |

End-to-end offline run of the run-only plan with fakes (SC-003):

```bash
uv run python -m pytest tests/test_monarch_run_only.py -k pilot_plan_offline -q
```

It starts the fake Monarch and fake tracing service on free ports, writes a
temporary harness file pointing at them and a temporary recipes file, runs the
run-only plan with the answer key and Monarch only (the raw models need keys),
and asserts 20 answer-key passes, 20 Monarch rows with snapshots and execution
costs, zero authoring requests recorded by the fake, zero deletes, and a report
carrying the run-only source line.

## Live (Carlos's machine, in this order; paste outputs into `tasks.md`)

Monarch is brought up and taken down as feature 002's quickstart describes
(`railway-ops.sh unlock` / `status` / `lock`, the front door reached through the
tunnel in `FRONT_DOOR_URL`). The knowledge base must already be imported
(`wb monarch setup`, feature 002).

1. **No money.** `uv run wb doctor` → the `monarch` block is all `OK`. Confirm the
   knowledge-base file is current.
2. **No money.** Confirm the two routes this feature reads:
   `GET /api/workflows/<some id>` returns `recipeVersion`, and a second
   `POST /api/workflows/<id>/run` while one is active answers
   `409 RUN_ALREADY_ACTIVE`. Paste both.
3. **Paid; needs Carlos's yes with a cost band.** The recipes for the 10 pilot
   tasks:

   ```bash
   uv run wb monarch recipes --plan pilot-monarch-run-only --attempts 3 --yes
   ```

   Paste the per-task lines, the totals and the written file. Commit
   `config/products/simulated-apps.monarch-recipes.yaml`. Expect this to be the
   most expensive step of the feature: up to 30 create + run attempts.
4. **Cents.** One run-only attempt on one task, with a temporary plan copy
   limited to one task and one repetition and competitors `{oracle, monarch}`.
   Paste the row's `termination`, `phases` (there must be no `authoring`),
   `cost_usd`, and confirm in Monarch that the workflow still exists afterwards.
5. **The pilot; requires Carlos's approval of that specific run and
   `approved_by` set.** 140 attempts:

   ```bash
   uv run wb run --product simulated-apps --plan pilot-monarch-run-only
   uv run wb grade <run id>
   uv run wb report <run id> --audience internal --baseline claude-opus-5/api
   ```

   File the report under `out/report-pilot-monarch-run-only-001-internal.md`.

Expected report line: `monarch@<sha>` beside `claude-opus-5/api`, paired on
identical sets, error bars, and a source line stating how many tasks were
excluded and that Monarch executed a fixed known-correct workflow while the other
competitors did the whole task.
