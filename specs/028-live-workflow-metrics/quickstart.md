# Offline validation

From monarch-benchmark/workflowbench/:

```
uv run --python 3.13 python -m pytest tests/test_studio_performance.py tests/test_studio_measures.py tests/test_studio_reports.py tests/test_static_csp.py -q
node tests/browser/live-workflows-model.cjs
node tests/browser/live-workflows.cjs
```

The browser check uses only the fixture Studio, scripted checks and synthetic
stream messages. It must never dispatch a paid run. Evidence and final command
results are recorded in implementation.md after execution.

Set BROWSER_PORT to a free port if 8779 is occupied. The fixture shuts itself
down after the browser scenario. PLAYWRIGHT_MODULE can identify an installed
Playwright module; Chrome must be available. Final screenshots and checks.json
are generated under the repository .tmp/live-workflows/ directory.
