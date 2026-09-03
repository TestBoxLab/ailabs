# Design · Monarch as a competitor in create + run mode (feature 002)

Date: 3 Sep 2026 · Author: Carlos Mattos with Claude · Status: approved in brainstorm, awaiting `/speckit-specify`

This document records the design settled in the brainstorm on 3 Sep 2026. It feeds
`/speckit-specify` for feature 002. It changes none of the fixed rules in
`monarch-benchmark/PLAN.md` §1; it adds inputs (a runnable Monarch harness, a
plan, a price table) and one new setup command.

## 1. Goal

Run Monarch, TestBox's product, as one competitor of the benchmark on the
simulated product (47 apps), in **create + run** mode: Monarch receives a
pre-built knowledge base, then, on the clock, turns the task request into a
workflow and executes it. Its result is graded by the same checker, from the
same stored snapshot, as every other competitor.

The first deliverable is a paired pilot: 10 tasks × 2 repetitions ×
{answer key, Claude Opus 4.8 raw via API, Monarch}, internal report.

## 2. Decisions taken in the brainstorm

| Decision | Choice | Why |
|---|---|---|
| Scope of feature 002 | Create + run only. Full flow = feature 003, run only = feature 004; both reuse the competitor built here. | Ten items and three modes are too much for one spec. Create + run is Lucas's original design, deterministic, with one open question for Deyton (product grant, §3 step 4). |
| Where Monarch runs | Docker on this machine (`just dev-otel` in `monarch-enterprise`). The bench's HTTP front door runs on the host on a fixed port, reachable from containers as `host.docker.internal:<port>`. | Already verified live on 2–3 Sep (`docs/benchmark-access.md` in the Monarch repo). |
| Product shape in Monarch | 47 products, one per simulated app, slug `bench-<service>`. | That is how Monarch represents real SaaS. One combined product would not be comparable with real use. |
| Monarch asks a question during authoring | Fixed automatic reply, identical for every attempt, hardcoded: "No further information is available. Proceed with your best judgment." The result row counts the questions. | Keeps the same-request rule; leaks nothing from the answer key; raw models get no clarification either. |
| Cost and phase data | Read from Langfuse (the local instance Monarch already ships with `just dev-otel`), priced by a versioned Bedrock price table in the bench. Not from Monarch's Postgres. | Carlos can change Monarch locally; the missing spans are work worth doing once and are exactly what work front C asked for. Front C therefore merges into 002 (D7 + D10 together). |
| Split across repositories | Two specs. Feature 002 in `ailabs` covers the bench side and publishes a contract (`specs/002-.../contracts/monarch-telemetry.md`). The Monarch change is a separate PR in the Monarch repo, written to that contract, reviewed by Deyton. | Each repo keeps its owner and its review. |
| Knowledge-base loading | Generated fixture folders bind-mounted into the FD API container, then `POST /v1/seeds/<slug>/import`. No Monarch code change. | Cheapest path that exists today; re-import is also the reset. |
| Reset between attempts | `DELETE /api/workflows/:id` (cascades to versions, runs, checkpoints, bindings). The world is fresh per attempt on the bench side anyway. | One call. |
| Competitor name | `monarch@<short git sha>` read from the Monarch checkout at run time (plus branch if not `main`). | Monarch has no HTTP-readable version. A read-only telemetry change does not alter behaviour, so the competitor stays "stock". |
| Concurrency | One Monarch attempt at a time (global lock in the competitor), whatever the plan's concurrency. | The knowledge base bakes the front door's URL, so the front door needs a fixed port. `# ponytail: global lock; per-slot ports + per-slot product sets if throughput matters.` |

