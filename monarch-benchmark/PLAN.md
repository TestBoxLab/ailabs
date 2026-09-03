# AI Labs · Monarch Benchmark Plan

Owner: Carlos Mattos · Co-lead: Lucas Wakigawa · Started 2 Sep 2026
Context: `docs/ai-labs-context.html` · Lucas's design of record: `DESIGN.md` v2.1, `BUILD-SPEC.md`

This file is the single tracking surface for the benchmark work. It answers three questions:
what will be done, what each piece delivers, and the test methodology that stays the same while
the targets change. Update it in place.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## 1. Test methodology

The methodology is the constant. Three things vary and plug into it: the **target platform**,
the **test mode** (how much of Monarch is under test), and the **competitors**.

```
trigger ──▶ run(config) ──▶ for each (task, competitor, trial):
                              prepare target ▶ snapshot before ▶ competitor works ▶ snapshot after ▶ check ▶ record
                           ──▶ statistics ──▶ report(audience) ──▶ publish (Slack, Langfuse)
```

### 1.1 Fixed rules

1. **Same request text for every competitor.** One system prompt and one task prompt per task,
   identical across competitors. For Monarch the task prompt is the workflow "goal"; the row records that.
2. **Same knowledge within a test mode.** Every competitor in the same mode sees the same catalog of actions.
3. **Nothing grades itself.** The checker runs separately on stored snapshots. Re-checking later from the
   same snapshots gives the same verdict (`wb grade`).
4. **Pass** = expected result present AND nothing else changed AND the competitor finished normally.
5. **Every task is frozen** before any competitor runs (hash of prompt + starting data + checks).
   Corpus CI enforces: every check fails on untouched data, and the scripted oracle passes.
6. **k trials per (task, competitor).** Simulated: k=4 default, k=2 for smoke. Real platforms: k=2.
7. **Paired comparisons only on identical sets.** Wins/losses + McNemar per pair; error bars beside
   every mean; infrastructure failures excluded from the denominator and reported separately.
8. **Every figure carries its source** (task set · version · count · competitor · run). No hand-typed numbers.
9. **Cost is complete.** Tokens split cached / not cached; dollars from a versioned price table;
   for Monarch, the sum over its whole model team. Wall-clock per stage.
10. **Audience rules are code.** `audiences.yaml` decides which competitors may appear in a report.
11. **Config hash per run.** Resume skips finished work and refuses if the config changed. Retries only on `infra:*`.
12. **API-key billing only** for vendor competitors. Pinned versions. Non-default flags recorded in the row.

### 1.2 What is recorded per test (already in `EpisodeRow`)

| Dimension | Fields |
|---|---|
| Correctness | `passed`, `assertions_passed`, `invariant_passed`, `unexpected_changes`, `n_changes` |
| Reliability | `trial`, `termination`, `retries`, `flags` |
| Cost | `tokens.prompt / cached / output`, `cost_usd`, cache hit rate |
| Time | `phases.*.wall_clock_s`, `started_at`, `finished_at` |
| Effort | `turns`, `tool_calls`, `phases.{discovery,authoring,execution}` (Monarch) |
| Provenance | `contract_sha256`, `arm` (versioned), `model`, `run_id`, `artifacts_uri` |

### 1.3 Variable 1 · Target platform

Which platform the competitors operate, and therefore which prompt set is used. Each platform gets
its own task corpus.

| Target | Example | What is different | Prompt set | Status |
|---|---|---|---|---|
| Simulated API set | AutomationBench mock, 47 apps | No UI. Endpoints described in files. Predictable, cents per test. | `corpus/imported-simple` (200) + AB's 6 business domains (576) | **v1 target** |
| Real platform, API + UI | Salesforce, HubSpot, Asana, Linear | Monarch can map from UI and network capture. Needs a test account, reset between tests, legal check. | to write per platform | later |
| Real platform, API only | A public REST API without a web app | Only the API surface exists to map. | to write per platform | later |

### 1.4 Variable 2 · Test mode (how much of Monarch is under test)

