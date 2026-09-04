# Implementation Plan: Monarch in Run-Only Mode

**Branch**: `004-monarch-run-only` | **Date**: 2026-09-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-monarch-run-only/spec.md`;
design of record `docs/superpowers/specs/2026-09-04-monarch-run-only-design.md`.

## Summary

Give `MonarchArm` a mode branch: in `run-only` it skips authoring entirely, runs
the task's recorded workflow, and never deletes it. Add `wb monarch recipes`, a
paid, gated, idempotent command that drives the existing create + run attempt up
to three times per task and keeps the first workflow whose snapshot the bench's
checker passes, writing `config/products/<product>.monarch-recipes.yaml`. Extend
the config loader with `MonarchRecipes` (in the run's hash), extend `prepare()`
to verify each recipe's version and the knowledge-base fingerprint, drop tasks
with no recipe from the whole run, and say so on the report's source line. Add
the run-only plan and the mode to the harness. All tests offline against the
existing fakes plus three routes.

## Technical Context

**Language/Version**: Python 3.13, `uv`

**Primary Dependencies**: none new. Stdlib (`urllib.request`, `threading`,
`json`) plus PyYAML and pydantic 2, already present, exactly as feature 002.

**Storage**: SQLite results store (unchanged schema); YAML config files; the new
recipes file under `config/products/`.

**Testing**: pytest, offline; the feature-002 fakes (`tests/fake_monarch.py`,
`tests/fake_langfuse.py`, `tests/fake_fd.py`) extended with the workflow read
route, a run-already-active refusal and a gone-workflow answer.

**Target Platform**: Windows host (Carlos) and Linux CI; Monarch wherever the
harness points (Docker on the host, or the Railway deployment through the front
door's tunnel), as in feature 002.

**Project Type**: CLI tool + library (`workflowbench`).

**Performance Goals**: the recipes command for 10 tasks within one authoring
budget each (~2 min per attempt, worst case 30 attempts); the drift check for 10
recipes under 5 s; no measurable slowdown of the other competitors.

**Constraints**: constitution §III (rules 1, 2, 3, 5, 7, 9, 11 enforced, none
changed), §IV (the recipes command is paid and gated; the pilot plan ships
unapproved), §V (plain names, English). One Monarch attempt at a time, reusing
the lock feature 002 already holds.

**Scale/Scope**: 10 pilot tasks; pilot 140 attempts across seven competitors;
3 modules changed, 1 new module, 1 new config file, 1 new plan, 3 docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Brainstorm → spec → plan → tasks → execute | PASS | Brainstormed with Carlos 4 Sep; design of record approved; spec 004 written from it; this is the plan. |
| II. Test-first | PASS | Every branch gets a failing test first: the mode split, each recipes-command outcome, each drift refusal, the exclusion, the already-active wait. Live steps paste their output into `tasks.md`. |
| III. Methodology fixed; inputs change | PASS | No rule in `PLAN.md` §1 changes. New inputs: a recipes file, a plan, one mode value. Rule 3 kept by grading recipes with the bench's own checker; rule 7 by excluding missing tasks for every competitor; rule 8 by the source line; rule 11 by hashing the recipes file. |
| IV. Money and pre-registration gates | PASS | `wb monarch recipes` is the only paid addition and refuses without an explicit yes and a printed cost band; the pilot plan ships with no approval; SC-009 orders the live steps. No task edits. |
| V. Plain language, graph-grounded | PASS | Graph consulted (`MonarchArm`, `Orchestrator`, `RunConfig`, `InfraError` god nodes). Files in English with plain names. Graph refresh is the last task. |

**Additional constraints**: stdlib-first; vendored tree untouched; provenance
kept (the recipe row's workflow, version and knowledge-base fingerprint go into
the run's config record).

Post-design re-check (after Phase 1): unchanged, PASS. Three ponytail notes
carried into code comments: the bounded wait for an active run (R4), reusing the
create + run attempt wholesale rather than factoring it (R2), and the exclusion
being applied in `resolve()` rather than per competitor (R6).

## Project Structure

### Documentation (this feature)

```text
specs/004-monarch-run-only/
├── spec.md
├── plan.md                    # this file
├── research.md                # R1–R9
├── data-model.md              # recipes file, plan, row fields, scenario additions
├── quickstart.md              # offline proof + ordered live steps
├── contracts/
│   ├── cli.md                 # wb monarch recipes; wb run in run-only
│   └── config-files.md        # recipes file, plan, product/harness modes
├── checklists/requirements.md
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root: `monarch-benchmark/workflowbench/`)

