# Contract: Monarch telemetry for the benchmark

**Owner of this document**: the benchmark (`ailabs`, feature 002).
**Implemented by**: a separate pull request in the Monarch repository
(`C:\Users\cgmat\Desktop\TestBox\monarch`), written by Carlos, reviewed by Deyton.
**Consumed by**: the benchmark's Monarch competitor, which reads Monarch's local
Langfuse after each attempt to compute cost per phase and per model.

This contract lets the benchmark meet `PLAN.md` §1 rule 9 (cost is complete;
for Monarch, the sum over its whole model team) and rule 7 (phases split). It
replaces work front C (C1–C3) and deliverable D10, now merged into feature 002.
Work item C4 (per-run token totals on Monarch's run endpoint) is superseded: the
benchmark reads Langfuse instead.

Everything here is behind the Langfuse switch Monarch already has; `just
dev-otel` points Monarch at its local Langfuse. Without the header below nothing
in Monarch changes. A read-only telemetry change does not alter behaviour, so the
competitor stays "stock".

## 1. Attempt identifier

The benchmark sends the header on the two requests that start work:

```
POST /api/workflows/recipe/runs        (authoring)
POST /api/workflows/:id/run            (execution)
x-bench-episode-id: <attempt id>
```

`<attempt id>` is an opaque string, at most 128 characters, safe for metadata
(letters, digits, `-`, `_`, `.`, `:`). Monarch MUST:

- store it as trace metadata `bench_episode_id` on every Langfuse trace created
  while serving that request, and on every trace of the jobs that request
  dispatches (the authoring job behind the SSE stream, the engine run and its
  steps), so a single query by `bench_episode_id` returns all of the attempt's
  traces;
- ignore the header when absent: no metadata, no other change;
- never echo the header into workflow content, prompts, or model input.

Queries the benchmark issues (public Langfuse API):

```
GET /api/public/traces?metadata[bench_episode_id]=<attempt id>&limit=100&page=N
GET /api/public/observations?traceId=<trace id>&limit=100&page=N
```

The benchmark authenticates with `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
(basic auth), the same keys `just dev-otel` sets.

## 2. Phase spans

Monarch MUST wrap each stage in a Langfuse span with exactly this name. Names are
fixed; the benchmark maps them to phases with the table's third column.

| Span name | Stage | Benchmark phase |
|---|---|---|
| `recipe.triage` | authoring: classify the goal | `authoring` |
| `recipe.select` | authoring: choose products and actions | `authoring` |
| `recipe.plan` | authoring: draft the workflow | `authoring` |
| `recipe.critic` | authoring: critique the draft | `authoring` |
| `recipe.review` | authoring: final review before saving | `authoring` |
| `engine.run` | execution: one workflow run | `execution` |
| `engine.step` | execution: one node of a run (child of `engine.run`) | `execution` |
| `discovery.run` | discovery of a product (feature 003; not exercised in 002) | `discovery` |

Rules:

- A stage that does not run produces no span. A stage that runs more than once
  (retries, loops) produces one span per run.
- Spans nest naturally (`engine.step` under `engine.run`); the benchmark walks
  up from each generation to the nearest ancestor whose name is in the table.
- Any other span name is allowed and ignored for phase attribution. A generation
  with no listed ancestor is counted by the benchmark under phase `other` and
  flagged, so drift is visible in the report; Monarch SHOULD avoid it.
- Wall-clock per phase is measured by the benchmark's own clocks, not taken from
  span timestamps.

## 3. Model calls (Langfuse generations)

Every model call Monarch makes while serving a tagged request MUST be a Langfuse
**generation** observation with:

| Field | Requirement |
|---|---|
| `model` | the model identifier as Bedrock reports it (for example `anthropic.claude-opus-4-8-…` or the inference-profile id). The benchmark maps it to a price-table entry by the model family (`claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5`, `claude-sonnet-4-6`, `claude-haiku-4-5`). An unmapped model stops the run. |
| `usage.input` | input tokens not served from cache |
| `usage.output` | output tokens |
| `usage.cache_read_input_tokens` | tokens read from the prompt cache, when Bedrock reports them; else absent |
| `usage.cache_creation_input_tokens` | tokens written to the prompt cache, when Bedrock reports them; else absent |
| parent | inside one of the phase spans of §2 (directly or through intermediate spans) |
| trace | a trace carrying `metadata.bench_episode_id` |

Rules:

- Token counts MUST be the provider's counts, not estimates. If the provider
  reports none, the generation is recorded with `usage` absent; the benchmark
  then counts zero tokens for it and flags the attempt `cost_missing`.
- The cost Langfuse computes on its own (`calculatedTotalCost` and friends) is
  ignored by the benchmark; it prices tokens with its own versioned table
  (`config/models/monarch-team-bedrock.yaml`).
- Streaming calls report usage once, at completion.

## 4. What the benchmark reads and computes

For one attempt:

1. Fetch all traces with `metadata.bench_episode_id == <attempt id>`.
2. Fetch all observations of those traces; keep `type == GENERATION`.
3. For each generation: phase = nearest ancestor span whose name is in §2, else
   `other`; model family = mapped from `model`; tokens = the four usage fields.
4. Sum tokens per (phase, model family). Price with the table. Store cost per
   phase and per model, cached and non-cached tokens separated.
5. No generation at all → cost 0, flag `cost_missing`. The verdict stands.

## 5. Health

The benchmark's `wb doctor` calls `GET /api/public/health` on the Langfuse
address before a run. A failing health check during a run is an infrastructure
failure for that attempt (retried, excluded from the denominator).

## 6. Fake used by the benchmark's tests

The benchmark ships a fake Langfuse (stdlib HTTP server in `tests/`) that serves
the two endpoints of §1 with traces and observations in the shape of §2 and §3.
The Monarch pull request SHOULD add a test on its side that a tagged authoring
request produces at least one trace with `bench_episode_id` and one generation
under a `recipe.*` span, so both sides test the same shape.

## 7. Compatibility

- Header absent → Monarch behaves exactly as today.
- Adding span names is a contract change: update §2 here first, then Monarch.
- Renaming or removing a span name is a breaking change: the benchmark's
  `cost_missing` share and `other` flag will show it in the next run's report.
