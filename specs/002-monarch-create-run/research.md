# Research: Monarch as a Competitor in Create + Run Mode

Phase 0 of `/speckit-plan`. Every decision below was checked against the code
in this repo (`monarch-benchmark/workflowbench/`), the Monarch checkout
(`C:\Users\cgmat\Desktop\TestBox\monarch`, `main` at `895742d7a`), and the notes
in `local-docs/benchmark/benchmark-access.md` there. Design decisions from the
brainstorm (design §2) are taken as given and not re-argued.

## R1. How the competitor plugs into the orchestrator

**Decision**: `MonarchArm` keeps the `run(ep, deadline) -> ArmResult` interface
every other competitor uses (`wb_arms/api_loop.py:115` `ArmResult`,
`wb_orchestrator/orchestrator.py:273` `_run_episode`). `build_arm_for`
(`orchestrator.py:94`) constructs it from the `Harness` dataclass instead of
the legacy `"monarch/stock"` key; the legacy `build_arm("monarch/…")` path and
the `monarch/lab` naming go away with the placeholder.

**Rationale**: the orchestrator already does everything around the attempt
(fresh `Episode`, snapshot0, deadline, `InfraError` retries with backoff,
snapshot1 via `ep.finish()`, grading, row). The competitor only needs to
mutate the `Episode` and return an `ArmResult`. No orchestrator change for the
attempt loop.

**Alternatives considered**: a separate Monarch runner outside the
orchestrator (rejected: would duplicate retry, snapshot and row logic and break
rule 3).

## R2. Termination mapping onto the existing exception model

**Decision**: use what exists. `InfraError(kind, msg, retryable=True)` for
every `infra:*` row (retried by `_run_episode` up to `MAX_INFRA_RETRIES`);
`EpisodeTimeout` for `timeout`; `ArmResult.termination = "agent_error"` with
`error` for Monarch's own failures. Two new `kind` strings:
`infra:monarch_llm` and `infra:monarch_setup`. `infra:harness_crash` stays for
"Monarch down / login refused / 5xx / Langfuse health failed".

**Rationale**: `EpisodeRow.termination` is a free string
(`runner/schema.py:61` lists examples, not an enum); the report already
buckets on the `infra:` prefix. No schema change.

**Note on the provider-error test**: "message names Bedrock, AWS, credentials,
or the 503 not configured" becomes a small case-insensitive keyword match on
the authoring error message (`bedrock`, `aws`, `credential`, `not configured`,
`AccessDenied`). `# ponytail: keyword match; a structured error code from
Monarch is the upgrade` and is noted in the telemetry contract as a wish, not
a requirement.

## R3. Global lock and the front door's fixed port

**Decision**: a module-level `threading.Lock` in `monarch.py`, taken at the
top of `run()` and released in `finally`. The deadline passed by the
orchestrator is computed before the lock; to honour the spec's edge case ("the
second attempt's deadline starts when it acquires the lock") the arm
re-derives its own deadline as `time.monotonic() + timeout_s` after acquiring,
where `timeout_s` is stored on the arm by `build_arm_for` from
`plan.timeout_s`.

**Rationale**: the orchestrator runs one `ThreadPoolExecutor` per competitor
with `provider_concurrency` workers (`orchestrator.py:243`); a lock inside the
arm serialises Monarch without touching the pool. The per-competitor semaphore
key is the provider, so the lock does not slow the other competitors.

**Alternatives considered**: `concurrency: 1` in the plan (rejected: it would
slow the answer key and the raw model too); per-slot ports and product sets
(deferred, noted as the ponytail upgrade in the design).

## R4. Front door reachable from Docker

**Decision**: `EpisodeHTTPShim.__init__` gains `host: str = "127.0.0.1"`;
the Monarch competitor passes `host="0.0.0.0"`, `port=shim_port`,
`public_url=f"http://host.docker.internal:{shim_port}"`. Existing callers and
tests are untouched (default unchanged). Bind failure (`OSError`, port busy)
becomes `InfraError("infra:harness_crash", …, retryable=True)`.

