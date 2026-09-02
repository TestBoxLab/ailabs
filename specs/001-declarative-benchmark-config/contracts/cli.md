# Contract: `wb` command changes

## wb run

```
wb run [--product NAME|PATH] [--plan NAME|PATH] [--run-id ID]
```

- Names resolve to `config/products/NAME.yaml` and `config/plans/NAME.yaml`;
  paths are used as given.
- Missing flag + terminal attached → numbered picker on stdout/stdin:
  ```
  Products:
    1) simulated-apps
  Pick a product [1-1]:
  ```
  Accepts a number or a name.
- Missing flag + no terminal → exit 2 with
  `wb run: --plan is required without a terminal; available: smoke-frontier`.
- Validation failure → exit 2, one `config error in <file>: <field>: <why>` per line, nothing contacted.
- Approval guard → exit 2 with the attempt count and `set approved_by`.
- Start banner (before the first attempt):
  ```
  product   simulated-apps (simulated, mutable data)
  plan      smoke-frontier  mode=create-run  audience=internal
  tasks     10 in tasks/   repetitions 2   competitors 3   attempts 60
  ceiling   US$ 5.00   approved_by: —
  ```
- Cost ceiling reached → exit 1 with
  `run <id> stopped: spend US$ 5.12 exceeds ceiling US$ 5.00 after 43 attempts; raise cost_ceiling_usd in the plan and run: wb resume <id>`.
- Removed flags: `--suite`, `--arms`, `--k`, `--timeout`, `--concurrency` (using one is an argparse error).

## wb resume

```
wb resume RUN_ID [--concurrency N]
```

Unchanged interface. Internally re-resolves product and plan from the run's
`config_json`, recomputes the hash (R2), refuses on drift (exit 2), refuses when
`stop_reason == cost_ceiling` and the ceiling was not raised above the spend
(exit 2, message names both numbers).

## wb status

Unchanged interface. Adds a line `stopped: cost_ceiling (spend US$ 5.12 / ceiling US$ 5.00)` when set.

## wb corpus declare

```
wb corpus declare DIR [--out DIR] [--overwrite] [--product NAME|PATH]
```

`--product` defaults to `simulated-apps`; the side-effect list is read from
the product's `side_effects` path.

## wb doctor, wb grade, wb report

Unchanged. `wb doctor --arms` keeps accepting model names (the registry is now
loaded from `config/models`).

## CI: .github/workflows/smoke.yml

Inputs: `plan` (default `smoke-frontier`). Steps: doctor on the plan's API
models, then
`uv run wb run --product simulated-apps --plan "${{ inputs.plan }}" --run-id "$RUN_ID"`,
then `wb report "$RUN_ID" --audience internal --baseline claude-opus-4-8/api`.
The old `k > 2` shell guard is removed: the approval gate is in code.
