# WorkflowBench — T0 (synthetic mode)

Working implementation of the T0 spec: world server, graph ingester, grader, pilot runner.
Everything here runs against `zapier/AutomationBench` (MIT) as a library — pinned clone expected as a sibling install (`pip install -e ../ab`).

## What works today (all tested, 9/9 green)

- **`wb_world/`** — the world server.
  - `episode.py`: per-episode `WorldState` seeded exactly the way the AB runner seeds it; frozen clock (`WorldMeta.current_time`); service gating via `allowed_services` (upstream feature — out-of-scope calls get a credentials error); start/end snapshots.
  - `server.py`: **real MCP server** (`python -m wb_world.server`), 3 tools: `api_search`, `api_fetch`, `base64_encode`. One episode per process, configured by env (`WB_TASK_FILE`, `WB_EPISODE_ID`, `WB_SNAPSHOT_DIR`, optional `WB_FROZEN_TIME`). Writes `snapshot0.json` at startup, `snapshot1.json` + `tool_calls.json` at exit. Smoke-tested over stdio with the MCP client SDK, including out-of-process grading from the written snapshots.
  - `snapshot.py`: whole-state diff (meta excluded, list items identified by `id`), with the explicit housekeeping ignore-list (`created_at`, `updated_at`, `last_modified_date`, …) — the simulated Salesforce updates `last_modified_date` on writes, which is exactly the autofield-noise class the design predicted.
- **`grader/`** — out-of-process grading: AB's assertion registry for positive checks + the **dual invariant** (every expected change present, every observed change expected-or-allowed; matchers with literal `[id=…]` paths and `*` wildcards) + **no-op validation** (every assertion must fail on the untouched world — AppWorld's rule, run as corpus CI).
- **`ingester/`** — `python -m ingester.graph_ingest`: the 47 `.jsonc` endpoint schemas → `product_graph.json` (47 services, **758 actions**, edges). Same files that drive `api_search`/`api_fetch`: parity by construction. The Monarch-side loader mapping is the open question for Deyton.
- **`runner/`** — 24-field `EpisodeRow` (design schema), three scripted arms, pilot runner emitting `episodes.jsonl`, `summary.json`, `noop_validation.json`.
- **`tasks/`** — 10 pilot tasks exported from AB's `simple` domain, each annotated with `expected_changes` / `allowed_changes` matchers.

## Pilot-001 results (10 tasks × 3 arms × k=2 = 60 episodes)

| Arm | Strict pass | Assertion pass | Invariant fails |
|---|---|---|---|
| `oracle/scripted` | **1.00** | 1.00 | 0 |
| `sloppy/collateral` | 0.40 | **1.00** | 12 |
| `null/no-action` | 0.00 | 0.00 | 20 |

The middle row is the point of the whole design: the sloppy arm **fools the positive assertions 100% of the time** and is caught only by the dual invariant. (It passes on the 4 opportunity-only tasks because there is no mail to trash — its collateral write needs a seeded inbox.) No-op validation: 0 vacuous assertions across the 10 tasks.

## Wiring a real bare arm (next step)

Point any MCP-capable harness at the server. Claude Code example (`.mcp.json`):

```json
{"mcpServers": {"wb-world": {
  "command": "python", "args": ["-m", "wb_world.server"],
  "env": {"WB_TASK_FILE": "tasks/simple.email_sf_contact_phone_update.json",
          "WB_EPISODE_ID": "run1", "WB_SNAPSHOT_DIR": "out/run1"}}}}
```

Give the agent the task's user prompt as the `/goal` brief, let it finish, then grade offline:
`grader.grade.grade(task, snapshot0, snapshot1)`.

## Run it

```
uv venv --python 3.13 && . .venv/bin/activate
uv pip install -e ../ab -e . pytest pytest-asyncio
python -m pytest tests -q          # 9 tests
python - <<'PY'
import json; from pathlib import Path; from runner.pilot import run_pilot
run_pilot([json.loads(p.read_text()) for p in sorted(Path('tasks').glob('*.json'))], Path('out/pilot'), k=2)
PY
```

## Open items (carried from the T0 spec)

- Monarch engine hookup: MCP directly, or an HTTP shim in front of `wb_world` (Deyton).
- `product_graph.json` → real product-graph loader mapping (Deyton).
- Expand corpus beyond the 10 pilot tasks; add `contract_sha256` into the task files themselves.
- Real bare-arm run (Claude Code via the `.mcp.json` above) and first monarch/stock pairing.