Monarch works in three stages: **discovery** (map the platform into a knowledge base),
**workflow creation** (turn the request into a workflow), **workflow execution** (run it).

| Mode | Stages | What Monarch receives | What the bare competitors receive | How it works on the simulated target |
|---|---|---|---|---|
| **Full flow** | 1 + 2 + 3 | Only a URL to the platform | The same 3 tools as today | The HTTP front door serves an **OpenAPI document** for the 47 apps. Feature Discovery's `api_spec` handler (credential `none`) reads it and builds the knowledge base itself (`FD_MODE=public_api_extractor`). Discovery cost and time are recorded as a phase. |
| **Create + run** | 2 + 3 | A fixed, pre-built knowledge base | The same 3 tools | The same OpenAPI document goes through a **seed generator** (the pattern in `public-api-seeds-runbook.md`) into fixture files loaded once. Deterministic and reviewable. This is Lucas's original design. |
| **Run only** | 3 | A known-correct workflow | n/a (engine-only comparison is Monarch vs Monarch versions, or Monarch engine vs a scripted executor) | Each task's scripted oracle is converted into a saved workflow (recipe). Only the engine is measured: correctness, wall-clock, retries. |

All three modes share the same checker, the same result row and the same report. They differ in
what is handed to Monarch before the clock starts.

### 1.5 Variable 3 · Competitors

Contract: `launch(episode) -> ArmResult`.

| Competitor | Role | Status |
|---|---|---|
| `oracle`, `sloppy`, `null` | checker validation | done |
| `bare/api/claude-opus-4-8` | baseline: Monarch's own brain, no product | adapter done, awaiting key for first run |
| `bare/api/gpt-5.6-sol` | second frontier baseline | registered, awaiting key for first run |
| `bare/api/{kimi-k3, glm-5.3, gemini-3.7-flash}` | cheap-model floor | done |
| `bare/cli/claude-code` | coding-agent comparison | code exists, never ran |
| `monarch/stock@<release>` in each test mode | the product | blocked, see WS-B |
| `monarch/lab@<cfg-hash>` | Lucas's experiments, internal only | after stock |

From 2 Sep 2026 competitor names in results are `model/harness` or the harness name (e.g. `claude-opus-4-8/api`, `oracle`, `monarch`).

### 1.6 Triggers

| Trigger | Status |
|---|---|
| Manual `wb run --product <product> --plan <plan>` | today |
| Weekly schedule | later (decision: manual for now) |
| Monarch release tag | later |

### 1.7 One round, step by step

```
wb doctor                                     # every provider reachable, cache hit proven
wb corpus validate <task set>                 # tasks are frozen and non-empty
wb run --product simulated-apps --plan <plan>  # resumable
wb report <run_id> --audience internal --baseline claude-opus-4-8/api
post summary to Slack #benchmarks; link Langfuse traces
```

---

## 2. Deliverables

| ID | Deliverable | Definition of done |
|---|---|---|
| D1 | Onboarding dossier | `docs/ai-labs-context.html`, plain English. **Done 2 Sep.** |
| D2 | This plan | `PLAN.md` with methodology, variables, tracked tasks. **Done 2 Sep.** |
| D3 | Reproducible environment | Fresh clone + one documented command runs the test suite and `wb doctor` on any machine. |
| D4 | Frontier baselines | `bare/api/claude-opus-4-8` and one GPT competitor run the 10-task pilot with cost and cache reported. |
| D5 | First round on the simulated target, no Monarch | 200 tasks, baselines + cheap models, k=2, internal report with source lines, summary in #benchmarks. |
| D6 | OpenAPI document for the simulated apps | Generated from the 47 `.jsonc` files, served by the HTTP front door, validated against the FD `api_spec` handler. |
| D7 | Monarch, create + run mode | `monarch@<version>` completes the 10-task pilot paired against D4; phases split (authoring, execution) with wall-clock and cost per phase and per model, read from Langfuse and priced by a versioned Bedrock table; questions asked recorded. Absorbs D10 (feature 002, `specs/002-monarch-create-run/`). |
| D8 | Monarch, full-flow mode | Same pilot with discovery inside the run; discovery phase cost and time recorded. |
| D9 | Monarch, run-only mode | Oracle workflows converted to recipes; engine-only results. |
| D10 | Monarch phase telemetry | Merged into D7 — feature 002 reads phase spans and token usage from Langfuse instead of a separate deliverable. |
| D11 | Langfuse + Slack output | One Langfuse trace per test; Slack post rendered from the report. |
| D12 | Second target platform design | Which real platform, tenant, reset, scoped checker, legal check. |

