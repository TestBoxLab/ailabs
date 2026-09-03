# Implementation Plan: Monarch as a Competitor in Create + Run Mode

**Branch**: `002-monarch-create-run` | **Date**: 2026-09-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-monarch-create-run/spec.md`;
design of record `docs/superpowers/specs/2026-09-03-monarch-create-run-design.md`.

## Summary

Replace the placeholder `wb_arms/monarch.py` with a competitor that drives a
locally running Monarch through its own API: log in once, author a workflow
from the task request (answering any question with one fixed sentence),
run it live against the bench's front door, delete it, and read cost and
phase tokens from Monarch's local Langfuse priced by a versioned Bedrock
table. Add `wb monarch setup` to turn the 47 OpenAPI documents into Monarch
knowledge-base fixtures, import them and record their hashes in a file the
config hash covers. Extend `wb doctor`, the harness file, and the docs. All
tests offline against three stdlib fake servers. Publish the telemetry
contract that the Monarch pull request implements.

## Technical Context

**Language/Version**: Python 3.13, `uv`

**Primary Dependencies**: stdlib only for the new code (`urllib.request`,
`http.server`, `threading`, `subprocess`, `json`); PyYAML and pydantic 2
already present. No new dependency (research R5, R7).

**Storage**: SQLite results store (unchanged schema); YAML config files;
generated seed folders under `out/monarch-seeds/`; `turns.jsonl` per attempt.

**Testing**: pytest, offline; fakes `tests/fake_monarch.py`,
`tests/fake_fd.py`, `tests/fake_langfuse.py` (stdlib `ThreadingHTTPServer`,
same pattern as `tests/mock_openai.py` and the front door).

**Target Platform**: Windows host (Carlos) and Linux CI; Monarch in Docker on
the host reaching the front door via `host.docker.internal`.

**Project Type**: CLI tool + library (`workflowbench`).

**Performance Goals**: setup for 47 apps in under two minutes (import measured
at ~2 s each); Langfuse read per attempt under 5 s; no measurable slowdown of
the other competitors from the Monarch lock.

**Constraints**: constitution §III (rules 1, 2, 3, 7, 9, 11 enforced, none
changed), §IV (no run beyond smoke without approval; pilot plan ships
unapproved), §V (plain names, English). One Monarch attempt at a time.

**Scale/Scope**: 47 apps, 686 operations; pilot 60 attempts; ~6 modules
touched, 4 new modules, 3 fakes, 5 config files, 5 docs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Note |
|---|---|---|
| I. Brainstorm → spec → plan → tasks → execute | PASS | Brainstormed 3 Sep; design approved by Carlos and the spec reviewer; spec 002 written from it; this is the plan. |
| II. Test-first | PASS | Every termination row, the fixed reply, the hash check, the cost sum and the seed validator get a failing test before code (quickstart table). Live steps produce pasted output. |
| III. Methodology fixed; inputs change | PASS | No rule in PLAN.md §1 changes. New inputs: harness fields, plan, price table, hash file. Rule 3 kept by taking the snapshot from the `Episode`, rule 1 by the fixed reply, rule 9 by Langfuse + price table, rule 11 by hashing the knowledge base. |
| IV. Money and pre-registration gates | PASS | Setup and doctor spend nothing; the paid probe is opt-in; the pilot plan has `approved_by: null`; SC-008 orders live steps by cost. No task edits. |
| V. Plain language, graph-grounded | PASS | Graph consulted (Episode, Orchestrator, InfraError, ConfigError god nodes; shim and config communities). Files in English with plain names. Graph refresh is the last task. |

**Additional constraints**: stdlib-first (no SDK for Langfuse or SSE);
vendored tree untouched; provenance kept (`monarch@<sha>`, price-table
version, kb hashes in `config_json`).

Post-design re-check (after Phase 1): unchanged, PASS. One ponytail note
carried into code comments: the provider-error keyword match (R2), the global
lock (R3), the grant-route fallback (R11).

## Project Structure

### Documentation (this feature)

```text
specs/002-monarch-create-run/
├── spec.md
├── plan.md                    # this file
├── research.md                # R1–R15
├── data-model.md              # harness, price table, kb file, plan, row fields, scenario
├── quickstart.md              # offline proof + ordered live steps
├── contracts/
│   ├── monarch-telemetry.md   # what the Monarch PR implements
│   ├── cli.md                 # wb monarch setup, wb doctor additions
│   └── config-files.md        # new/changed YAML
├── checklists/requirements.md
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root: `monarch-benchmark/workflowbench/`)

