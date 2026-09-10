# Initial offline baseline

Date: 2026-09-07 America/Sao_Paulo.

- AILabs commit: `88cddf6e172a4c39f0b32fa49eb2e98b8fa8cd28`.
- AutomationBench upstream commit: `4a8e1061254004d9dac807054eed33fad7d1ff14` (1.0.6).
- uv.lock SHA256: `178018bc8191d913829362045e7fe1e50d8af2e2b9c15a58d923043ac95880bb`.
- Host: Windows, Python 3.13.9; dependencies installed with `uv sync --frozen`.
- WorkflowBench application/test code was unchanged during these runs.
- No paid benchmark or external judging calls were launched.

## Full suite

From `monarch-benchmark/workflowbench`:

```text
uv run --frozen python -m pytest tests -q
1 failed, 703 passed, 3 skipped in 678.85s (0:11:18)
```

Failure: `tests/test_monarch_arm.py::test_timeout_during_run`, assertion at line 396.
Expected an execution-phase timeout; observed:

```text
deadline passed in the authoring phase: deadline hit while streaming authoring run rr-1
```

The test gives the arm a 1.0-second timeout and expects authoring to finish before
an intentionally nonterminating execution begins. On this host it expires during
authoring. Fake-server connection-reset/aborted messages followed cancellation.
This identifies the observed phase mismatch, not a verified root cause.

## Focused reproduction

```text
uv run --frozen python -m pytest tests/test_monarch_arm.py::test_timeout_during_run -q
1 failed in 3.86s
```

The same authoring-phase mismatch reproduced. The checkout is therefore not a
passing baseline on this host. Investigate phase deadline accounting and make the
test's phase transition deterministic without weakening its cleanup and retained
spend assertions. Do not erase this result after a repair.

## Scope limits

These checks exercise local fixtures and do not validate live Monarch, native CLI
isolation, provider billing or repaired ApplicationBench graders. The installed
upstream baseline intentionally has not yet adopted `1.0.6+evalrepair.10`.