---

## 3. Workstreams and tasks

### WS-A · Environment and first round (deliver first)

- [x] A1 Pin AutomationBench (upstream 1.0.6 at 4a8e106 in `workflowbench/vendor/`; Lucas's commit 5a0dea3 is not upstream). Lucas used a patched local copy (`1.0.6+evalrepair.10`, path `AB-5a0dea3-clean`). Clone upstream at `5a0dea3` into `workflowbench/vendor/automation-bench`; ask Lucas for his patches and apply them as a `.patch` file in the repo.
- [x] A2 Replace the machine-specific `.venv` with `uv.lock` so `uv sync` reproduces it.
- [~] A3 Run the test suite (64 tests: 63 pass, 1 timing-sensitive test also failed for Lucas) and `wb doctor` here; save the output in `out/doctor-<date>.txt`.
- [x] A4 Anthropic adapter in `wb_arms/api_loop.py` + `claude-opus-4-8` provider (prices, `cache_read_input_tokens`, explicit `cache_control` on tools and system). Match Monarch's effort setting.
- [x] A5 OpenAI provider entry (`gpt-5.6-sol`, `gpt-5.6-terra`) (OpenAI-compatible path already exists).
- [x] A6 Smoke `smoke-frontier-001` (2 Sep): 10 tasks × k=2 × {oracle, claude-opus-4-8, gpt-5.6-sol}, 60 episodes, US$ 1.93 total. Opus 90% (US$ 1.39, cache 77%), GPT-5.6 Sol 100% (US$ 0.54, cache 75%), no infra errors, no cache-degraded flags. Report: `workflowbench/out/report-smoke-frontier-001-internal.md`.
- [ ] A7 Full round on `corpus/imported-simple` (200 tasks), k=2, internal report. → **D3, D4, D5**

### WS-F · CI and corpus contracts (added 2 Sep, after the smoke)

- [x] F1 Repository: work moved into the clone of `TestBoxLab/ailabs` (`ailabs/monarch-benchmark/`); two local commits, nothing pushed yet. **The GitHub repo is public**; decide visibility before the first push.
- [x] F2 `.github/workflows/ci.yml`: tests + corpus validation on every push/PR, no keys, free.
- [x] F3 `.github/workflows/smoke.yml`: manual paid smoke (10 tasks, k ≤ 2 enforced), report as artifact. Weekly schedule present but commented out. Needs repo secrets.
- [x] F4 `wb corpus declare`: derives `expected_changes` from assertion types and `allowed_changes` from a short per-service side-effect list (`wb_orchestrator/declare.py`). Reproduces all 10 manual pilot contracts exactly; offline regrade of smoke-frontier-001 flips only the two `closed_won` Opus verdicts to pass.
- [x] F5 Corpus `imported-simple` declared in place (200/200, 0 unmapped types); no-op and validation green.
- [ ] F6 Pilot `tasks/` still carry Lucas's manual contracts (missing the Salesforce close pair). Replace with the derived ones after Lucas agrees; contract hashes change.
- [ ] F7 Scripted oracle covers only Salesforce field updates: 184 of 200 corpus tasks have no oracle check in CI. Extend the oracle per assertion type, or accept no-op + smoke as the guard.
- [ ] F8 Slack post from the smoke workflow (needs a webhook secret).

### WS-B · Monarch on the simulated target, three modes

- [ ] B1 Bring up the Monarch stack locally (`just dev`); confirm workflow creation works with Bedrock from this machine.
- [x] B2 Generate `openapi.json` (`wb_world/openapi.py`: 47 docs, 686 operations, all valid; 72 same-path variants merged, not dropped) for the 47 apps from the `.jsonc` files; serve it from the HTTP front door; validate with FD's `api_spec` handler. → **D6**
- [x] B3 Finish `wb_arms/http_shim.py` (REST routes per service + `/openapi/*.json`; AB error envelopes become HTTP status; validated with FD's `api_spec` handler still pending, see B5): `POST`/`GET` routes per endpoint over one `Episode`, one instance per test, plus `/openapi.json`.
- [ ] B4 Create + run mode: seed generator from the OpenAPI document (follow `public-api-seeds-runbook.md`), load once, run authoring + execution. → **D7** → feature 002 (`specs/002-monarch-create-run/`)
- [ ] B5 Full-flow mode: register an `api_spec` discovery configuration (credential `none`, target = the front door's `/openapi.json`); run discovery inside the test; record it as a phase. → **D8**
- [ ] B6 Run-only mode: convert each task's oracle actions into a saved recipe; run the engine only. → **D9**
- [ ] B7 Rewrite `wb_arms/monarch.py` against the real endpoints: session login → `POST /api/workflows/recipe/runs {goal}` → SSE until saved → `POST /api/workflows/:id/run {mode: live}` → poll. Drop the `events.jsonl` assumption. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] B8 Cost: read the authoring token ledger + engine LLM calls per run; price with a versioned table; store per phase. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] B9 Paired pilot in each mode: 10 tasks × {monarch/stock, bare/api/claude-opus-4-8, oracle} × k=2.
- [ ] B10 Decide hosting for the Monarch stack used by the bench: laptop, a Docker VM, or staging with IP allowlist. Railway cannot host it (Lambda emulation needs the Docker socket).

### WS-C · Monarch phase telemetry (parallel, in the Monarch repo)

- [ ] C1 Read `apps/backend/src/telemetry/llm-spans.ts` and `recipe-agent/token-usage.ts`; list which stages already have spans. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] C2 Add stage spans (`discovery.run`, `recipe.triage`, `recipe.select`, `recipe.plan`, `recipe.critic`, `recipe.review`, `engine.run`, `engine.step`) with token attributes, behind the existing Langfuse switch. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] C3 Accept a `bench.episode_id` attribute (header or request field) so traces join to bench rows. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] C4 Expose per-run token totals by stage on the run read endpoint, so the bench does not scrape SSE. → **D10** — superseded: the bench reads Langfuse

