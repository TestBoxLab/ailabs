# Tasks: Declarative Benchmark Configuration

**Input**: Design documents from `/specs/001-declarative-benchmark-config/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution §II mandates red → green → refactor; every
task that adds logic starts with a failing test in
`monarch-benchmark/workflowbench/tests/test_config.py` (or the named file).

**Organization**: Grouped by user story. Story order follows spec priority:
US1 (launch from files) and US4 (never spend by accident) are P1; US2
(models and harnesses) and US3 (product and side effects) are P2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US4 from spec.md

## Path Conventions

All code paths are under `monarch-benchmark/workflowbench/` (written as `wb/`
below for brevity). Tests run with
`cd monarch-benchmark/workflowbench && uv run python -m pytest tests -q`.

---

## Phase 1: Setup

- [x] T001 Declare `pyyaml>=6.0` in `wb/pyproject.toml` dependencies and run `uv sync`; confirm `uv run python -c "import yaml"` works
- [x] T002 [P] Create the folder skeleton `wb/config/{products,models,harnesses,plans}/` with a one-line `wb/config/README.md` naming the four kinds and pointing to `specs/001-declarative-benchmark-config/contracts/config-files.md`

---

## Phase 2: Foundational (blocking)

**Purpose**: the loader/validator every story depends on, plus the shipped files it validates.

- [x] T003 Write failing tests in `wb/tests/test_config.py` for `config.load_product/load_model/load_harness/load_plan`: each shipped file loads; `name` ≠ stem fails; unknown key fails; missing required key fails; bad enum fails; error message contains file path and field name (data-model.md §Validation rules 1–2)
- [x] T004 Create `wb/wb_orchestrator/config.py` with `ConfigError(Exception)`, dataclasses `Product`, `Model`, `Harness`, `Plan`, `CompetitorSpec`, and the four `load_*` functions (PyYAML `safe_load`, explicit allowed-key sets per kind, enum checks) to make T003 green
- [x] T005 [P] Write the seven model files under `wb/config/models/` from the values in `wb/wb_arms/providers.py` (claude-opus-4-8, gpt-5.6-sol, gpt-5.6-terra, kimi-k3, kimi-k3-fireworks, glm-5.3, gemini-3.7-flash) per contracts/config-files.md, including `prices_verified` dates from the source comments
- [x] T006 [P] Write harness files `wb/config/harnesses/{api,claude-code,oracle,sloppy,null}.yaml` (runnable) and `{codex,gemini-cli,opencode,monarch}.yaml` (`runnable: false`) per contracts/config-files.md
- [x] T007 [P] Write `wb/config/products/simulated-apps.yaml` with the 47 services taken from the schema file names in `wb/vendor/automation-bench/automationbench/tools/api/schemas/*.jsonc`
- [x] T008 [P] Write `wb/config/plans/smoke-frontier.yaml` per contracts/config-files.md (tasks `tasks`, repetitions 2, timeout 600, oracle + claude-opus-4-8/api + gpt-5.6-sol/api, ceiling 5, approved_by null)
- [x] T009 Write failing tests for `config.resolve(product_path, plan_path) -> RunConfig`: competitor naming (`model/harness`, harness alone), rules 3–10 of data-model.md each with one failing fixture (missing env var, mode unsupported by product, unknown model/harness, harness rejects provider, model given to a `none` harness, harness not runnable, duplicate competitor, baseline absent, task service outside product, unknown audience)
- [x] T010 Implement `config.resolve` in `wb/wb_orchestrator/config.py`: loads referenced models/harnesses, loads tasks via `orchestrator.load_suite`, computes services touched from each task's `info.initial_state` keys, applies rules 3–10, returns `RunConfig` with `competitors`, `tasks`, `attempts_per_competitor`, `attempts_total`
- [x] T011 Write failing test for `RunConfig.hash` and `RunConfig.config_json`: hash changes when a model price, a harness field, the product, or the plan's timeout changes; hash does NOT change when `cost_ceiling_usd` or `approved_by` change; `config_json` contains no environment-variable values (research.md R2)
- [x] T012 Implement `RunConfig.hash` and `config_json` in `wb/wb_orchestrator/config.py` (canonical JSON, sorted task contract hashes, guard fields excluded, `key_env`/`credential_env` names only)

---

## Phase 3: User Story 1 — Launch a round from files (P1)

**Goal**: `wb run --product X --plan Y` runs the same attempts as `smoke-frontier-001`; missing flags are asked interactively; no terminal → error listing options; resume/status/grade/report unchanged.

**Independent test**: `tests/test_config.py::test_smoke_plan_reproduces_smoke_frontier_001` and a mock-provider run through `Orchestrator.from_config`.

- [x] T013 [US1] Write failing test: `Orchestrator.from_config(store, run_config, out_dir)` runs a plan whose competitors are `{harness: oracle}` and `{model: mock, harness: api}` (mock registered as in `tests/test_fixes.py`) and records rows whose `arm` values are `oracle` and `mock/api`, with `test_mode` equal to the plan mode
- [x] T014 [US1] Add `test_mode: str | None = None` to `EpisodeRow` in `wb/runner/schema.py`
- [x] T015 [US1] In `wb/wb_orchestrator/orchestrator.py` add `build_arm_for(competitor)` dispatching on `harness.kind` (api → `ApiLoopArm(model.name)`, scripted → `_ScriptedAdapter(script)`, cli/claude-code → `ClaudeCodeArm(env=...)`, monarch → `MonarchArm`) and setting `arm.name = competitor.name`; add classmethod `from_config` that stores `RunConfig`, uses `run_config.hash` and `config_json`, and sets `test_mode` (and `model` = release for Monarch) on every row; keep the old constructor working for existing tests
- [x] T016 [US1] Write failing test `test_smoke_plan_reproduces_smoke_frontier_001`: resolving `simulated-apps` × `smoke-frontier` yields 10 tasks from `tasks/`, repetitions 2, timeout 600, competitor names `{oracle, claude-opus-4-8/api, gpt-5.6-sol/api}`, attempts_total 60 (set the three key env vars to dummies in the test)
- [x] T017 [US1] Make T016 green (fix file contents if needed; no code expected)
- [x] T018 [US1] Write failing tests for `config.pick(kind, folder, stdin, stdout)`: lists names numbered, accepts a number, accepts a name, rejects out-of-range with a retry, and `config.resolve_name_or_path("smoke-frontier", "plans")` → `config/plans/smoke-frontier.yaml`, a path is returned as-is; when `stdin` is not a tty a missing choice raises `ConfigError` listing names (research.md R8)
- [x] T019 [US1] Implement `pick` and `resolve_name_or_path` in `wb/wb_orchestrator/config.py`
- [x] T020 [US1] Rewrite `cmd_run` in `wb/wb_orchestrator/cli.py`: `--product`, `--plan`, `--run-id`; remove `--suite --arms --k --timeout --concurrency`; call `pick` for missing flags; on `ConfigError` print each line as `config error in <file>: <field>: <why>` and exit 2; print the start banner from contracts/cli.md; build `Orchestrator.from_config`
- [x] T021 [US1] Rewrite `cmd_resume` in `wb/wb_orchestrator/cli.py` to re-resolve product and plan from the run's `config_json` (`product_path`, `plan_path`), recompute the hash, and pass `--concurrency` through; keep `ConfigDrift` → exit 2
- [x] T022 [US1] Update `wb/wb_orchestrator/orchestrator.py::regrade` callers: `cmd_grade` reads `tasks_dir` from `config_json` (fall back to `suite_dir` for old runs) so `wb grade` keeps working on both old and new runs
- [x] T023 [US1] Update `_print_run_report` in `wb/wb_orchestrator/cli.py` to print `product`/`plan` names when present in `config_json` (old runs still print `suite`)
- [x] T024 [US1] Run the full suite; fix any test that constructed `Orchestrator` with removed CLI flags (none expected; the constructor is kept)

---

## Phase 4: User Story 4 — Never spend by accident (P1)

**Goal**: validation before any provider contact; approval gate above smoke scale; cost ceiling stops the run; resume refuses until the ceiling is raised.

**Independent test**: mock-provider run with a US$ 0.00001 ceiling stops after the first paid attempt; a plan with 11 tasks and no `approved_by` never builds an arm.

- [x] T025 [US4] Write failing test: `config.resolve` on a plan copy with `repetitions: 3` over the 10 pilot tasks raises `ConfigError` mentioning `approved_by`, `30`, and `20`; with `approved_by: "Carlos"` it resolves (research.md R9)
- [x] T026 [US4] Implement the smoke-scale guard in `config.resolve` (`wb/wb_orchestrator/config.py`)
- [x] T027 [US4] Write failing test in `wb/tests/test_config.py`: `Store` gets a nullable `runs.stop_reason` column on open, including on a database created by the old schema (create a DB with the old `CREATE TABLE`, reopen, assert the column exists); `store.set_stop_reason(run_id, reason)` and `store.run(run_id)["stop_reason"]`
- [x] T028 [US4] Implement the guarded `ALTER TABLE runs ADD COLUMN stop_reason TEXT` and `set_stop_reason` in `wb/wb_results/store.py`; include `stop_reason` and spend in `store.status`
- [x] T029 [US4] Write failing test: a mock-provider run with `cost_ceiling_usd` below one attempt's cost stops (`RunKilled` message contains spend and ceiling), `stop_reason == "cost_ceiling"`, fewer rows than attempts; `Orchestrator.from_config(...).resume` with the same ceiling raises `ConfigError`/`RunKilled` naming both numbers; with a raised ceiling it continues and completes with all rows (research.md R3)
- [x] T030 [US4] Implement in `wb/wb_orchestrator/orchestrator.py`: `_spent` accumulation under `_count_lock` in `_run_episode`, abort + `stop_reason` when over the ceiling, `RunKilled` message per contracts/cli.md, resume check against `run["stop_reason"]` and recorded spend, clearing `stop_reason` when allowed; set `stop_reason` also for `interrupted` and `worker_error` paths
- [x] T031 [US4] Write failing test: `wb run` (call `cli.main([...])`) with an unset key env var exits 2, prints `config error in config/models/...: key_env: ... is not set`, and never instantiates an arm (monkeypatch `build_arm_for` to fail loudly)
- [x] T032 [US4] Make T031 green by ordering `cmd_run`: resolve → guards → banner → orchestrator (no arm built before validation) in `wb/wb_orchestrator/cli.py`
- [x] T033 [US4] Update `wb/wb_orchestrator/cli.py::cmd_status` to print the `stopped:` line from contracts/cli.md when `stop_reason` is set

---

## Phase 5: User Story 2 — Models and harnesses without code (P2)

**Goal**: the registry and the harness set come from files; adding a model is a file, not code.

**Independent test**: delete the `register(...)` calls; `providers.get("claude-opus-4-8")` still works from `config/models`; a new model file appears in `providers.REGISTRY` without code changes.

- [x] T034 [US2] Write failing test in `wb/tests/test_config.py`: `providers.load_models("config/models")` returns seven `Provider` objects whose fields equal the current constants (`price_in`, `price_cached`, `price_out`, `price_cache_write`, `adapter`, `base_url`, `cache_min_prompt_tokens`, `header_fallbacks`, `key_env`, `model_id`); the default adapter rule (anthropic→anthropic, openai→openai_responses, google→gemini, else openai) applies when `adapter` is absent (research.md R4)
- [x] T035 [US2] In `wb/wb_arms/providers.py` add `effort: str = "xhigh"` to `Provider`, add `load_models(dir) -> dict[str, Provider]`, replace the seven `register(...)` calls with `REGISTRY.update(load_models(DEFAULT_MODELS_DIR))` (path relative to the package: `Path(__file__).parent.parent / "config" / "models"`); keep `register()` and `get()` for tests and the mock provider
- [x] T036 [US2] In `wb/wb_arms/api_loop.py` make the OpenAI Responses and Anthropic adapters read `provider.effort` as the default, with `WB_OPENAI_EFFORT` / `WB_ANTHROPIC_EFFORT` env still overriding (one-line change each); run `tests/test_anthropic_adapter.py`
- [x] T037 [US2] Write failing test: `ClaudeCodeArm(env={"ANTHROPIC_MODEL": "claude-opus-4-8"})` passes that variable into the subprocess environment (monkeypatch `subprocess.run`/`Popen` to capture `env`) and `build_arm_for` renders `{model}` / `{provider}` / `{key_env}` placeholders from the harness file
- [x] T038 [US2] Add the `env` parameter to `ClaudeCodeArm.__init__` in `wb/wb_arms/cli_claude_code.py` and merge it into the launch environment; render placeholders in `build_arm_for` (`wb/wb_orchestrator/orchestrator.py`)
- [x] T039 [US2] Write failing test: `wb doctor --arms claude-opus-4-8` path still resolves through `providers.get` after the registry change (existing doctor tests plus one asserting `sorted(providers.REGISTRY)` equals the seven file stems when no mock is registered)
- [x] T040 [US2] Update `wb/wb_report/audiences.yaml` patterns to the new names (`internal: "*"`, `public-rung2: "monarch"`) and adjust `wb/tests/test_m4.py` fixtures that assert on `monarch/stock@*` gating so they use `monarch` and `monarch-lab` names; keep `GateError` behaviour identical

---

## Phase 6: User Story 3 — Product and side effects (P2)

**Goal**: the side-effect list lives in the file the product points to; `wb corpus declare` reads it from there and produces identical output.

**Independent test**: `declare_dir` with the loaded file equals `declare_dir` with the old constant, byte for byte, on a temp copy of `corpus/imported-simple`.

- [x] T041 [US3] Write `wb/config/side-effects.yaml` by transcribing every entry of `SIDE_EFFECTS` in `wb/wb_orchestrator/declare.py` in the same order (format in research.md R7)
- [x] T042 [US3] Write failing test: `declare.load_side_effects("config/side-effects.yaml")` equals the current `SIDE_EFFECTS` constant exactly (list of `(service, cond, matchers)` tuples)
- [x] T043 [US3] Implement `load_side_effects` in `wb/wb_orchestrator/declare.py` and add a `side_effects` parameter to `declare_dir` (default: load from the `simulated-apps` product's path); make T042 green
- [x] T044 [US3] Write failing test: `declare_dir` on a temp copy of the first 20 tasks of `corpus/imported-simple` with `--out` produces files identical to running it with the old constant (keep the constant in the test as a frozen fixture, then delete it from `declare.py`)
- [x] T045 [US3] Delete the `SIDE_EFFECTS` constant from `wb/wb_orchestrator/declare.py`; update the module docstring
- [x] T046 [US3] Add `--product` (default `simulated-apps`) to `wb corpus declare` in `wb/wb_orchestrator/cli.py`; read `side_effects` path from the product file via `config.load_product`
- [x] T047 [US3] Write failing test: `config.resolve` fails with the task id, the service, and the product file when a task's `initial_state` names a service missing from `product.services` (fixture: a temp product with `services: [gmail]` against a Salesforce task)
- [x] T048 [US3] Make T047 green (rule 8 already in T010; adjust message to name task, service, and file)

---

## Phase 7: Polish & cross-cutting

- [x] T049 [P] Update `.github/workflows/smoke.yml`: input `plan` (default `smoke-frontier`), doctor on `claude-opus-4-8,gpt-5.6-sol`, `wb run --product simulated-apps --plan "${{ inputs.plan }}" --run-id "$RUN_ID"`, report baseline `claude-opus-4-8/api`; drop the shell `k > 2` guard
- [x] T050 [P] Update `wb/README.md` "Run" section and `monarch-benchmark/PLAN.md` §1.6 (trigger line) and §1.7 (round steps) to the new command; add a decisions-log line dated 2026-09-02: "Benchmark inputs are files: products, models, harnesses, plans; run = product × plan"
- [x] T051 [P] Update `CLAUDE.md` "What lives where" with `workflowbench/config/` and the four folders
- [x] T052 Run the full suite with `uv run python -m pytest tests -q`; paste the output in the PR/commit message; run quickstart.md steps 2–4 and record their output
- [x] T053 Refresh the knowledge graph: `python -c "from graphify.watch import _rebuild_code; from pathlib import Path; _rebuild_code(Path('.'))"` from the repo root

---

## Dependencies

- Phase 1 → Phase 2 → US1 (Phase 3) → US4 (Phase 4).
- US2 (Phase 5) depends on Phase 2 only; can run after US1 or in parallel with US4 on a separate branch.
- US3 (Phase 6) depends on Phase 2 (T004) and T010; independent of US1/US4/US2.
- Phase 7 after all stories.

## Parallel execution examples

- Phase 2: T005, T006, T007, T008 (four file-writing tasks) in parallel after T004.
- After Phase 2: US4 (T025–T033) and US3 (T041–T048) in parallel with US1 if on separate worktrees; otherwise sequential in the order given.
- Phase 7: T049, T050, T051 in parallel.

## Implementation strategy

MVP = Phase 1 + Phase 2 + US1 + US4: files exist, `wb run --product --plan`
works with validation, approval gate, and cost ceiling. That alone retires the
flags and encodes the money rule. US2 then removes the price table from code;
US3 removes the side-effect list. Each story ends with the full suite green.
