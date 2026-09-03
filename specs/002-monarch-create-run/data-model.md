# Data Model: Monarch as a Competitor in Create + Run Mode

Plain names in files; code identifiers in parentheses where they differ.

## 1. Harness file `config/harnesses/monarch.yaml` (`Harness`, kind `monarch`)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | str | yes | `monarch` |
| `kind` | `monarch` | yes | |
| `accepts` | `none` | yes | takes no model |
| `runnable` | bool | yes | becomes `true` |
| `base_url` | str | yes | Monarch backend, e.g. `${MONARCH_URL}` → `http://localhost:4174` |
| `credential_env` | str | yes | variable holding a session token; set → login skipped |
| `login_email` | str | yes | seeded bench user, e.g. `dev-root@testbox.com` |
| `login_password_env` | str | yes | variable holding the password; never the password itself |
| `fd_url` | str | yes | discovery service, e.g. `${MONARCH_FD_URL}` → `http://localhost:3001` |
| `shim_port` | int | yes | fixed port of the front door on the host, e.g. `9105` |
| `shim_public_host` | str | no | default `host.docker.internal` |
| `langfuse_url` | str | yes | e.g. `http://localhost:3000` |
| `langfuse_public_key_env`, `langfuse_secret_key_env` | str | yes | variable names |
| `price_table` | str | yes | model-file name, e.g. `monarch-team-bedrock` |
| `monarch_repo` | str | yes | path of the Monarch checkout, for the version |
| `modes` | list | yes | subset of `full-flow, create-run, run-only` |
| `description` | str | no | |

Removed: `release`. Validation: unknown keys rejected; `shim_port` in
1024–65535; `${VAR}` placeholders expanded by the competitor at launch, not by
the loader (as today). `credential_env` no longer required to be set in the
environment when `login_password_env` is set (one of the two must be).

## 2. Price table `config/models/monarch-team-bedrock.yaml` (`PriceTable`)

```yaml
name: monarch-team-bedrock
kind: price-table
provider: bedrock
region: us-west-2
prices_verified: 2026-09-03
models:
  - {family: claude-opus-4-8,  match: [opus-4-8],  usd_per_million: {input: 5.00, cached: 0.50, cache_write: 6.25, output: 25.00}}
  - {family: claude-opus-5,    match: [opus-5],    usd_per_million: {...}}
  - {family: claude-sonnet-5,  match: [sonnet-5],  usd_per_million: {...}}
  - {family: claude-sonnet-4-6, match: [sonnet-4-6], usd_per_million: {...}}
  - {family: claude-haiku-4-5, match: [haiku-4-5], usd_per_million: {...}}
```

`match` are substrings tested against the Bedrock model id, first hit wins.
Loaded by `load_price_table`; the whole resolved table enters the config
hash. Prices are filled from the Bedrock price page at implementation time and
dated in `prices_verified`.

## 3. Knowledge-base hash file `config/products/simulated-apps.monarch-kb.yaml` (`MonarchKb`)

```yaml
product: simulated-apps
generated_at: 2026-09-04T12:00:00Z
seeds_format: public-api-seeds@1
shim_public_url: http://host.docker.internal:9105
kb:
  bench-airtable: 6d07bde6…
  bench-asana: …
  # 47 entries, sorted
```

Written only by `wb monarch setup`; read by `resolve()` when a Monarch
competitor is in the plan. `kb` and `shim_public_url` enter the config hash;
`generated_at` does not. Exactly 47 entries, one per service of the product.

## 4. Plan `config/plans/pilot-monarch-create-run.yaml` (`Plan`)

Same schema as feature 001. Values: `mode: create-run`, `tasks: tasks`,
`repetitions: 2`, `timeout_s: 900`, `concurrency: 4`, competitors
`[{harness: oracle}, {model: claude-opus-4-8, harness: api}, {harness: monarch}]`,
`baseline: claude-opus-4-8/api`, `audience: internal`,
`cost_ceiling_usd: 15`, `approved_by: null`.