### WS-D · Output: Langfuse and Slack

- [ ] D1 One Langfuse trace per test from the runner (id, competitor, task, verdict, cost, snapshot links); Monarch's spans nest under it via C3.
- [ ] D2 Slack post generated from `wb report` output. Template: what we now believe / what must happen next / confidence / cost with source. → **D11**

### WS-E · Second target platform

- [ ] E1 Pick it: one that FD has already mapped, legally clean (Google Workspace or Linear), with a tenant we control. Or an API-only public service.
- [ ] E2 Write its prompt set (task corpus) and the scoped checker + reset.
- [ ] E3 Design doc, reviewed with Lucas. → **D12**

### Parked (Lucas's plan, untouched this round)

Import of the 5,427 old results · real tenant pool · computer-use competitors · scheduled triggers · UI surfaces · public posts.

---

## 4. Decisions log

| Date | Decision | By |
|---|---|---|
| 2 Sep 2026 | First deliverable = Monarch vs raw models; baselines = Claude and GPT via API with the generic loop. | Carlos |
| 2 Sep 2026 | Runs stay manual for now; Slack #benchmarks is the destination, Langfuse the backend behind it. | Carlos |
| 2 Sep 2026 | v1 target = the simulated API set. All three test modes (full flow, create + run, run only) get built against it. | Carlos |
| 2 Sep 2026 | "Target" means the platform Monarch operates and its prompt set; "test mode" means how much of Monarch is under test. Kept as two separate axes. | Carlos |
| 2 Sep 2026 | Baseline competitor = `claude-opus-4-8` raw, because that is Monarch's authoring brain (`config/env.ts`). | from code |
| 2 Sep 2026 | Engine speaks HTTP, not MCP → HTTP front door. Authoring entrypoint = `POST /api/workflows/recipe/runs` behind session auth. | from code |
| 2 Sep 2026 | Knowledge base for the simulated apps comes from an OpenAPI document via FD's `api_spec` discovery (full flow) or its seed generator (create + run). No hand-insertion. | from code |
| 2 Sep 2026 | GPT competitors use the Responses API: chat-completions rejects function tools when reasoning is on, and reasoning off would be an unfair control against Opus at xhigh. Effort `xhigh` on both. | from doctor |
| 2 Sep 2026 | Full rounds cost real money: only smoke scale (10 tasks, k=2) without explicit approval of the specific run. | Carlos |
| 2 Sep 2026 | Code lives in `TestBoxLab/ailabs` under `monarch-benchmark/`; no separate repo. | Carlos |
| 2 Sep 2026 | Corpus invariants are derived mechanically from assertion types plus a reviewed side-effect list, not hand-written per task. | Carlos |
| 2 Sep 2026 | Repo language: English for every file; conversation in Portuguese. Plain language, no internal jargon in shared docs. | Carlos |
| 2 Sep 2026 | Benchmark inputs are files: products, models, harnesses, plans; run = product × plan. | Carlos |
| 3 Sep 2026 | Monarch cost and phases come from Langfuse priced by a versioned Bedrock table, not from Monarch's Postgres. | Carlos |
| 3 Sep 2026 | A question during authoring gets one fixed reply, hardcoded; questions counted per attempt. | Carlos |