**Rationale**: `http_shim.py:36` hardcodes `127.0.0.1`; `public_url` already
exists for the OpenAPI index. One constructor argument, as the design says.

## R5. Monarch HTTP client: stdlib only

**Decision**: `urllib.request` with a small helper for JSON POST/GET/DELETE
and the `x-monarch-session` header; SSE read as a chunked response iterated
line by line (`for raw in resp:`), parsing `data: ` frames and ignoring
`: ping`. Timeouts from the deadline. No `requests`, no `httpx`, no `sseclient`.

**Rationale**: constitution "stdlib-first"; the frames are plain JSON per
`benchmark-access.md` §2 (verified live). The API loop already uses `urllib`
for providers.

**Endpoints used** (all verified in `benchmark-access.md` unless marked):

| Step | Call |
|---|---|
| login | `POST /api/auth/login {email,password}` → cookie `monarch_session`; token reused as header `x-monarch-session` |
| liveness / health | `GET /api` (200 unauthenticated); `GET /api/health` (session) |
| authoring | `POST /api/workflows/recipe/runs {goal}` + `x-bench-episode-id` → `{runId, token}` |
| stream | `GET /api/workflows/recipe/runs/:id/stream` → `data: <RecipeJobView>` frames; `status` in `running|awaiting_input|done|error`; `awaiting_reply.requestId`, questions with `id`; terminal frame carries `workflowId`, `recipeVersion` |
| reply | `POST /api/workflows/recipe/runs/:id/reply {requestId, answers:[{id,text}]}` |
| cancel | `POST /api/workflows/recipe/runs/:id/cancel` |
| run | `POST /api/workflows/:id/run {mode:"live"}` + `x-bench-episode-id` → `{…, engine:{runId,status}}`; refusals by `code` |
| poll | `GET /api/workflows/runs/:runId` → `status`, `error`, `errorCode`, `errorNodeId`, `steps[]` [route verified, execution unverified] |
| delete | `DELETE /api/workflows/:id` (cascade) |

**Login credentials**: harness fields `login_email` and `login_password_env`
(default seeded dev user `dev-root@testbox.com`, password from
`MONARCH_PASSWORD`, seeded default `monarch-dev`). `MONARCH_TOKEN` set → skip
login. The password is never written to config; only its variable name.

## R6. Where the run's final status comes from

**Decision**: poll `GET /api/workflows/runs/:runId` every 2 s until `status`
is terminal (`succeeded|failed|cancelled|stopped`; anything else keeps
polling) or the deadline passes. The engine's REST calls hit the front door
and mutate the `Episode` in process; the orchestrator's `ep.finish()` takes
snapshot1. Nothing is read back from Monarch to build the snapshot.

**Rationale**: rule 3; design §4 step 4. The terminal-status set is taken
from `benchmark-access.md` §6 and confirmed against the fake; the live
checklist re-verifies it (SC-008).

## R7. Langfuse reader: stdlib, public API, no SDK

**Decision**: `wb_arms/langfuse_cost.py` with `read_generations(base_url,
public_key, secret_key, episode_id) -> list[Generation]` using
`GET /api/public/traces?metadata[bench_episode_id]=…` then
`GET /api/public/observations?traceId=…` (basic auth), paging with
`page`/`limit`. Phase attribution walks `parentObservationId` up to the
first ancestor whose `name` is in the contract table. **Pricing**:
`cost_for(prices, input, output, cache_read, cache_write)` prices the four
disjoint counts of contract §3 directly from the price-table entry. It
deliberately does not reuse `providers.cost_usd`, which takes an inclusive
prompt count and subtracts the cached subset: Bedrock reports the four
separately, so there is nothing to subtract and no overreport to clamp.

**Rationale**: the public Langfuse API is plain JSON over basic auth; the
`langfuse` Python SDK would be a new dependency for two GET calls. Constitution:
new dependencies need a reason; there is none.