## 5. Attempt result (`ArmResult` → `EpisodeRow`), Monarch additions

`EpisodeRow` is unchanged. Monarch fills existing fields:

| Row field | Monarch value |
|---|---|
| `arm` | `monarch@<sha>[+<branch>]` |
| `model` | same string |
| `termination` | per the FR-010 table (`completed`, `agent_error`, `timeout`, `infra:monarch_llm`, `infra:monarch_setup`, `infra:harness_crash`) |
| `error` | detail string (`authoring_error: …`, `run_refused: <code>`, `run_error: <code> node=<id>`, `account_requested`, `stream_closed`) |
| `phases.authoring`, `phases.execution` | `PhaseMetrics`: `wall_clock_s` from the bench clock; `tokens_input`, `tokens_output`, `cost_usd` from Langfuse; `turns` = questions asked (authoring) |
| `phases.discovery` | absent in 002 |
| `tokens` | sums over phases; `cached` = cache-read tokens, `cache_write` = cache-creation tokens |
| `cost_usd` | sum over phases |
| `flags` | `cost_missing`, `phase_other:<span name>`, `questions_asked=<n>`, plus the orchestrator's own |
| `turn_log` | one entry per SSE frame and per poll (status, phase, timestamps), written to `turns.jsonl` |
| `gate_refusals` | empty (legacy field) |

Monarch identifiers (`workflowId`, `runId`, `recipeVersion`, `recipeRunId`)
go into `turn_log[0]["monarch"]` so they land in `turns.jsonl` and
`artifacts_uri`, without a schema change.

## 6. Cost record (`Generation`, in `wb_arms/langfuse_cost.py`)

| Field | Source |
|---|---|
| `trace_id`, `observation_id` | Langfuse |
| `model` | observation `model` |
| `family` | mapped via price table `match` |
| `input`, `output`, `cache_read`, `cache_write` | `usage.input`, `usage.output`, `usage.cache_read_input_tokens`, `usage.cache_creation_input_tokens` (absent → 0) |
| `phase` | nearest ancestor span name in the contract table → `authoring|execution|discovery`, else `other` |

Aggregation: `CostSummary` = `{phase: {family: {input, output, cache_read,
cache_write, cost_usd}}}` plus `total_usd`, `missing: bool`,
`other_spans: list[str]`.

## 7. Fake Monarch scenario (`tests/fake_monarch.py`, `Scenario`)

| Field | Meaning |
|---|---|
| `login_ok` | `False` → 401 on login |
| `frames` | list of SSE frames as dicts; `awaiting_input` frames carry `awaiting_reply.requestId` and `questions[{id,text}]` |
| `run_refusal` | `None` or a code (`RUN_HOST_BLOCKED`, `INPUT_INVALID`, …) |
| `run_outcome` | `succeeded` or `failed` + `errorCode`, `errorNodeId` |
| `engine_calls` | list of `(method, path, body)` the fake engine sends to the front door before the run turns terminal |
| `delay_s` | per step, to test deadlines |

Records: `requests` (method, path, headers, body), `replies_received`,
`deleted_workflows`.

## 8. State transitions of one Monarch attempt

```
acquire lock → start front door → (login once per run)
→ authoring: POST recipe/runs → stream
     running ──► awaiting_input ──reply──► running
     running ──► done{workflowId} ──► execution
     running ──► error ──► agent_error | infra:monarch_llm
     (account prompt) ──► agent_error:account_requested
     (deadline) ──cancel──► timeout
→ execution: POST :id/run
     refused{code} ──► infra:monarch_setup | agent_error:run_refused
     accepted ──► poll runs/:runId
         succeeded ──► completed
         failed ──► agent_error:run_error
         (deadline) ──delete──► timeout
→ always: DELETE workflow → stop front door → release lock
→ cost: read Langfuse (never changes the termination)
```