## 5. Open questions

- **Repo visibility:** `TestBoxLab/ailabs` is public. Specs contain vendor legal notes and internal names. Make it private, or scrub, before pushing. (Carlos)
- **Task contract gap found by the smoke** (`simple.sf_opp_closed_won`): Opus set `is_closed`/`is_won` alongside the stage, which real Salesforce does automatically; the simulated Salesforce does not, and the contract does not allow those fields, so the invariant fails. GPT only set the stage and passed. Proposed fix: add `is_closed` and `is_won` on that opportunity to `allowed_changes` (changes the contract hash; old rows will not regrade). Not applied: task edits after seeing results need Lucas's sign-off, and his `evalrepair` patches may already cover it. (Carlos + Lucas)

- Lucas's AutomationBench patches (`evalrepair.10`): where are they, and are they needed for the 200-task corpus? (Lucas)
- Is there a service-account or API-key path for `/api/workflows/recipe/runs`, or does the bench log in with a session? (Deyton)
- Does `FD_MODE=public_api_extractor` need anything beyond the OpenAPI URL (auth, product slug registration)? (Deyton / code)
- Which second target platform, and does FD's existing map for it cover the task shapes we want? (Lucas)
- Owner A / Owner B naming by 2 Oct: is Carlos one of them? (Lucas + Sam)

**Feature 002 open questions** (`specs/002-monarch-create-run/spec.md`; none blocks the spec, the plan,
or the offline implementation; all three block the live pilot):

- **Model-provider permission.** None of Carlos's AWS SSO roles may call `bedrock:InvokeModel` in the
  region Monarch uses (tested 3 Sep, all denied). Monarch's authoring uses that provider only.
  Owner: Deyton or infra.
- **Product access grant.** The mechanism that grants the 47 `bench-<service>` products to the bench
  user's organisation is not named in Monarch's benchmark-access notes; until it is, setup prints the
  missing products and the step is manual. Owner: Deyton.
- **Credential binding for credential-free actions.** Whether products whose actions need no credential
  still require a credential binding, or a declaration in Monarch's discovery catalogue, for the engine
  to execute them. Owner: Carlos, verified live against the runbook before the first attempt.

Note: Monarch attempts are named `monarch@<version>`; `wb_report/audiences.yaml`'s `public-rung2`
today allows only the exact name `monarch`. A public report with the real Monarch competitor needs a
`monarch@*` pattern (or equivalent) added there before publication.
