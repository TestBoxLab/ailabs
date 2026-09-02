# Data Model: Declarative Benchmark Configuration

All four file kinds are YAML mappings. `name` must equal the file stem.
Unknown keys are errors. Paths are relative to the `workflowbench/` directory.
Environment variables are referenced by name; values are read only at run time.

## Product (`config/products/<name>.yaml`)

| Field | Type | Required | Rule |
|---|---|---|---|
| `name` | str | yes | equals file stem |
| `kind` | enum | yes | `simulated` \| `real-api-ui` \| `real-api` |
| `data.dataset` | str | yes | human label of the dataset or tenant |
| `data.mutable` | bool | yes | may the benchmark change the data |
| `services` | list[str] | yes | services the product exposes (e.g. `salesforce`, `gmail`) |
| `side_effects` | path | yes | file in the side-effects format (R7) |
| `modes` | list[enum] | yes | subset of `full-flow`, `create-run`, `run-only` |
| `description` | str | no | free text |

## Model (`config/models/<name>.yaml`)

| Field | Type | Required | Rule |
|---|---|---|---|
| `name` | str | yes | equals file stem |
| `provider` | str | yes | vendor: `anthropic`, `openai`, `google`, `zai`, `moonshot`, `fireworks` |
| `model` | str | yes | the provider's model id |
| `effort` | str | yes | default reasoning effort (`xhigh`, `high`, `medium`, `low`, `none`) |
| `usd_per_million.input` | float | yes | |
| `usd_per_million.cached` | float | yes | |
| `usd_per_million.output` | float | yes | |
| `usd_per_million.cache_write` | float | no | defaults to `input` |
| `key_env` | str | yes | environment variable holding the key; must be set at validation |
| `adapter` | enum | no | `openai` \| `openai_responses` \| `gemini` \| `anthropic`; default by provider (R4) |
| `base_url` | str | no | for OpenAI-compatible endpoints |
| `cache_min_prompt_tokens` | int | no | default 0 |
| `header_fallbacks` | list[str] | no | default empty |
| `prices_verified` | date | no | provenance of the prices |

## Harness (`config/harnesses/<name>.yaml`)

| Field | Type | Required | Rule |
|---|---|---|---|
| `name` | str | yes | equals file stem |
| `kind` | enum | yes | `api` \| `cli` \| `scripted` \| `monarch` |
| `accepts` | list[str] or `none` | yes | vendors accepted; `none` = no model |
| `runnable` | bool | no | default true; false = descriptive only, refused at validation |
| `description` | str | no | |
| **kind = cli** | | | |
| `launcher` | enum | yes | `claude-code` \| `codex` \| `gemini-cli` \| `opencode` |
| `command` | str | yes | e.g. `claude -p` |
| `env` | map[str,str] | no | injected into the process; values may use `{model}`, `{provider}`, `{key_env}` |
| `output` | str | no | how the result is read (`json-stream`, `text`) |
| **kind = scripted** | | | |
| `script` | enum | yes | `oracle` \| `sloppy` \| `null` |
| **kind = monarch** | | | |
| `base_url` | str | yes | may be `${MONARCH_URL}` |
| `credential_env` | str | yes | env var holding the token |
| `release` | str | yes | recorded in `EpisodeRow.model` |
| `modes` | list[enum] | yes | which test modes this harness supports |

## Plan (`config/plans/<name>.yaml`)

| Field | Type | Required | Rule |
|---|---|---|---|
| `name` | str | yes | equals file stem |
| `tasks` | path | yes | directory of task JSON files |
| `mode` | enum | yes | `full-flow` \| `create-run` \| `run-only` |
| `repetitions` | int ≥ 1 | yes | |
| `timeout_s` | number > 0 | yes | per attempt |
| `concurrency` | int ≥ 1 | yes | per provider |
| `competitors` | list | yes | each `{model, harness}` or `{harness}`; names unique after resolution |
| `baseline` | str | yes | a competitor name from the list |
| `audience` | str | yes | key of `audiences.yaml` |
| `cost_ceiling_usd` | number > 0 | yes | |
| `approved_by` | str or null | yes (may be null) | required non-empty above smoke scale |
| `description` | str | no | |

## Side effects (`config/side-effects.yaml`)

List of `{service, when?, allowed: [{service, op, path}]}` (R7).

## Competitor (resolved, not a file)

| Field | From |
|---|---|
| `name` | `model/harness` or `harness` |
| `model` | Model or None |
| `harness` | Harness |

## RunConfig (resolved, not a file)

| Field | Content |
|---|---|
| `product` | Product |
| `plan` | Plan |
| `competitors` | list[Competitor] |
| `tasks` | loaded task dicts (from `plan.tasks`) |
| `attempts_per_competitor` | `len(tasks) × repetitions` |
| `attempts_total` | × `len(competitors)` |
| `hash` | R2 |
| `config_json` | product + plan (minus guard fields) + models + harnesses, secrets by name only |

## Validation rules (all before any provider contact; each error names file and field)

1. Folder has files; no duplicate stems; each file's `name` equals its stem.
2. No unknown keys; all required keys present with the right type/enum.
3. Every `key_env` / `credential_env` referenced by a chosen competitor is set.
4. `plan.mode ∈ product.modes`; for Monarch competitors also `∈ harness.modes`.
5. Each competitor: `harness` exists; if `model` given, it exists and its
   `provider ∈ harness.accepts`; if not given, `harness.accepts == none`.
6. `harness.runnable` is true.
7. Competitor names unique; `baseline` among them.
8. Services touched by the task set (`info.initial_state` keys of every task)
   ⊆ `product.services`.
9. `attempts_per_competitor ≤ 20` or `approved_by` non-empty.
10. `plan.audience` is a key of `audiences.yaml`.

## State: run

`runs.stop_reason` ∈ {NULL, `cost_ceiling`, `interrupted`, `worker_error`}.
Resume clears it when allowed (R3).

## EpisodeRow additions

`test_mode: str | None` (the plan's mode). `model` for Monarch = release.
