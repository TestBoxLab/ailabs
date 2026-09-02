# Implementation Plan: Declarative Benchmark Configuration

**Branch**: `001-declarative-benchmark-config` | **Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-declarative-benchmark-config/spec.md`

## Summary

Move every input of the benchmark methodology out of CLI flags and code into
four folders of YAML files (`products/`, `models/`, `harnesses/`, `plans/`)
under `monarch-benchmark/workflowbench/config/`. A run is product × plan.
`wb run` takes `--product` and `--plan` (name or path) and asks interactively
for what is missing. One new module, `wb_orchestrator/config.py`, loads and
validates the files and produces a resolved `RunConfig`; the orchestrator gains
a cost ceiling and an approval gate; the provider registry and the side-effect
list become loaders of those files. Competitor names in results become
`model/harness` (or the harness name alone).

## Technical Context

**Language/Version**: Python 3.13, managed by `uv`

**Primary Dependencies**: PyYAML (already in the venv transitively; declared
explicitly now), pydantic 2 (already used for `EpisodeRow`), stdlib
`argparse`, `input()`, `sys.stdin.isatty()`

**Storage**: SQLite via `wb_results/store.py` (runs, episodes, artifacts);
YAML files under `config/`; run artifacts under `out/`

**Testing**: pytest (`uv run python -m pytest tests -q`, 73 tests today);
new `tests/test_config.py` for loading/validation/guards; existing tests keep
passing with the constructor path

**Target Platform**: Windows and Linux (CI on ubuntu-latest)

**Project Type**: CLI tool + library package (`workflowbench`)

**Performance Goals**: validation of the four folders in well under a second;
no provider contact before validation passes

**Constraints**: no full round without approval (constitution §IV); no price
table or side-effect list left in code (FR-013, FR-014); `resume`, `status`,
`grade`, `report` keep their interfaces (FR-016); every file in English with
plain names (constitution §V)

**Scale/Scope**: ~10 config files shipped; 5 code modules touched; 1 new
module; 1 CI workflow updated

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Brainstorm → spec → plan → tasks → execute | PASS | Brainstormed 2026-09-02 with Carlos; spec 001 approved; this is the plan. |
| II. Test-first | PASS | Each guard and validation rule gets a failing test before code; smoke plan reproduction test; declare byte-identity test. |
| III. Methodology fixed; inputs change | PASS | No rule in PLAN.md §1 changes. Only its inputs move to files. Config hash still refuses drift; audience gate still code. |
| IV. Money and pre-registration gates | PASS | The feature *implements* the approval gate and a cost ceiling. No run is started during implementation; tests use the mock provider. Task files are not edited. |
| V. Plain language, graph-grounded | PASS | YAML keys use plain names (competitors, repetitions, tasks). Graph consulted for orchestrator, providers, declare, CLI communities. Graph refresh is the last task. |

**Additional constraints**: stdlib-first (PyYAML is the one dependency, already
present; declared, not added). Vendored tree untouched. Provenance kept: the
resolved config (with prices) is stored in the run's `config_json`.

## Project Structure

### Documentation (this feature)

```text
specs/001-declarative-benchmark-config/
├── plan.md              # This file
├── research.md          # Phase 0: decisions on naming, hashing, ceiling, loaders
├── data-model.md        # Phase 1: the four file kinds + RunConfig
├── quickstart.md        # Phase 1: how to prove it works
├── contracts/
│   ├── config-files.md  # YAML schemas for products, models, harnesses, plans, side-effects
│   └── cli.md           # wb run / resume / corpus declare contract
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
monarch-benchmark/workflowbench/
├── config/                          # NEW — the person-edited inputs
│   ├── products/simulated-apps.yaml
│   ├── models/{claude-opus-4-8,gpt-5.6-sol,gpt-5.6-terra,kimi-k3,kimi-k3-fireworks,glm-5.3,gemini-3.7-flash}.yaml
│   ├── harnesses/{api,claude-code,oracle,sloppy,null,monarch,codex,gemini-cli,opencode}.yaml
│   ├── plans/smoke-frontier.yaml
│   └── side-effects.yaml            # moved out of declare.py
├── wb_orchestrator/
│   ├── config.py                    # NEW — load, validate, resolve, hash, pick
│   ├── cli.py                       # run takes --product/--plan; interactive picker; corpus declare --product
│   ├── orchestrator.py              # from_config(); cost ceiling; approval gate; competitor names; mode on rows
│   └── declare.py                   # SIDE_EFFECTS list -> loaded from a YAML path
├── wb_arms/
│   ├── providers.py                 # register() calls -> load_models(config/models)
│   └── cli_claude_code.py           # accepts env overrides from the harness file (model injection)
├── wb_results/store.py              # runs.stop_reason column (guarded ALTER)
├── runner/schema.py                 # EpisodeRow.test_mode (plan mode) — see research.md R6
├── wb_report/audiences.yaml         # patterns updated to the new competitor names
├── pyproject.toml                   # pyyaml declared
└── tests/test_config.py             # NEW — loading, validation, guards, smoke reproduction, declare identity

.github/workflows/smoke.yml          # wb run --product simulated-apps --plan smoke-frontier
```

**Structure Decision**: single package, one new module. The config folder sits
beside the code that reads it, as `wb_report/audiences.yaml` already does.
`audiences.yaml` stays where it is (FR-015: unchanged behaviour).

## Complexity Tracking

No constitution violations. One judgement call recorded in research.md R3:
`cost_ceiling_usd` and `approved_by` are excluded from the configuration hash
so that raising the ceiling and resuming is possible (FR-010) without breaking
drift detection (FR-011).

## Phase 0 → research.md

Decisions R1–R8 in [research.md](research.md): competitor naming and the
audience gate; hash contents; ceiling/resume semantics; model-file → `Provider`
mapping; harness kinds and model injection; where the plan's mode is recorded;
side-effect file format; interactive picker.

## Phase 1 → data-model.md, contracts/, quickstart.md

Entities, fields, validation rules, and the resolved `RunConfig` in
[data-model.md](data-model.md). File schemas in
[contracts/config-files.md](contracts/config-files.md); command contract in
[contracts/cli.md](contracts/cli.md). Validation walkthrough in
[quickstart.md](quickstart.md).

## Constitution re-check after design

Unchanged: PASS on all five. The design adds one module and no new dependency;
the methodology's rules are untouched; the money gates move from agreement to
code; names are plain.