Known blocker: none of Carlos's five AWS SSO roles may call `bedrock:InvokeModel`
(tested 3 Sep in `us-west-2`, all `AccessDeniedException`). Monarch's authoring
uses Claude through Bedrock only. Everything is testable offline; the live pilot
waits for that permission (request to Deyton or infra; procedure in the Monarch
repo's `docs/monarch-account-bootstrap.md`).

## 3. Setup, once per platform: `wb monarch setup`

A new idempotent command that spends no LLM money:

1. Generates 47 fixture folders from the OpenAPI documents produced by
   `wb_world/openapi.py`, following the acceptance bar of the Monarch repo's
   `feature-discovery/docs/public-api-seeds-runbook.md`: `auth_scheme: none`,
   `response_template` with `schema` and `extract`, `creates_entities` with
   identifier paths so actions can chain.
2. Writes them under `workflowbench/out/monarch-seeds/`. Monarch's (gitignored)
   `monarch-enterprise/docker-compose.override.yaml` must bind-mount that folder
   into the FD API container's `api/src/seeds/fixtures/public-api-seeds/`; the
   command prints the exact override snippet and refuses to continue while
   `GET /v1/seeds` does not list the 47 slugs. The Monarch PR documents the mount.
3. Registers each product with the idempotent `POST /v1/products`
   (`slug`, `display_name`), then calls `POST /v1/seeds/bench-<service>/import`
   and records the returned `kb_hash`.
4. Checks that the bench user's organisation has the 47 products granted on the
   Monarch side. **Open for Deyton:** the grant mechanism (route or seed script)
   is not named in `benchmark-access.md`; until it is, the setup prints the
   missing slugs and the step is manual.
5. Writes the 47 hashes to `config/products/simulated-apps.monarch-kb.yaml`
   (covered by the run's config hash: a different knowledge base is a different
   run). `wb run` re-reads `GET /v1/seeds` before the first Monarch attempt and
   refuses if any hash differs from the file.

**To verify live before the first attempt (runbook §4–§5):** whether products
whose actions carry `auth_scheme: none` need a credential binding
(`PUT /api/workflows/:id/products/:slug/credentials/:kind`) or a declaration in
`discovery-configuration-catalog.ts` for the engine to execute them. If yes,
the binding becomes a setup step and the declaration joins the Monarch PR's
scope; "no Monarch code change" then no longer holds for the knowledge base.

Full flow (feature 003) will decide whether discovery reads the OpenAPI from the
front door (the `api_spec` path, already proven) or whether Monarch discovers
through the bench's own search tool. That question stays open there, not here.

## 4. One attempt, step by step (`wb_arms/monarch.py`, rewritten)

Input: the task, a fresh world, a deadline. Steps:

1. Take the global Monarch lock. Then start the HTTP front door
   (`wb_arms/http_shim.py`) on this world, on the harness's fixed `shim_port`,
   bound to `0.0.0.0` (today it binds `127.0.0.1`, which containers cannot
   reach; the bind address becomes a constructor argument), advertising
   `http://host.docker.internal:<port>`. The live checklist includes fetching
   `/openapi/index.json` from inside a container.
2. Log in once per run (`POST /api/auth/login` with the seeded bench user);
   keep the token and send it as `x-monarch-session`. `MONARCH_TOKEN` in the
   environment skips the login.
3. Authoring clock starts. `POST /api/workflows/recipe/runs` with
   `{"goal": <request text, identical to the other competitors>}` and header
   `x-bench-episode-id`. Read the SSE stream line by line (frames are
   `data: <RecipeJobView JSON>`, status `running|awaiting_input|done|error`).
   On `awaiting_input`, answer `POST .../runs/:id/reply` with
   `{"requestId": <awaiting_reply.requestId>, "answers": [{"id": <question id>,
   "text": <fixed reply>}]}` for every question in the frame, and count them.
   If the job parks on an account choice instead (the `account` prompt), the
   attempt ends `agent_error:account_requested`. Ends at `done` (with
   `workflowId`) or `error`.
4. Execution clock starts. `POST /api/workflows/:id/run {"mode":"live"}`; poll
   `GET /api/workflows/runs/:runId` until a terminal status. Every REST call
   the engine makes lands on the front door and mutates the attempt's world
   in-process, so the final snapshot is the `Episode` itself. No file
   fold-back as in the old placeholder.
5. `DELETE /api/workflows/:id`. Stop the front door. Release the lock.

Result mapping:

| Outcome | Termination | Detail recorded |
|---|---|---|
| Authoring `done` and run terminal normal | `completed` | `workflowId`, `runId`, `recipeVersion`, questions asked |
| Authoring `error` caused by the model provider (message names Bedrock, AWS, credentials, or the 503 "not configured") | `infra:monarch_llm` | the bench is at fault, not Monarch |
| Authoring `error`, any other | `agent_error` | `authoring_error: <message>` |
| Run refused for a setup fault (`RUN_HOST_BLOCKED`, `ENGINE_UNAVAILABLE`, `RUN_ALREADY_ACTIVE`) | `infra:monarch_setup` | our binding, queue or cleanup is wrong |
| Run refused for the workflow's own fault (`INPUT_INVALID`, `product_not_granted`, `LLM_LOOP_UNACKNOWLEDGED`, `RUN_LEGACY_RECIPE`) | `agent_error` | `run_refused:<code>` |
| Run finished with error | `agent_error` | `run_error:<code>`, failing node id |
| Deadline hit | `timeout` | `POST .../recipe/runs/:id/cancel` for authoring; `DELETE /api/workflows/:id` for a run in flight (there is no run-cancel route) |
| Monarch down, login refused, 5xx, Langfuse unreachable for the health check | `infra:*` | retried by the orchestrator (rule 11); nothing else is |

`infra:*` rows are retried and leave the denominator (rule 7): the product is
charged only for its own failures.

The checker runs later, from the snapshot, exactly as for every competitor.

## 5. Cost and phases, from Langfuse

After each attempt the competitor queries the local Langfuse API
(`langfuse_url`, keys `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`) for traces
whose metadata `bench_episode_id` equals the attempt id. From each generation it
reads model, input tokens, output tokens, cache tokens, and the parent span
name. It sums per phase (`authoring`, `execution`; `discovery` stays empty in
002) and prices with `config/models/monarch-team-bedrock.yaml`: one line per
model of Monarch's team (Claude Opus 4.8, Opus 5, Sonnet 5, Sonnet 4.6, Haiku
4.5), Bedrock `us-west-2` prices, versioned like every other price file. The
cost Langfuse computes on its own is ignored.