```text
wb_arms/
├── monarch.py            # REWRITE: MonarchArm (lock, front door, login, authoring SSE, run, poll, delete, cost)
├── monarch_client.py     # NEW: stdlib HTTP client for the Monarch backend (json calls, SSE frames)
├── langfuse_cost.py      # NEW: read generations, attribute phases, price with the table
└── http_shim.py          # CHANGE: `host` constructor argument
wb_world/
└── seeds.py              # NEW: OpenAPI -> public-api-seeds fixture folders + validator
wb_orchestrator/
├── config.py             # CHANGE: monarch harness fields, load_price_table, MonarchKb in RunConfig + hash
├── monarch_setup.py      # NEW: wb monarch setup steps against the FD API
├── orchestrator.py       # CHANGE: build_arm_for(monarch) from Harness; optional arm.prepare() before first attempt; drop build_arm("monarch/…")
├── doctor.py             # CHANGE: check_monarch + --monarch-probe
└── cli.py                # CHANGE: `monarch setup` group; doctor flag; banner line
config/
├── harnesses/monarch.yaml                 # CHANGE
├── models/monarch-team-bedrock.yaml       # NEW
├── plans/pilot-monarch-create-run.yaml    # NEW
├── products/simulated-apps.monarch-kb.yaml # NEW, written by setup (committed once generated live)
└── README.md                              # CHANGE
tests/
├── fake_monarch.py       # NEW
├── fake_fd.py            # NEW
├── fake_langfuse.py      # NEW
├── test_monarch_arm.py   # NEW
├── test_langfuse_cost.py # NEW
├── test_monarch_setup.py # NEW
├── test_seeds.py         # NEW
├── test_config.py        # CHANGE
├── test_run_config.py    # CHANGE
├── test_openapi_shim.py  # CHANGE
└── test_arms_m2.py       # CHANGE: drop the placeholder's tests
```

Docs touched (repo root): `monarch-benchmark/PLAN.md`,
`monarch-benchmark/docs/HANDOFF-2026-09-03.md`, `CLAUDE.md`,
`specs/001-declarative-benchmark-config/contracts/config-files.md` (pointer).

**Structure Decision**: same single package as feature 001. New logic goes in
four new modules so the rewrite of `monarch.py` stays readable: the HTTP
client, the cost reader, the seed generator and the setup command each have
one job and one fake to test against.

## Design notes that tasks depend on

1. **Attempt flow** (data-model §8) lives in `MonarchArm.run`; each step is a
   small method so a test can script one scenario per FR-010 row.
2. **Deadline**: the arm re-derives its deadline after acquiring the lock
   (R3); every HTTP call gets `timeout = max(1, deadline - now)`; the SSE
   reader checks the deadline between lines.
3. **Cleanup order** in `finally`: delete workflow (ignore 404), stop front
   door, release lock. Cost read happens after cleanup and never changes the
   termination.
4. **Config hash**: `RunConfig._hashed()` adds `monarch_kb` and the resolved
   price table only when a Monarch competitor is present, so hashes of
   existing plans do not change (the two smoke runs stay resumable).
5. **`build_arm_for`** passes the whole `Harness`, the plan's `timeout_s`, the
   resolved price table and the kb file to `MonarchArm`; reads the git sha
   there so a missing checkout fails at resolve time, before any spend.
6. **Legacy removal**: `build_arm("monarch/…")`, `MONARCH_*_CMD` env,
   `events.jsonl` fold-back and `monarch/lab` go. `wb_orchestrator/telemetry.py`
   stays (used by the CLI competitor).
7. **Audiences**: unchanged for the internal pilot; a note in PLAN.md that a
   public report needs `monarch@*` in `audiences.yaml`.

## Complexity Tracking

No constitution violations. Four new modules instead of one is a readability
choice, not an abstraction: each has one caller and one fake.
