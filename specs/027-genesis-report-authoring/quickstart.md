# Offline validation

From monarch-benchmark/workflowbench use uv run python -m pytest with the new
report lifecycle and pattern tests, then relevant Genesis/report suites.
Use tests/browser/server.py with a fixture publication only; no real model calls.
Final check output and rendered evidence are recorded in validation.md.
