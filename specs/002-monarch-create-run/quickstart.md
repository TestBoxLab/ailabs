# Quickstart: proving feature 002 works

All commands from `monarch-benchmark/workflowbench/`. Offline steps need no
key and no Monarch. Live steps are gated (constitution §IV) and listed last.

## Offline (every developer, CI)

```bash
uv sync
uv run python -m pytest tests -q
```

Expected: all tests green (199 before this feature plus the new
`tests/test_monarch_arm.py`, `tests/test_langfuse_cost.py`,
`tests/test_monarch_setup.py`, `tests/test_seeds.py`, additions to
`tests/test_config.py` and `tests/test_run_config.py`).

What the new tests prove, mapped to the spec:

| Test file | Proves |
|---|---|
| `test_seeds.py` | 47 folders, 686 action files, acceptance-bar validator passes, deterministic output (SC-003) |
| `test_monarch_setup.py` | setup against the fake discovery service: stop when not mounted, 47 registrations and imports, hash file written, second run byte-identical, zero model calls (SC-003) |
| `test_config.py` | new harness fields validated; `release` rejected; price table loaded; `kind: price-table` skipped by `load_models` |
| `test_run_config.py` | hash file enters the config hash; missing file refuses; drift refuses before the first Monarch attempt (SC-004) |
| `test_monarch_arm.py` | one scenario per row of the FR-010 table (SC-002); fixed reply and question count (SC-006); deadline cancels and deletes; snapshot from the `Episode` after the fake engine's calls; lock serialises two attempts; competitor name from a temp git repo |
| `test_langfuse_cost.py` | cost per phase and per model to the cent; `cost_missing`; `other` phase flagged; unmapped model stops the run (SC-005) |
| `test_openapi_shim.py` (extended) | front door binds to the host given; default unchanged |

End-to-end offline run of the pilot plan with fakes (SC-001):

```bash
uv run python -m pytest tests/test_monarch_arm.py -k pilot_plan_offline -q
```

It starts the fake Monarch, fake discovery service and fake Langfuse on free
ports, writes a temporary harness file pointing at them, runs
`Orchestrator.from_config` on the pilot plan with the answer key and Monarch
only (the raw model needs a key), and asserts 20 answer-key passes, 20 Monarch
rows with snapshots and cost, and a report with both names.

## Live (Carlos's machine, in this order; paste outputs into `tasks.md`)

Monarch runs on Railway (project `monarch-dev`), kept up only while a benchmark
runs. Before and after any live step, from any shell:

```bash
bash C:/Users/cgmat/Desktop/TestBox/monarch/local-docs/setup/scripts/railway-ops.sh unlock   # before: rebuilds and waits for /api (8-12 min)
bash C:/Users/cgmat/Desktop/TestBox/monarch/local-docs/setup/scripts/railway-ops.sh status   # what is up
bash C:/Users/cgmat/Desktop/TestBox/monarch/local-docs/setup/scripts/railway-ops.sh lock     # after: instant, backend and web go away, cost stops
```

The front door is reached through the ngrok tunnel in `FRONT_DOOR_URL`
(`shim_public_url` in the harness); the tunnel must be up on this machine.
Details in the Monarch repo, `local-docs/setup/railway-deploy.md`.

1. Monarch up with tracing: `cd <monarch>/monarch-enterprise && just dev-otel`.
   Environment: `MONARCH_URL`, `MONARCH_FD_URL`, `LANGFUSE_URL`,
   `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `MONARCH_PASSWORD` in
   `workflowbench/.env`.
2. `uv run wb doctor` → the `monarch` block shows four `OK` lines. No money.
3. `uv run wb monarch setup` → follow the printed override snippet if step 2
   stops; rerun until `write` prints the hash file. No money.
4. From inside a Monarch container:
   `curl http://host.docker.internal:9105/openapi/index.json` while a front
   door is up (start one with `uv run python -m wb_arms.http_shim --host 0.0.0.0 --port 9105`).
5. Only after `bedrock:InvokeModel` is granted: `uv run wb doctor --monarch-probe`
   (cents), then one attempt on one task:
   `uv run wb run --product simulated-apps --plan pilot-monarch-create-run`
   with a temporary plan copy limited to one task and one repetition (cents).
6. The paired pilot, 60 attempts, only after Carlos approves it with a cost
   band and sets `approved_by`: the full plan. Then `wb grade`, `wb report`.

Expected report line: `monarch@<sha>` beside `claude-opus-4-8/api`, paired on
identical sets, error bars, source lines with the price-table version and the
share of attempts with `cost_missing`.
