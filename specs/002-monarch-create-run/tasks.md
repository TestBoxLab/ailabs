# Tasks: Monarch as a Competitor in Create + Run Mode

**Input**: Design documents from `/specs/002-monarch-create-run/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution §II mandates red → green → refactor; every
task that adds logic starts with a failing test in the named test file. All
tests offline; no key in the environment; no `wb run` during implementation.

**Organization**: Grouped by user story in spec priority order: US2 (setup)
and US1 (run the pilot) are P1; US3 (terminations), US4 (fixed reply), US5
(cost) are P2; US6 (doctor) and US7 (docs) are P3. US2 comes before US1
because the run refuses without the hash file US2 writes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US7 from spec.md

## Path Conventions

All code paths are under `monarch-benchmark/workflowbench/` (written as `wb/`
below). Tests run with
`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.
The Monarch checkout is `C:\Users\cgmat\Desktop\TestBox\monarch`.

---

## Phase 1: Setup

- [x] T001 Delete the placeholder tests `test_monarch_arm_blocked_without_entrypoints` and `test_monarch_lab_requires_config_and_hashes_it` from `wb/tests/test_arms_m2.py`; run the suite and confirm 197 green (the two removed)
- [x] T002 [P] Write `wb/config/models/monarch-team-bedrock.yaml` per `contracts/config-files.md` with Bedrock `us-west-2` prices for the five families looked up today and `prices_verified: 2026-09-03` (state the source URL in `description`)
- [x] T003 [P] Write `wb/config/plans/pilot-monarch-create-run.yaml` per `contracts/config-files.md` (`approved_by: null`)
- [x] T004 [P] Rewrite `wb/config/harnesses/monarch.yaml` per `contracts/config-files.md` (`runnable: true`, new fields, `release` removed, `modes: [create-run]`)

---

## Phase 2: Foundational (blocking)

**Purpose**: config loading and hashing every story depends on; the three fake servers; the front door bind address.