**Model mapping**: Bedrock model ids
(`anthropic.claude-opus-4-8-…`, `us.anthropic.claude-sonnet-5-…`, inference
profiles) are mapped to a price-table family by substring
(`opus-4-8`, `opus-5`, `sonnet-5`, `sonnet-4-6`, `haiku-4-5`). Unmapped →
`ConfigError`-like stop of the run (FR-024) raised as a non-retryable
`InfraError("infra:harness_crash", retryable=False)` so the orchestrator
records the row and stops.

## R8. Price table as a model file

**Decision**: `config/models/monarch-team-bedrock.yaml` is **one file with
five entries** under a `models:` list, not five model files. It is loaded by
a new `load_price_table(path)` in `config.py`, referenced from the harness
field `price_table`, and included in `RunConfig._hashed()` under
`harnesses.monarch.price_table_resolved` so a price change is a config change.

**Rationale**: the existing `models/*.yaml` are competitors (one model, one
provider, one key). Monarch's team is not a competitor and has no key; making
five fake competitors would confuse `wb doctor` and `resolve`. A list keeps
the same `usd_per_million` shape and `prices_verified` date.

**Alternatives considered**: five entries in `models/` with
`runnable: false` (rejected: `resolve` and doctor would need a new exclusion).

## R9. Knowledge-base hash file and the config hash

**Decision**: `config/products/simulated-apps.monarch-kb.yaml` with
`generated_at`, `fd_url`, `seeds_format: public-api-seeds@1`, and `kb:` a
sorted mapping `bench-<service>: <kb_hash>`. `resolve()` loads it when any
competitor's harness is `kind: monarch` and stores it on `RunConfig` as
`monarch_kb`; `_hashed()` includes it. Missing file → `ConfigError(product
file, "monarch_kb", "run `wb monarch setup` first")`.

`MonarchArm` gets a `check_kb(fd_url) -> None` called once per run by the
orchestrator before the first Monarch attempt (a `prepare()` hook on the arm,
called in `_run_arm_group` if present; `# ponytail: hasattr check, one line`).
It compares `GET /v1/seeds` items' `kb_hash` with the file and raises
`InfraError(... retryable=False)` on drift, naming the app.

**Rationale**: FR-019/020; "a different knowledge base is a different run".

## R10. Seed generator: OpenAPI → fixture folder

**Decision**: `wb_world/seeds.py` builds, from `wb_world.openapi.build_all()`
(47 documents, 686 operations), one folder per service under
`out/monarch-seeds/bench-<service>/` with `_meta.json` and one action file per
operation in the `public-api-seeds` shape observed in
`feature-discovery/api/src/seeds/fixtures/public-api-seeds/public-api.monaco/`:

- `business_action`: `id` = `bench-<service>:<verb>:<resource>`, `label`,
  `product_id` = `bench-<service>`, `product_domain` = `host.docker.internal`,
  `area`, `verb` (from method + path: `create|read|list|update|delete`),
  `description`, `source_url` = the front door's OpenAPI URL, `state: active`.
- one `implementations[]` entry: `source: public`, `http_template` with
  `call_type: rest`, `transport_mode: header_only`, `auth_scheme: none`,
  one `steps[]` entry: `method`, `url_template` =
  `http://host.docker.internal:<shim_port>/<service>/<path>` with `{{param}}`
  placeholders, `headers_template` = `content-type: application/json`,
  `body_template` from the request schema (one `{{field}}` per top-level
  property), `response_template` with `status`, `schema` (the response
  schema), `extract` (every top-level id-like property, at least `id` when
  present).
- `creates_entities` on `create` verbs with `identifier_path` `$.id` (or the
  id property the schema names) and `identifier_keys` = the path parameters
  sibling operations use on that resource.

The generator is deterministic (sorted keys, fixed `first_seen_at`), prints
`operations_in_spec` vs `files_written`, and refuses to write a partial set.
Seed folders are found by directory scan (`seed-catalog.ts:seedFixtureDir`),
so a bind-mount into `api/src/seeds/fixtures/public-api-seeds/` is enough and
**no catalog edit is needed**. `bench-` slugs do not collide with the
committed `public-api.*` and `browser.*` folders.