```text
wb_arms/
└── monarch.py              # CHANGE: `mode` on the arm; run() branches; _execute reused;
                            #         no delete and no authoring in run-only; prepare()
                            #         gains the recipe check; wait for an active run
wb_orchestrator/
├── monarch_recipes.py      # NEW: the `wb monarch recipes` command (author, run, check, keep)
├── config.py               # CHANGE: MonarchRecipes dataclass + loader; RunConfig field;
                            #         _hashed() includes it; resolve() loads it in run-only
                            #         and drops tasks with no recipe
├── orchestrator.py         # CHANGE: build_arm_for passes the plan's mode and the recipes
└── cli.py                  # CHANGE: `monarch recipes` subcommand; banner line
wb_report/
└── report.py               # CHANGE: run-only source line (tasks excluded; what is compared)
config/
├── harnesses/monarch.yaml                        # CHANGE: modes gains run-only
├── plans/pilot-monarch-run-only.yaml             # NEW
├── products/simulated-apps.monarch-recipes.yaml  # NEW, written by the command (committed after the live step)
└── README.md                                     # CHANGE
tests/
├── fake_monarch.py             # CHANGE: GET /api/workflows/:id; run-already-active; gone workflow
├── test_monarch_run_only.py    # NEW: the mode branch, the waits, the terminations
├── test_monarch_recipes.py     # NEW: the command against the fakes
├── test_run_config.py          # CHANGE: recipes in the hash; drift; exclusion
├── test_config.py              # CHANGE: the new mode; the recipes file loader
└── test_m4.py                  # CHANGE: the run-only source line
```

Docs touched (repo root): `monarch-benchmark/PLAN.md`, project `CLAUDE.md`,
`monarch-benchmark/workflowbench/config/README.md`.

**Structure Decision**: same single package as features 001 and 002. Only one new
module: the recipes command, which has one caller and one fake to test against.
The competitor stays one class with a mode branch rather than two classes,
because the execution half is identical and a second class would have to be kept
in step with it by hand.

## Design notes that tasks depend on

1. **The mode reaches the arm through `build_arm_for`**, which already receives
   the whole `RunConfig` for a Monarch competitor; it passes `plan.mode` and
   `run_config.monarch_recipes`. Nothing else in the orchestrator changes.
2. **`run()` branches once**, at the top: run-only skips `_author` and the
   `finally` that deletes. `_execute` is called unchanged, so every termination
   it already maps keeps its meaning.
3. **The absent authoring phase** is achieved by not setting the key. Reports
   already iterate over the phases a row has, so nothing downstream needs a guard
   — a test asserts the key is absent rather than zero.
4. **`prepare()`** already exists for the knowledge-base check and is called once
   per run before the first attempt. In run-only it also reads each recorded
   workflow and compares the recipe version, and compares the recipes file's
   recorded knowledge-base fingerprint with the current one. Both refusals are
   non-retryable.
5. **Exclusion happens in `resolve()`**, where the task set is built, so every
   competitor sees the same set and the count is available for the banner and the
   report. Doing it per competitor would break rule 7 by construction.
6. **The recipes command reuses `MonarchArm` in create + run mode** plus the
   orchestrator's existing grading path. It is not a second attempt loop: it
   builds an `Episode`, runs the arm, takes the snapshot, calls the checker, and
   keeps or deletes. Cost per attempt is read the same way, so the command can
   print what it spent.
7. **The recipes file enters `RunConfig._hashed()`** only when the plan's mode is
   run-only, so the hashes of existing plans do not move and earlier runs stay
   resumable — the same discipline feature 002 used for the knowledge base.

## Complexity Tracking

No constitution violations. One new module and one branch; no new dependency, no
new abstraction. The alternative considered and rejected — a separate
`MonarchRunOnlyArm` class — would duplicate the execution path, the lock, the
cost read and the cleanup order, and would drift from the create + run arm the
first time either changed.
