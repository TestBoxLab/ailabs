# Research: Declarative Benchmark Configuration

All unknowns resolved from the code as of commit `c52add8`. No external
research needed; every decision below cites the file it affects.

## R1. Competitor names and the audience gate

**Decision**: the orchestrator assigns `arm.name = competitor.name` after
building the arm, where `competitor.name` is `model/harness` or the harness
name alone. Existing arm classes keep their own default names for direct use
in tests. `wb_report/audiences.yaml` patterns become:

```yaml
internal:
  - "*"
public-rung2:
  - "monarch"
```

**Rationale**: FR-012 fixes the naming; today names are built inside four
classes (`bare/api/<key>`, `bare/cli/claude-code@ver`, `monarch/stock@rel`,
`oracle/scripted`). Overriding one attribute at one place is smaller than
editing four classes, and keeps the classes usable standalone. The Monarch
release is recorded in `EpisodeRow.model` (R6) and in the config hash, so
provenance does not depend on the name.

**Alternatives**: keep old names and map plan entries onto them — leaves
`bare/api/...` in reports, which Carlos asked to retire; add `@release` to
the Monarch competitor name — contradicts FR-012 and can be added later as a
harness file `monarch-1.5.yaml` if two releases must compete.

## R2. What the configuration hash covers

**Decision**: `config_hash` over a canonical JSON of: sorted task contract
hashes (as today), the resolved product (all fields), the plan minus
`cost_ceiling_usd` and `approved_by`, and each referenced model and harness
file's resolved fields with `key_env`/`credential_env` **names** kept and
values never read. Stored in `runs.config_hash`; the full resolved config
(same exclusions) goes to `runs.config_json` so a report can print prices and
releases from the run itself.

**Rationale**: FR-011 wants resume to refuse on drift in any file; FR-010 wants
resume to continue after the ceiling is raised. The two guard fields are not
experimental inputs, so excluding them keeps both.

**Alternatives**: hash everything and add a `--force` to resume — a bypass on
the drift check is exactly what rule 11 forbids.

## R3. Cost ceiling and resume

**Decision**: `Orchestrator` keeps `self._spent` under the existing
`_count_lock`; after each `record_episode`, if `_spent > cost_ceiling_usd` it
sets `_abort` and `stop_reason = "cost_ceiling"`. `_execute` writes
`runs.stop_reason` (new nullable column, added by a guarded `ALTER TABLE`) and
raises `RunKilled` with the spend and ceiling in the message. `wb resume`
re-resolves product and plan from `config_json` paths, recomputes the hash,
then: if `stop_reason == "cost_ceiling"` and the plan's ceiling is not greater
than the recorded spend, refuse with a message naming both numbers; otherwise
clear `stop_reason` and continue. Pending attempts have no rows; `wb status`
shows them as remaining and prints `stop_reason` when set. The check runs after
each attempt is recorded, so at most concurrency × competitors in-flight attempts
can still finish (and spend) after the ceiling trips.

**Rationale**: the abort path already exists for Ctrl-C and worker crashes;
the ceiling reuses it. One column is the smallest durable record.

**Alternatives**: mark pending attempts with placeholder rows — pollutes the
denominator logic in `wb_stats`, which treats every row as an attempt.

## R4. Model files → `Provider`

**Decision**: `wb_arms/providers.py` keeps the `Provider` dataclass and the
`REGISTRY` dict (tests and `api_loop` depend on them). The seven `register(...)`
calls are replaced by `load_models(dir)` called at import with the default
`config/models`. Field mapping:

| YAML | Provider field | Note |
|---|---|---|
| `name` | `key` | equals file stem |
| `provider` | — | vendor: anthropic, openai, google, zai, moonshot, fireworks |
| `model` | `model_id` | |
| `key_env` | `key_env` | |
| `effort` | new `effort` field | default reasoning effort; adapters read it instead of `WB_*_EFFORT` env defaults (env still overrides) |
| `usd_per_million.input/cached/output` | `price_in/price_cached/price_out` | |
| `usd_per_million.cache_write` (optional) | `price_cache_write` | |
| `adapter` (optional) | `adapter` | default by provider: anthropic→anthropic, openai→openai_responses, google→gemini, else openai |
| `base_url` (optional) | `base_url` | |
| `cache_min_prompt_tokens` (optional) | same | |
| `header_fallbacks` (optional) | same | |