**Rationale**: design §3; runbook acceptance bar. The exact field names are
copied from a real fixture, not from the runbook prose. The declaration in
`discovery-configuration-catalog.ts` (credential wiring) is not needed for
`auth_scheme: none` per the runbook ("`none` is a real runnable shape"); the
open question 3 in the spec verifies it live.

**Validation**: `seeds.validate(folder)` checks the acceptance bar
mechanically (auth scheme reachable, `schema` + `extract` present and
non-empty, `identifier_path` on creates, `identifier_keys` covering sibling
path params). Tests run it on the generated 47 folders.

## R11. `wb monarch setup` and the fake FD API

**Decision**: new CLI group `wb monarch setup [--product NAME|PATH]
[--harness NAME|PATH] [--out DIR]` in `cli.py`, logic in
`wb_orchestrator/monarch_setup.py`. Steps and stop conditions exactly as
design §3. Uses the FD API: `GET /v1/seeds`, `POST /v1/products
{slug, display_name}`, `POST /v1/seeds/:slug/import`. Product access check:
`GET /api/workflows/products` on the ME backend is not confirmed to exist;
until Deyton names the grant route, the check calls
`POST /api/workflows/:id/run` nowhere and instead reads the org's granted
products from whatever route exists at implementation time, falling back to
"unknown, verify manually" printed per slug. `# ponytail: print and continue;
the grant route is open question 2`.

The fake FD API (`tests/fake_fd.py`, stdlib `ThreadingHTTPServer`) serves the
three routes over an in-memory dict and computes `kb_hash` as sha256 of the
sorted action ids so re-import is idempotent.

## R12. `wb doctor` extension

**Decision**: `doctor.py` gains `check_monarch(harness) -> dict` with four
sub-checks (ME `GET /api`, ME `GET /api/health` with session, FD
`GET /health`, Langfuse `GET /api/public/health`) and an opt-in
`--monarch-probe` flag for the paid authoring probe (one `recipe/runs` with a
trivial goal, cancelled at the first frame). `run_doctor` includes the Monarch
check when a runnable `monarch` harness file exists in `config/harnesses/`.

## R13. Competitor name from the checkout

**Decision**: `git -C <monarch_repo> rev-parse --short HEAD` and
`git -C … rev-parse --abbrev-ref HEAD` via `subprocess` at `build_arm_for`
time; name `monarch@<sha>` or `monarch@<sha>+<branch>`. Failure →
`ConfigError(harness file, "monarch_repo", …)` before any spend (FR-013).
`EpisodeRow.model` records the same string (replaces `model_label = h.release`).

The audience allowlist (`wb_report/audiences.yaml`) matches the exact name
`monarch` for public reports; the internal audience is `*`. The pilot is
internal, so no change now; a public report will need the pattern
`monarch@*` (noted in PLAN.md, not done here).

## R14. Fake Monarch for tests

**Decision**: `tests/fake_monarch.py`, stdlib `ThreadingHTTPServer`, scripted
by a `Scenario` object: login outcome, the list of SSE frames to send
(including `awaiting_input` with N questions, `error` with a message, `done`
with `workflowId`), run refusal code or run outcome, and a list of REST calls
the "engine" makes against the front door URL it receives (so the world
mutates and the checker can pass). Records every request for assertions
(headers seen, replies received, delete called).

## R15. Docs and PLAN.md edits

**Decision**: done as tasks in this feature, in the same branch: PLAN.md
(B4/B7/B8, C1–C3 → feature 002; D7 absorbs D10; two decisions rows; three
open questions; C4 marked superseded), `config/README.md`, the config-file
contract of feature 001 (appendix pointing at this feature's
`contracts/config-files.md`), `HANDOFF-2026-09-03.md`, project `CLAUDE.md`
status line. Graphify refresh is the last task.

## Unknowns carried as open questions (not blocking offline work)

1. `bedrock:InvokeModel` for Carlos's AWS roles (blocks live steps only).
2. Product grant route or script (setup prints missing slugs meanwhile).
3. Credential binding for `auth_scheme: none` (verified live before the first
   attempt; if needed, a `PUT /api/workflows/:id/products/:slug/credentials/none`
   step is added to the attempt after authoring, behind a harness flag).
