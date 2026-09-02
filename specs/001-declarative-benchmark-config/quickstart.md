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

```
uv run wb run --product simulated-apps --plan smoke-frontier < /dev/null
```

Without keys set, expected: exit 2 and lines like
`config error in config/models/claude-opus-4-8.yaml: key_env: ANTHROPIC_API_KEY is not set`.
Nothing is contacted.

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