- [x] T005 Write failing tests in `wb/tests/test_config.py`: `load_harness` on the new `monarch.yaml` returns every new field; `release` present → `ConfigError` naming the field; `shim_port` outside 1024–65535 fails; `load_price_table` returns five families with four prices each; duplicate family fails; `load_models(folder)` skips `kind: price-table` files
- [x] T006 Implement in `wb/wb_orchestrator/config.py`: new `Harness` fields (`login_email`, `login_password_env`, `fd_url`, `shim_port`, `shim_public_host`, `langfuse_url`, `langfuse_public_key_env`, `langfuse_secret_key_env`, `price_table`, `monarch_repo`), `_HARNESS_KEYS["monarch"]` updated, `release` removed; `PriceTable`/`PriceEntry` dataclasses and `load_price_table(path)`; `_read` accepts `kind: price-table` under `models/`; make `wb/wb_arms/providers.py::load_models` skip price tables. T005 green
- [x] T007 Write failing tests in `wb/tests/test_run_config.py`: `resolve()` with a Monarch competitor loads `products/<name>.monarch-kb.yaml` into `RunConfig.monarch_kb` and the price table into `RunConfig.price_tables`; missing kb file → `ConfigError(product, "monarch_kb", …)` mentioning `wb monarch setup`; kb file with a slug outside the product's services fails; `RunConfig.hash` changes when one kb hash or one price changes; the hash of `smoke-frontier` (no Monarch) is unchanged versus the value recorded in `out/run-20260903-000243/config.json` (read it in the test); env check accepts `login_password_env` set when `credential_env` is unset
- [x] T008 Implement in `wb/wb_orchestrator/config.py`: `MonarchKb` dataclass + `load_monarch_kb(path, product)`; `RunConfig.monarch_kb`, `RunConfig.price_tables`; `_hashed()` adds `monarch_kb` (kb + shim_public_url) and `price_tables` only when present; `resolve()` env rule for credential vs password variable. T007 green
- [x] T009 [P] Write failing test in `wb/tests/test_openapi_shim.py`: `EpisodeHTTPShim(ep, host="0.0.0.0", port=0, public_url="http://host.docker.internal:9105")` binds and `/openapi/index.json` URLs use the public URL; default `host` stays `127.0.0.1`
- [x] T010 [P] Add `host: str = "127.0.0.1"` to `EpisodeHTTPShim.__init__` in `wb/wb_arms/http_shim.py` and use it in the bind and `self.url`; add a `python -m wb_arms.http_shim --host --port --task` entry point that serves the first pilot task's world (used by the live checklist). T009 green
- [x] T011 [P] Create `wb/tests/fake_fd.py`: stdlib `ThreadingHTTPServer` serving `GET /health`, `GET /v1/seeds` (items with `slug`, `kb_hash`, `action_count`, `in_sync`), `POST /v1/products` (upsert by slug), `POST /v1/seeds/:slug/import` (404 unless the slug's folder exists under a configurable `fixtures_dir`; `kb_hash` = sha256 of sorted action ids in the folder; returns `{slug, actions_imported, before, after, in_sync}`); records requests; `start()/stop()` and a context manager
- [x] T012 [P] Create `wb/tests/fake_langfuse.py`: stdlib server with basic-auth check serving `GET /api/public/health`, `GET /api/public/traces?metadata[bench_episode_id]=…&page=&limit=` and `GET /api/public/observations?traceId=…&page=&limit=` from an in-memory list of traces/observations loaded by the test (`add_trace(episode_id, spans, generations)` helper building parent links); records requests
- [x] T013 [P] Create `wb/tests/fake_monarch.py`: stdlib server driven by a `Scenario` dataclass (data-model §7): `POST /api/auth/login` (sets cookie and returns user), `GET /api`, `GET /api/health` (401 without `x-monarch-session`), `POST /api/workflows/recipe/runs` (records `x-bench-episode-id`, returns `{runId, token}`), `GET …/runs/:id/stream` (chunked `data:` frames from `scenario.frames`, `: ping` lines, waits for a reply before continuing after an `awaiting_input` frame), `POST …/runs/:id/reply`, `POST …/runs/:id/cancel`, `POST /api/workflows/:id/run` (refusal by `scenario.run_refusal`, else fires `scenario.engine_calls` at the front-door URL it is given via `scenario.shim_url` in a thread and returns `{engine:{runId,status}}`), `GET /api/workflows/runs/:runId` (running until engine calls finish, then `scenario.run_outcome`), `DELETE /api/workflows/:id`; records everything
- [x] T014 Write `wb/tests/test_fakes.py`: smoke test for each fake (start, one request per route, stop) so the fakes themselves are verified before the stories use them

---

## Phase 3: User Story 2 — Prepare Monarch once per product (P1)

**Goal**: `wb monarch setup` generates 47 seed folders, verifies they are mounted, registers and imports 47 products, writes the hash file; idempotent; no model call.

**Independent test**: `wb/tests/test_seeds.py` and `wb/tests/test_monarch_setup.py` against `fake_fd`.

- [x] T015 [US2] Write failing tests in `wb/tests/test_seeds.py`: `seeds.generate(out_dir, shim_public_url)` writes exactly one folder per service (47) with `_meta.json` and one action file per operation (686 total, count from `openapi.build_all`); every action has `auth_scheme: none`, `response_template.schema` and non-empty `extract`, `creates_entities[0].identifier_path` on `verb: create`, `url_template` starting with the shim public URL; `seeds.validate(folder)` returns no gaps on the generated set and names the gap on a corrupted file; two generations are byte-identical
- [x] T016 [US2] Create `wb/wb_world/seeds.py` per research R10: `generate(out_dir, shim_public_url) -> Summary(operations_in_spec, files_written, folders)`, `validate(folder) -> list[Gap]`, verb from method + path, `body_template` from the request schema, `extract` from id-like response properties, `identifier_keys` from sibling path parameters; deterministic JSON (sorted keys, fixed timestamps); refuse to write on any gap. T015 green
- [x] T017 [US2] Write failing tests in `wb/tests/test_monarch_setup.py` against `fake_fd`: not mounted → exit 3 and the override snippet printed containing the absolute out dir, no products registered; mounted → 47 registrations, 47 imports, hash file written with 47 sorted entries and `shim_public_url`; second run → identical file bytes and exit 0; FD unreachable → exit 4 naming the address; generation gap → exit 2 and nothing written; grant check prints `unknown (open question 2)`; no request ever goes to a Monarch backend or Langfuse (assert on the fakes)
- [x] T018 [US2] Create `wb/wb_orchestrator/monarch_setup.py`: `run(product, harness, out_dir, env, stdout) -> int` with the six steps and exit codes of `contracts/cli.md`; FD calls with `urllib.request`; writes `config/products/<product>.monarch-kb.yaml` via `yaml.safe_dump` with sorted keys. T017 green
- [x] T019 [US2] Add the `monarch` subcommand group with `setup` (`--product`, `--harness`, `--out`) to `wb/wb_orchestrator/cli.py` reusing `resolve_name_or_path`; test in `wb/tests/test_monarch_setup.py` that `main(["monarch","setup",…])` returns the step's exit code
- [x] T020 [US2] Add `wb/config/products/.gitkeep`-style note: commit `simulated-apps.monarch-kb.yaml` only after the live setup (T053); until then the pilot plan's `resolve()` test uses a fixture kb file under `tests/`

---

## Phase 4: User Story 1 — Run Monarch as a competitor in a paired pilot (P1)

**Goal**: a Monarch attempt authors, runs against the front door, is snapshotted by the bench, and the pilot plan runs offline end to end with the answer key and Monarch.

**Independent test**: `wb/tests/test_monarch_arm.py::test_pilot_plan_offline` (SC-001).

- [x] T021 [US1] Write failing tests in `wb/tests/test_monarch_client.py` against `fake_monarch`: `MonarchClient(base_url, token=None)`; `login(email, password)` stores the token; `token` given → no login request; every call sends `x-monarch-session`; `start_authoring(goal, episode_id)` sends `x-bench-episode-id` and returns `runId`; `stream(run_id, deadline)` yields parsed frames and ignores `: ping`; `reply`, `cancel`, `run_workflow` (sends the header), `get_run`, `delete_workflow` (404 tolerated); 5xx → `InfraError("infra:harness_crash")`; deadline inside `stream` → `EpisodeTimeout`
- [x] T022 [US1] Create `wb/wb_arms/monarch_client.py` (stdlib `urllib.request`, `http.cookiejar` for the login cookie, chunked line iteration for SSE, per-call timeout from the deadline). T021 green
- [x] T023 [US1] Write failing test in `wb/tests/test_monarch_arm.py`: `build_arm_for(monarch competitor)` names the arm `monarch@<sha>` from a temporary git repo created in the test (and `monarch@<sha>+<branch>` on a non-main branch); a path that is not a git repo → `ConfigError(harness file, "monarch_repo", …)`; `arm.model_label` equals the name
- [x] T024 [US1] Implement `monarch_version(repo_path) -> str` in `wb/wb_arms/monarch.py` (`git rev-parse --short HEAD`, `--abbrev-ref HEAD`) and the `monarch` branch of `build_arm_for` in `wb/wb_orchestrator/orchestrator.py` (passes harness, `plan.timeout_s`, price table, kb, env); remove `build_arm("monarch/…")`, `_validate_arm_key`'s monarch clause and the placeholder's env-driven constructor. T023 green
- [x] T025 [US1] Write failing test in `wb/tests/test_monarch_arm.py::test_completed_attempt`: scenario with frames `running → done{workflowId}` and `engine_calls` that create a Salesforce contact on the front door; after `arm.run(ep, deadline)` the `Episode` world contains the contact, `result.termination == "completed"`, `turn_log[0]["monarch"]` has `workflowId/runId/recipeVersion`, the fake saw `x-bench-episode-id == ep.episode_id` on both start requests, the workflow was deleted, the front door port is free again, `phases.authoring.wall_clock_s` and `phases.execution.wall_clock_s` are set
- [x] T026 [US1] Rewrite `MonarchArm` in `wb/wb_arms/monarch.py`: constructor from harness + timeout + price table + kb; `run()` per data-model §8 with the module lock, front door on `0.0.0.0:<shim_port>` with the public URL, login once per run (cached token on the arm), authoring stream, run + poll every 2 s, cleanup in `finally`, deadline re-derived after the lock. T025 green
- [x] T027 [US1] Write failing tests in `wb/tests/test_monarch_arm.py`: `test_lock_serialises` (two threads call `run`; the fake records no overlapping authoring; the second attempt's authoring clock starts after the first's delete) and `test_port_busy_is_infra` (occupy `shim_port` first → `InfraError` retryable naming the port)
- [x] T028 [US1] Make T027 green in `wb/wb_arms/monarch.py` (bind `OSError` → `InfraError("infra:harness_crash", …, retryable=True)`)
- [x] T029 [US1] Write failing test in `wb/tests/test_run_config.py::test_kb_drift_refuses`: `Orchestrator.from_config` with a Monarch competitor calls `arm.prepare()` before the first attempt; `fake_fd` returning one different hash → the run stops before any authoring request, error names the slug
- [x] T030 [US1] Implement `MonarchArm.prepare()` (`GET /v1/seeds` compared with the kb file) in `wb/wb_arms/monarch.py` and the optional `prepare()` call in `Orchestrator._run_arm_group` in `wb/wb_orchestrator/orchestrator.py` (`# ponytail: hasattr check`). T029 green
- [x] T031 [US1] Write failing test `wb/tests/test_monarch_arm.py::test_pilot_plan_offline` per quickstart: fakes on free ports, temporary harness file, temporary kb fixture, plan with `{oracle, monarch}` on the 10 pilot tasks × 2, `Orchestrator.from_config(...).run()`; assert 20 oracle passes, 20 Monarch rows with `snapshot1.json` artifacts and `test_mode == "create-run"`, `wb report` output (internal) lists both competitor names, `config_json` contains the 47 kb hashes and the price-table name
- [x] T032 [US1] Make T031 green (scenario engine calls that reproduce each pilot task's answer key from `tasks/*.json` oracle actions so Monarch's rows can pass; banner line in `wb/wb_orchestrator/cli.py::_banner` adds `monarch: <name>, kb <n> apps, price table <name>@<date>`)

---

## Phase 5: User Story 3 — Charge Monarch only for its own failures (P2)

**Goal**: every outcome in the FR-010 table maps to the right termination and detail; cleanup always runs.

**Independent test**: one parametrised test per row in `wb/tests/test_monarch_arm.py`.

- [x] T033 [US3] Write failing parametrised test `test_termination_table` in `wb/tests/test_monarch_arm.py` with one scenario per row: authoring `error` with message `Bedrock AccessDeniedException` → `InfraError("infra:monarch_llm")`; authoring `error` "planner gave up" → `agent_error`, `error` starts with `authoring_error:`; run refused `RUN_HOST_BLOCKED` / `ENGINE_UNAVAILABLE` / `RUN_ALREADY_ACTIVE` → `InfraError("infra:monarch_setup")`; refused `INPUT_INVALID` / `product_not_granted` / `LLM_LOOP_UNACKNOWLEDGED` / `RUN_LEGACY_RECIPE` → `agent_error` with `run_refused:<code>`; run `failed{errorCode, errorNodeId}` → `agent_error` with `run_error:<code> node=<id>`; login 401 → `InfraError` retryable; stream closes without terminal frame → `agent_error` `stream_closed`; `account` prompt frame → `agent_error` `account_requested`. In every case the fake recorded a `DELETE` (when a workflow existed) and the port is free
- [x] T034 [US3] Implement the mapping in `wb/wb_arms/monarch.py` (`_classify_authoring_error` keyword match with a `# ponytail:` note, `_classify_refusal`, run-outcome mapping). T033 green
- [x] T035 [US3] Write failing tests `test_timeout_during_authoring` (scenario delay > deadline; expect `EpisodeTimeout`, the fake saw `cancel`, then `DELETE` if a workflow id existed) and `test_timeout_during_run` (engine never finishes; expect `EpisodeTimeout`, the fake saw `DELETE`) in `wb/tests/test_monarch_arm.py`
- [x] T036 [US3] Make T035 green in `wb/wb_arms/monarch.py` (deadline checks between SSE lines and between polls; cancel/delete in the timeout path before re-raising)
- [x] T037 [US3] Write failing test `test_leftover_workflow_deleted_next_attempt`: a scenario whose `DELETE` fails once; the next `run()` on the same arm deletes the remembered id first. Make it green in `wb/wb_arms/monarch.py` (`self._leftover: list[str]`)

---

## Phase 6: User Story 4 — Answer Monarch's questions without leaking (P2)

**Goal**: the fixed sentence for every question; count recorded; not configurable.

**Independent test**: `wb/tests/test_monarch_arm.py::test_questions_get_fixed_reply`.

- [x] T038 [US4] Write failing test `test_questions_get_fixed_reply` in `wb/tests/test_monarch_arm.py`: frames `running → awaiting_input{requestId, questions:[q1,q2]} → running → awaiting_input{q3} → done`; the fake recorded two replies whose every answer text equals `wb_arms.monarch.FIXED_REPLY`, `result.phases["authoring"].turns == 3`, flag `questions_asked=3`; a scenario with no questions records `questions_asked=0`
- [x] T039 [US4] Implement `FIXED_REPLY` constant and the reply loop in `wb/wb_arms/monarch.py`. T038 green
- [x] T040 [US4] Write test `test_fixed_reply_not_in_config` in `wb/tests/test_config.py`: `load_harness` rejects a `reply` or `fixed_reply` key on the monarch harness (unknown key); grep-style assertion that no shipped YAML under `wb/config/` contains the sentence

---

## Phase 7: User Story 5 — Complete cost from Monarch's own traces (P2)

**Goal**: cost per phase and per model from Langfuse priced by the table; `cost_missing`; unmapped model stops the run.

**Independent test**: `wb/tests/test_langfuse_cost.py` against `fake_langfuse`.

- [x] T041 [US5] Write failing tests in `wb/tests/test_langfuse_cost.py`: `read_generations(base_url, keys, episode_id)` returns only generations of traces tagged with the episode; phase from the nearest ancestor in the contract table (`recipe.plan` → authoring, `engine.step` under `engine.run` → execution, unlisted → `other`); `summarize(generations, price_table)` prices `input/output/cache_read/cache_write` to the cent for two families in two phases; empty → `total_usd == 0`, `missing == True`; a generation with model `anthropic.claude-nova` → `PriceLookupError` naming the model and the table; usage absent → zero tokens for that generation; pagination across two pages
- [x] T042 [US5] Create `wb/wb_arms/langfuse_cost.py` per data-model §6 and research R7 (stdlib `urllib`, basic auth, paging, parent walk, `Generation`, `CostSummary`, `PriceLookupError`). T041 green
- [x] T043 [US5] Write failing test `test_cost_lands_in_row` in `wb/tests/test_monarch_arm.py`: completed attempt with fake Langfuse traces → `result.cost_usd`, `result.tokens_*`, `result.phases["authoring"/"execution"].cost_usd/tokens_input/tokens_output`, `turn_log` carries the per-family breakdown; no traces → `cost_usd == 0` and flag `cost_missing`, termination unchanged; `other` span → flag `phase_other:<name>`; unmapped model → `InfraError(retryable=False)` after cleanup; Langfuse unreachable during the read → flag `cost_missing` only (health check failure before the attempt is the infra case, tested separately)
- [x] T044 [US5] Wire the cost read into `MonarchArm.run` in `wb/wb_arms/monarch.py` (after cleanup, never changes termination except the unmapped-model stop). T043 green
- [x] T045 [US5] Write failing test in `wb/tests/test_m4.py` (report): the internal report's source line for a run with Monarch rows prints `price table monarch-team-bedrock@2026-09-03` and `cost missing on N/M attempts`; make it green in `wb/wb_report/report.py` (reads the flags and `config_json.price_tables`)

---

## Phase 8: User Story 6 — Check the Monarch environment before spending (P3)

**Goal**: four Monarch checks in `wb doctor`; paid probe only on request.

**Independent test**: `wb/tests/test_doctor_monarch.py` against the three fakes.

- [x] T046 [US6] Write failing tests in `wb/tests/test_doctor_monarch.py`: `check_monarch(harness, env)` returns `{backend, backend_health, fd, langfuse}` each `OK` with the fakes up; one fake down → that key `FAIL` with the address; without `--monarch-probe` the fake Monarch saw no `recipe/runs`; with it, one `recipe/runs` then `cancel`; `run_doctor` includes the block only when `config/harnesses/monarch.yaml` is runnable; `format_report` prints the block
- [x] T047 [US6] Implement `check_monarch` and the `monarch_probe` option in `wb/wb_orchestrator/doctor.py`; add `--monarch-probe` to `wb/wb_orchestrator/cli.py::cmd_doctor`. T046 green

---

## Phase 9: User Story 7 — Read the updated plan and configuration (P3)

**Goal**: PLAN.md, config docs, handoff and CLAUDE.md reflect the feature.

**Independent test**: read the files against FR-033–FR-035.

- [x] T048 [P] [US7] Update `monarch-benchmark/PLAN.md`: B4, B7, B8 and C1–C3 gain "→ feature 002 (`specs/002-monarch-create-run/`)"; C4 marked "superseded: the bench reads Langfuse"; D7's definition of done absorbs D10 and D10 says "merged into D7"; decisions log rows dated 3 Sep 2026: "Monarch cost and phases come from Langfuse priced by a versioned Bedrock table, not from Monarch's Postgres" and "A question during authoring gets one fixed reply, hardcoded; questions counted per attempt" (by Carlos); open questions: the three from spec.md with owners; note that a public report needs `monarch@*` in `audiences.yaml`
- [x] T049 [P] [US7] Update `wb/config/README.md` (new harness fields, price-table kind, kb hash file, pilot plan, `wb monarch setup`) and append to `specs/001-declarative-benchmark-config/contracts/config-files.md` a one-line pointer to `specs/002-monarch-create-run/contracts/config-files.md`
- [x] T050 [P] [US7] Update `monarch-benchmark/docs/HANDOFF-2026-09-03.md` (new section "Feature 002 specified": branch, artifact paths, what is offline-done vs live-pending) and the status paragraph in `CLAUDE.md` ("Feature 002 … specified and planned: `specs/002-monarch-create-run/`; live pilot blocked on Bedrock")

---

## Phase 10: Polish and gates

- [x] T051 (3 Sep, HEAD af85094, no API key in the environment: `320 passed in 327.42s`) Run the full suite `cd wb && uv run python -m pytest tests -q`; paste the summary line below this task; fix any regression before continuing
- [x] T052 (done 3 Sep: 583 files, 12254 nodes, 294 communities; graphify-out is gitignored) Refresh the knowledge graph from the repo root: `python3 -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"`; confirm `graphify-out/GRAPH_REPORT.md` lists `MonarchArm`, `MonarchClient`, `langfuse_cost`, `seeds`, `monarch_setup`
- [ ] T053 **Live gate 1 (no money)**: with Monarch up (`just dev-otel`), run `uv run wb doctor` and paste the `monarch` block below; then `uv run wb monarch setup`, follow the printed override snippet, rerun until the hash file is written; commit `wb/config/products/simulated-apps.monarch-kb.yaml`; paste the setup output (47 imports, hashes) below
- [ ] T054 **Live gate 2 (no money)**: start a front door with `uv run python -m wb_arms.http_shim --host 0.0.0.0 --port 9105` and from inside a Monarch container run `curl http://host.docker.internal:9105/openapi/index.json`; paste the first lines below. Also confirm that `DELETE /api/workflows/:id` on a workflow whose run is in flight really stops the engine job (there is no run-cancel route; FR-012 relies on the cascade). Verify open question 3 against the runbook (`PUT /api/workflows/:id/products/:slug/credentials/none` needed or not) and record the answer in `research.md` R15 and `PLAN.md`
- [ ] T055 **Live gate 3 (cents; only after `bedrock:InvokeModel` is granted)**: `uv run wb doctor --monarch-probe`, then one attempt on one task with a temporary plan copy (1 task × 1 repetition, `{oracle, monarch}`); paste the row's `termination`, `cost_usd`, `phases` and the report line below; confirm Monarch tags retried attempts' traces with the same episode id (the arm bills each generation once)
- [ ] T056 **Live gate 4 (paired pilot, 60 attempts; requires Carlos's approval with a cost band and `approved_by` set)**: `uv run wb run --product simulated-apps --plan pilot-monarch-create-run`, then `wb grade` and `wb report`; paste the report's paired table and source lines below; file the report under `wb/out/report-pilot-monarch-create-run-001-internal.md`
- [ ] T057 Open the Monarch pull request from `contracts/monarch-telemetry.md` in `C:\Users\cgmat\Desktop\TestBox\monarch` (header → trace metadata, phase spans, generation usage; behind the Langfuse switch; plus the compose override documented) and ask Deyton for review; record the PR link in `PLAN.md` C2/C3. (Separate repo; not part of this branch's tests.)

---

## Dependencies

```
Phase 1 → Phase 2 → US2 (Phase 3) → US1 (Phase 4) → US3, US4, US5 (any order, all on monarch.py: sequential)
                                                    → US6 (Phase 8, independent of US3–US5)
US7 (Phase 9) any time after Phase 2; Phase 10 last; T053–T056 in order; T057 after T053.
```

- US1 needs US2's kb file shape (fixture is enough offline).
- US3, US4, US5 all edit `wb/wb_arms/monarch.py`: run them one after another, not in parallel.
- US6 and US7 are parallel with US3–US5.

## Parallel execution examples

- Phase 1: T002, T003, T004 together.
- Phase 2: T009+T010, T011, T012, T013 together after T006/T008.
- Phase 9: T048, T049, T050 together.

## Implementation strategy

1. **MVP** = Phases 1–4 (US2 + US1): the pilot plan runs offline end to end
   with Monarch rows graded from bench snapshots. That alone proves rule 3 and
   the plumbing.
2. Then US3–US5 harden the row (terminations, reply, cost), each one a short
   sequential pass over `monarch.py` with its own tests.
3. US6, US7 and the graph refresh close the offline work; the branch is
   reviewable and mergeable at that point.
4. Live gates T053–T056 run later, in order, each pasted into this file; the
   Monarch PR (T057) goes in parallel once T053 shows the mount works.