No generation found → `cost_usd = 0`, flag `cost_missing`. The report prints
the share of attempts with missing cost on the source line. This is not an
infra error: the verdict stands, only the cost is incomplete. Wall-clock per
phase comes from the bench's own clocks, not from Langfuse.

## 6. Contract the Monarch side must meet (`contracts/monarch-telemetry.md`)

Written in `ailabs`, implemented by Carlos as a PR in the Monarch repo:

- `POST /api/workflows/recipe/runs` and `POST /api/workflows/:id/run` accept
  header `x-bench-episode-id` and store it as trace metadata `bench_episode_id`
  on every trace of the request and of the jobs it dispatches. Without the
  header nothing changes.
- Phase spans with fixed names: `recipe.triage`, `recipe.select`,
  `recipe.plan`, `recipe.critic`, `recipe.review`, `engine.run`, `engine.step`
  (and `discovery.run`, for feature 003). Every model call is a Langfuse
  generation with `model`, input, output and cache tokens when Bedrock reports
  them.
- All behind the Langfuse switch that already exists; `just dev-otel` points at
  the local Langfuse.

The bench side tests the contract against a fake Langfuse that serves traces in
the agreed shape.

## 7. Configuration

`config/harnesses/monarch.yaml` becomes `runnable: true` and gains:
`fd_url`, `shim_port`, `langfuse_url`, `price_table`, `monarch_repo` (path used
to read the git sha for the competitor name). `release` stops being a fixed
string. The fixed reply to questions is a constant in `monarch.py`, not a
config field: making it editable would let it drift between runs.

New plan `config/plans/pilot-monarch-create-run.yaml`: `mode: create-run`,
10 pilot tasks, 2 repetitions, competitors {oracle, claude-opus-4-8/api,
monarch}, baseline `claude-opus-4-8/api`, audience internal, cost ceiling,
`approved_by: null` until Carlos approves the specific run.

`wb doctor` gains Monarch checks: `GET /api` (liveness), `GET /api/health`
with the session, FD `GET /health`, Langfuse `GET /api/public/health`. A
Bedrock authoring probe runs only on explicit request, because it costs money.

## 8. Testing and verification

Offline by default:

- A fake Monarch in `tests/` (stdlib HTTP server, like the front door): login,
  `recipe/runs`, an SSE stream with a configurable frame sequence (including
  `awaiting_input` and `error`), `/:id/run`, run polling, `DELETE`; it calls
  back into the bench's front door to mutate the world.
- A fake Langfuse serving traces.
- A fake FD API for `wb monarch setup`.

Covered: status → termination mapping; fixed reply to questions; deadline and
cancellation; final snapshot from the `Episode`; cost per model and phase;
`cost_missing`; config hash including the 47 `kb_hash`; fixture generator
validated against the runbook format.

Live, in order, each step with output pasted into `tasks.md`: `wb doctor`
against the real Monarch; `wb monarch setup` and the 47 imports; one single
attempt on one task (cents; only once Bedrock is granted); then the paired
pilot, 60 attempts, announced with a cost band before it runs.

## 9. Documents that change

- `monarch-benchmark/PLAN.md`: B4, B7, B8 and C1–C3 point to feature 002; D7
  and D10 merge; decisions "Monarch cost comes from Langfuse, not Postgres" and
  "a question gets the fixed reply" join the decisions table; the Bedrock
  permission joins the open questions.
- `workflowbench/config/README.md` and the config-file contract: new harness
  fields.
- `monarch-benchmark/docs/HANDOFF-2026-09-03.md`: the push of `main` on 3 Sep,
  the repo move, this design.
- Project `CLAUDE.md`: status line.

## 10. Out of scope

Full flow (003), run only (004), the Slack post (work front D), the Monarch
PR itself (its own spec in the Monarch repo), the second product under test.