**Rationale**: `api_loop` and `doctor` are untouched; only the source of truth
moves. Unknown keys are rejected at load (FR-008).

## R5. Harness kinds and model injection

**Decision**: harness files declare `kind` ∈ {`api`, `cli`, `scripted`,
`monarch`} and `accepts` (list of vendor names, or `none`). `build_arm` in the
orchestrator dispatches on kind:

- `api` → `ApiLoopArm(model.name)`
- `cli` → `ClaudeCodeArm(env=harness.env rendered with `{model}`, `{provider}`)`
  for `launcher: claude-code`; other launchers (`codex`, `gemini-cli`,
  `opencode`) ship with `runnable: false` and are refused at validation with
  "harness not runnable yet" (spec assumption).
- `scripted` → `_ScriptedAdapter(harness.script)` with `script` ∈ {oracle, sloppy, null}
- `monarch` → `MonarchArm(...)` with `base_url`, `credential_env`, `release`,
  `modes`; runnable only when the Monarch competitor exists (separate feature),
  so it ships with `runnable: false` too.

Validation: model's `provider` ∈ harness `accepts`; `{harness}` alone allowed
only when `accepts == none`; a `{model, harness}` pair requires `accepts != none`.

**Rationale**: matches what exists (four arm classes) with one switch; Codex,
Gemini CLI, OpenCode, Monarch are descriptive now, exactly as the spec allows.

## R6. Where the plan's mode is recorded

**Decision**: `EpisodeRow` already has `mode: str = "synthetic"` meaning the
world mode (synthetic vs real). The plan's test mode (full-flow, create-run,
run-only) goes to a new field `test_mode: str | None`, set by the orchestrator
from the plan for every row; `model` is set to the Monarch release for Monarch
competitors. `config_json` also carries `mode`.

**Rationale**: reusing `mode` would silently change its meaning for the 5,427
imported rows.

## R7. Side-effect file format

**Decision**: `config/side-effects.yaml`, a list of entries mirroring the
tuples in `declare.py`:

```yaml
- service: salesforce
  when: ".stage_name"        # substring of an expected path; omit for always
  allowed:
    - {service: salesforce, op: "*", path: "salesforce.opportunities[*].is_closed"}
```

`declare.load_side_effects(path)` returns the same list-of-tuples shape;
`declare_dir` takes it as a parameter. `wb corpus declare` gains `--product`
(default `simulated-apps`) and reads the path from the product file. The
byte-identity test runs `declare_dir` on a temp copy of the corpus with the
old constant and with the loaded file and diffs the outputs.

## R8. Interactive picker

**Decision**: `config.pick(kind, folder)` lists `*.yaml` sorted by name,
prints `1) name` lines, reads `input()`, accepts a number or a name. Called
from `cmd_run` only when the flag is absent and `sys.stdin.isatty()`; otherwise
raises `ConfigError` listing the names. No dependency.

**Rationale**: stdlib does it; the spec asks for a numbered list, nothing more.

## R9. Smoke-scale guard

**Decision**: `attempts_per_competitor = n_tasks × repetitions`; if `> 20` and
`approved_by` is empty → `ConfigError("plan X: 30 attempts per competitor
exceed smoke scale (20); set approved_by")`. Evaluated in `config.resolve`,
before any arm is built.

## R10. Start banner

**Decision**: before the first attempt, `cmd_run` prints one block: product,
plan, competitors, tasks, repetitions, attempts total, cost ceiling, approval.
This satisfies FR-019 and the standing rule "state episode count and cost band
before any wb run".
