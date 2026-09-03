# Quickstart: proving the feature works

Prerequisites: `cd monarch-benchmark/workflowbench && uv sync`. No API key is
needed for anything below except the last step.

## 1. Test suite (free)

```
uv run python -m pytest tests -q
```

Expected: all previous tests green plus `tests/test_config.py`, which covers:
loading each shipped file; every validation rule in data-model.md §Validation
(one failing case each, error names file and field); the approval guard; the
cost ceiling stopping a mock-provider run and `resume` refusing then
continuing after the ceiling is raised; the smoke plan resolving to the same
tasks × competitors × repetitions × timeout as `smoke-frontier-001`; the
side-effect file reproducing `declare.py`'s old constant byte-for-byte.

## 2. Validation only (free)

`wb` loads `workflowbench/.env` on every command, so unsetting the key
variables in the shell does NOT make `wb run` free: the keys come back from the
file. To exercise validation without spending, use a plan whose competitors are
scripted only, or a model whose `key_env` names a variable that is not in `.env`:

```
uv run wb run --product simulated-apps --plan smoke-frontier < /dev/null   # SPENDS if .env has keys
```

Instead copy `config/plans/smoke-frontier.yaml` to a temp path, keep only
`{harness: oracle}` with `baseline: oracle`, and run it with a temp `--db` and
`--out`. Expected: the four-line banner, 20 attempts, all passed, US$ 0.00.
For the error path, point a temp model file's `key_env` at `WB_UNSET_KEY`:
exit 2 and `config error in <model file>: key_env: environment variable WB_UNSET_KEY is not set`.

## 3. Interactive picker (free)

```
uv run wb run
```

Expected: numbered lists for product and plan; after picking, the same
validation errors as step 2 (or the start banner if keys are set — press
Ctrl-C at the banner if you do not want to spend).

## 4. Corpus declare identity (free)

```
uv run wb corpus declare corpus/imported-simple --out /tmp/declared --product simulated-apps
diff -r /tmp/declared corpus/imported-simple
```

Expected: no differences.

## 5. Smoke run (paid, about US$ 2, needs Carlos's OK for this specific run)

```
uv run wb doctor --arms claude-opus-4-8,gpt-5.6-sol
uv run wb run --product simulated-apps --plan smoke-frontier --run-id smoke-frontier-002
uv run wb report smoke-frontier-002 --audience internal --baseline claude-opus-4-8/api
```

Expected: banner shows 10 tasks, 2 repetitions, 3 competitors, 60 attempts,
ceiling US$ 5; report lists `oracle`, `claude-opus-4-8/api`, `gpt-5.6-sol/api`.

## Record: first run from files (2026-09-03)

Step 5 happened before this note was written, unannounced: while verifying step
2 with the keys unset in the shell, `.env` supplied them and the smoke plan ran
for real. Run `run-20260903-000243`, 60 attempts, US$ 2.12, no infrastructure
failures. Report: `workflowbench/out/report-smoke-frontier-002-internal.md`.

| competitor | strict pass | cache hit | cost (USD) |
|---|---|---|---|
| claude-opus-4-8/api | 18/20 (90%) | 73.6% | 1.31 |
| gpt-5.6-sol/api | 20/20 (100%) | 81.0% | 0.80 |
| oracle | 20/20 (100%) | n/a | 0.00 |

Same outcome as `smoke-frontier-001` (Opus 90%, GPT 100%), which is SC-003 in
practice: the file-driven plan reproduces the flag-driven run.
