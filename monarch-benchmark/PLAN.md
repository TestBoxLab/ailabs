# AI Labs · Monarch Benchmark Plan

Owner: Carlos Mattos · Co-lead: Lucas Wakigawa · Started 2 Sep 2026
Context: `docs/ai-labs-context.html` · Lucas's design of record: `DESIGN.md` v2.1, `BUILD-SPEC.md`

This file is the single tracking surface for the benchmark work. It answers three questions:
what will be done, what each piece delivers, and the test methodology that stays the same while
the targets change. Update it in place.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

10 September continuation: shared harness instructions reconciled. Carlos's final
comparability decision preserves upstream world, routes, seeds and assertions;
only our approval-rule translation may change. Airtable/invoice limitations and
upstream issue drafts: docs/rounds/2026-09-10-upstream-limitations.md. Retained
Salesforce correction: docs/rounds/2026-09-10-invoice-jira-corrections.md.
Evalrepair adoption is suspended. Langfuse usage reconciliation and deployment
status are linked in STATE-OF-THE-PROGRAM section 13.
Deployment is complete with the catalogue preserved. One diagnostic confirmed
application routing and reproduced the filter trap, then hit missing writer
pricing. A successor price configuration and approver defaults are verified
offline; the original result and unknown-cost holds remain intact. Full-suite
and focused follow-up outcomes are recorded in that same section.


11 September Genesis voice continuation: [~] local GPT-Live-1 WebRTC connection,
server delegation, shared conversation/workspace context, cancellation and voice
controls implemented. Offline evidence and remaining scope are recorded in
[feature 025](../specs/025-genesis-voice-live-build/implementation-2026-09-11.md).
[!] Live audio validation awaits existing billing reconciliation; no paid session,
push or deployment was performed. The complete feature remains in progress.

---

## 1. Test methodology

The methodology is the constant. Three things vary and plug into it: the **target platform**,
the **test mode** (how much of Monarch is under test), and the **competitors**.

```
trigger ──▶ run(config) ──▶ for each (task, competitor, trial):
                              prepare target ▶ snapshot before ▶ competitor works ▶ snapshot after ▶ check ▶ record
                           ──▶ statistics ──▶ report ──▶ publish (Slack, Langfuse)
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
10. **One report.** Every competitor that ran appears in it and every reader sees the same page.
    (Superseded rule, 11 Sep 2026: `audiences.yaml` decided which competitors may appear.
    Retired by Lucas; a lab build is displayed like any other and the interface refuses to
    export or print a report carrying one.)
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
wb report <run_id> --baseline claude-opus-4-8/api
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
| D9 | Monarch, run-only mode | One known-correct recipe per task, made by `wb monarch recipes` (Monarch authors it off the clock; the bench's checker decides it is correct) and kept inside Monarch; the 10-task pilot run with the engine alone — an execution phase with wall-clock and cost, and no authoring phase at all; tasks with no recipe excluded from every competitor's task set and stated on the report's source line, which also says that Monarch executed a fixed workflow while the other competitors did the whole task (feature 004, `specs/004-monarch-run-only/`). |
| D10 | Monarch phase telemetry | Merged into D7 — feature 002 reads phase spans and token usage from Langfuse instead of a separate deliverable. |
| D11 | Langfuse + Slack output | One Langfuse trace per test; Slack post rendered from the report. |
| D12 | Second target platform design | Which real platform, tenant, reset, scoped checker, legal check. |
| D13 | Rounds by difficulty tier | The six scored AutomationBench domains imported and declared (800-task corpus); four task sets frozen by `wb corpus tiers` — tier-simple, tier-medium, tier-complex and random-10, ten prompts each, drawn from a recorded seed with the measure and cut points in `tasks/tiers-manifest.yaml`; four rounds run separately against the same competitors as `pilot-monarch-create-run` (prompts: 10; attempts per prompt and competitor: 2; attempts per competitor: 20 = 10 × 2; competitors: 7; attempts in the round: 140), each with its own approval and its own internal report (feature 005, `specs/005-task-tiers/`). |
| D14 | Results report as HTML tables | `wb report` writes the official page of a round: metrics per competitor, comparison against the baseline, task matrix, failures, provenance, each table with its source line; `wb summary` puts two to six rounds on one page with a mean per competitor and the random draw beside the mean of the tiers. Every number from the results store, standard library only (feature 006, `specs/006-html-report/`). |

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
- [ ] F6 Pilot `tasks/` still carry Lucas's manual contracts (missing the Salesforce close pair). Replace with the derived ones after Lucas agrees; contract hashes change. Until then a tier round (derived rules) and the pilot round (manual rules) are not rule-identical.
- [ ] F7 Scripted oracle covers only Salesforce field updates: 184 of 200 corpus tasks have no oracle check in CI. Extend the oracle per assertion type, or accept no-op + smoke as the guard.
- [ ] F8 Slack post from the smoke workflow (needs a webhook secret).
- [ ] F9 Import the six scored AutomationBench domains (finance, hr, marketing, operations, sales, support; 100 tasks each) into `corpus/imported-<domain>`, derive their approval rules with `wb corpus declare` and the reviewed side-effect list, and validate. Free and offline. All 42 services they seed are already among the product's 47 (measured 4 Sep). → feature 005 (`specs/005-task-tiers/`)
- [ ] F10 `wb corpus tiers --seed N`: score every corpus task (services seeded + expected changes + tools needed), cut at the terciles (9 and 12 today), draw ten per tier stratified by domain plus ten from the usable corpus minus the thirty tier tasks, and write four frozen task sets plus `tasks/tiers-manifest.yaml`. Drawn tasks are byte copies whose contract hash does not move; `info.tier` and `info.domain` are excluded from the hash. Free and offline. → **D13** → feature 005
- [ ] F11 Run the four rounds one at a time in the order simple, medium, complex, random, each with Carlos's approval of that specific run stated as "prompts: 10; attempts per prompt and competitor: 2; attempts per competitor: 20 = 10 × 2; competitors: 7; attempts in the round: 140" and a cost band. → **D13**

### WS-G · Reports (added 4 Sep, after the create + run pilot)

- [ ] G1 One module for every figure of the page (`wb_report/metrics.py`), calling `wb_stats` rather than reimplementing it, so the page and the markdown report can never disagree. → feature 006 (`specs/006-html-report/`)
- [ ] G2 The per-round page: metrics, comparison against the baseline with a plain-words verdict, task matrix, failures, provenance; real tables, standard library, no chart. → **D14**
- [ ] G3 The renderer receives a dictionary and cannot query the results store, proved across all four tables. → feature 006
- [ ] G4 `wb summary --runs | --plans`: two to six rounds on one page, a mean per competitor across rounds, the random draw beside the mean of the three tiers. Paired figures stay per round on identical sets, never pooled. → **D14**
- [ ] G5 Slack post rendered from the page. → WS-D, D11 (not feature 006)

### WS-H · Studio: design system, measures, reports, live views (added 9 Sep)

The web app that launches and reads rounds. Plan of record:
`docs/AI-LABS-IMPLEMENTATION-PLAN-2026-09-09.md` (seven phases, features 012
to 018). The methodology in §1 does not change; the Studio reads stored
records and never grades anything.

- [x] H0 Stabilise: New run as a route, one vocabulary (setup, track, attempt), the browser suite in `tests/browser/`, the CSS test, `THIRD_PARTY_LICENSES.md`. (9 Sep)
- [x] H1 Design system: Radix Colors, IBM Plex, Lucide, one token sheet, CSS layers, no hex colours or `!important` outside the tokens. (9 Sep)
- [x] H2 Measures on the server and the chart kit; Budget on the kit. (9 Sep)
- [x] H3 Reports as the front door: run and round reports, caveats from data, automatic ledger-charged narrative, public audience by default, print and HTML export. (9 Sep)
- [ ] H4 Evidence and live views: side panel tabs (Output, Checks, Trace, Timeline), workstream blocks, turns and violations columns, leaderboard fairness in Standings, Settings regrouped. (in progress, 9 Sep)
- [x] H5 Genesis research library and the hypothesis record with written rules. (9 Sep)
- [ ] H6 Runtime closure: budget chip in the top bar and the concurrency note at launch are done (9 Sep); live provider acceptance, the workers-mode pause drill and the restart drill wait for approved spend and a real coordinator.
- [x] H7 Product graph versions readable at a glance: summary sentence from diff counts, per-product drilldown, research log as blocks. (9 Sep)
- [x] H8 Genesis as an autonomous scientist (feature 019, 9 Sep): cards as inputs worked by a watcher under daily and per-card ceilings; a daily Monarch code index with read-only code tools; a bounded three-tier memory with a nightly consolidation job; a Trello-like board; a fixed library topic list. Live acceptance of the watcher and the nightly turn waits on a verified model route.
- [ ] H9 Genesis grows (feature 020, started 9 Sep, order from the research note Part 3): identity file `SOUL.md` done (a starter text, an editor on the Memory tab, people-only writes, first block of every prompt); next confidence and provenance tags, post-run debrief, question cards, skills, weekly sweep, evidence-to-proposal, memory self-check, digest page, Slack brief once a webhook exists.
- [x] H10 The Studio redesigned as a Swiss technical manual (9 Sep night, `docs/AI-LABS-STUDIO-DESIGN-SYSTEM-2026-09-09.md`), reviewed twice by a fresh reviewer; Newsreader vendored for report prose with Lucas's approval.
- [ ] H12 Genesis for the whole team (feature 022, 10 Sep): chat first with the board as what Genesis tracks, anyone on the team talks to it, structured hypotheses over any setup against any setup, a model per step on a configuration page, an admin-set weekly Genesis envelope, a Reviewer chamber that gates launches and ranks hypotheses, full-text ingest, the memory suite with its evaluation, Slack plus a digest page, Monarch patch proposals. Design of record `docs/superpowers/specs/2026-09-10-genesis-team-scientist-design.md`. Landed 10 Sep: layer 0 (the per-request ledger ceiling that refused every live turn is now paid from what is left of the allowance and the provider receives the cap; a model per step in `genesis/config.json`, cheapest available by default; refusals in words; the plugin seam `genesis_plugins.py`; the launch gate). Lanes A (hypotheses, tools) and C (Reviewer, ranking, memory) in progress; lane B (surface, people) briefed in `.tmp/genesis-lane-b-brief.md`.
- [x] H11 Genesis as an autonomous researcher (feature 021, 9 Sep night): autonomy dials and a kill switch in code, smoke-scale experiments launched by Genesis within its allowances, question cards, an activity record; report prose rules from CONSORT, APA and Cochrane (interval in every rate, harms first, closed certainty words); New run says what will happen on every step, blocked steps print their reason, Run again on a finished run. Design of record `docs/superpowers/specs/2026-09-09-genesis-autonomy-reports-journeys-design.md`.

### WS-B · Monarch on the simulated target, three modes

- [ ] B1 Bring up the Monarch stack locally (`just dev`); confirm workflow creation works with Bedrock from this machine.
- [x] B2 Generate `openapi.json` (`wb_world/openapi.py`: 47 docs, 686 operations, all valid; 72 same-path variants merged, not dropped) for the 47 apps from the `.jsonc` files; serve it from the HTTP front door; validate with FD's `api_spec` handler. → **D6**
- [x] B3 Finish `wb_arms/http_shim.py` (REST routes per service + `/openapi/*.json`; AB error envelopes become HTTP status; validated with FD's `api_spec` handler still pending, see B5): `POST`/`GET` routes per endpoint over one `Episode`, one instance per test, plus `/openapi.json`.
- [ ] B4 Create + run mode: seed generator from the OpenAPI document (follow `public-api-seeds-runbook.md`), load once, run authoring + execution. → **D7** → feature 002 (`specs/002-monarch-create-run/`)
- [ ] B5 Full-flow mode: register an `api_spec` discovery configuration (credential `none`, target = the front door's `/openapi.json`); run discovery inside the test; record it as a phase. → **D8**
- [ ] B6 Run-only mode: one known-correct recipe per task, authored by Monarch off the clock and kept; run the engine only. (Not the answer key's actions converted into a recipe: there is no route that creates a workflow from recipe data, and a recipe a person wrote is not the product's own work.) → **D9** → feature 004 (`specs/004-monarch-run-only/`)
- [ ] B7 Rewrite `wb_arms/monarch.py` against the real endpoints: session login → `POST /api/workflows/recipe/runs {goal}` → SSE until saved → `POST /api/workflows/:id/run {mode: live}` → poll. Drop the `events.jsonl` assumption. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] B8 Cost: read the authoring token ledger + engine LLM calls per run; price with a versioned table; store per phase. → feature 002 (`specs/002-monarch-create-run/`)
- [ ] B9 Paired pilot in each mode: 10 tasks × {monarch@<version>, claude-opus-4-8/api, oracle} × 2 repetitions.
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
| 4 Sep 2026 | In run-only, "known-correct" means a workflow Monarch itself authored, off the clock, whose run passed the bench's checker. Nothing else counts as correct — not a recipe a person wrote, not one converted from the answer key. | Carlos |
| 4 Sep 2026 | Run-only reuses one kept recipe per task (never deleted, verified by recipe version before each run); a task with no passing recipe leaves the task set of **every** competitor, and the report says how many were excluded and why. | Carlos |
| 4 Sep 2026 | Difficulty is measured in three tiers of ten prompts each, run as **separate rounds** against the same competitors, plus a ten-prompt random draw as a check on the blended average. AutomationBench's own hard-set method (the ten hardest per domain, on a private set we do not have) is not copied. | Carlos |
| 4 Sep 2026 | The difficulty measure is objective and computed from the task file alone: services seeded + expected changes + tools needed; tiers are the terciles of the whole corpus (9 and 12 today), ties falling in the lower tier. Recorded alternative: domain as the proxy. **To be confirmed with Lucas before the drawn sets are frozen and committed.** | Carlos |
| 4 Sep 2026 | The random-10 set excludes the thirty tier tasks, so it is an independent check of the blended average. | Carlos |
| 4 Sep 2026 | A drawn task is a byte copy of its corpus original with `info.tier` and `info.domain` added; those two keys are excluded from the contract hash, so a label cannot make a copy a different task. No prompt, starting data or approval rule is ever edited by the draw. | Carlos |
| 4 Sep 2026 | Repetitions stay at 2 per prompt and competitor. Every document states "prompts: N; attempts per prompt and competitor: 2; attempts per competitor: N × 2", never only the per-competitor total. | Carlos |
| 4 Sep 2026 | The official record of a round is the HTML page written by `wb report`: real tables, every number from the results store, every table carrying its source line. Langfuse stays where the raw traces live. | Carlos |
| 4 Sep 2026 | Report pages are built with the standard library, no templating engine, CSS framework or chart library, and open from disk with no network. | Carlos |
| 4 Sep 2026 | Across rounds, the aggregate is a mean of per-round rates; paired comparisons are never pooled across different task sets. | Carlos |
| 9 Sep 2026 | Studio reports render for the public audience by default; the internal view is a filter with a visible mark, never a different report. | Lucas |
| 11 Sep 2026 | There is one report, with no internal/public division, in the Studio and in `wb report` alike: `audiences.yaml`, the gate, `Plan.audience` and `--audience` are retired. A lab build is displayed like any other competitor; the interface refuses to export or print a report that carries one ("display yes, export no"). | Lucas |
| 9 Sep 2026 | The narrative of a finished run is written automatically, reserved in the weekly ledger before the request and settled from the receipt, US$ 0.50 per run unless the plan says otherwise; no manual "Analyse" button. Every number in a report comes from code; the model fills prose slots only, and a claim without evidence renders as Unknown. | Lucas |
| 9 Sep 2026 | The Studio's design system is composed, not adopted: Radix Colors (sage, green accent), IBM Plex, Lucide, Tufte-style report layer; square geometry; green means better than Bare and red worse; model families get hues that are neither green nor red. | Lucas |
| 9 Sep 2026 | The weekly budget is a chip in the Studio's top bar, always visible; Budget leaves the main navigation. | Lucas |
| 9 Sep 2026 | Genesis works dropped cards on its own: reading, searching records and writing analyses are automatic under `STUDIO_GENESIS_CARD_USD` (US$ 2.00 per card) and `STUDIO_GENESIS_DAILY_USD` (US$ 6.00 per day); anything that launches or pays for a run or an analysis stays behind the approval card. The watcher only takes runs and sources that arrive after it first ran. | Lucas |
| 9 Sep 2026 | Genesis memory is bounded: two core files of 2,500 characters and 4,000 per card, every entry tagged with its record, seven-day probation, thirty-day decay, pinned entries never decay; the nightly consolidation turn is capped at US$ 0.50. No hosted memory vendor, no vector store. Facts from Monarch's code are internal-only. | Lucas |
| 9 Sep 2026 | The Monarch code index follows the declared build (`MONARCH_BUILD_COMMIT`, else the branch of `MONARCH_BUILD`, else `main`) and is rebuilt daily at 04:00 São Paulo by code, with no model; docs extraction is not scheduled yet. | Lucas |
| 9 Sep 2026 | The Studio shows the live Product Graph Monarch Enterprise uses (products and their stored business actions) read only, through GET routes to the discovery service; the same view shows any bench product-graph version. The Studio never writes to Monarch's graph. | Lucas |
| 9 Sep 2026 | Genesis grows next (chosen by multiple select): weekly research sweep, post-run debrief, evidence-to-proposal, nightly memory self-check; self-written skills and Monarch patch proposals; daily brief to Slack `#ailabs`, a weekly digest page, question cards, an identity file; confidence and provenance on every claim. Not chosen: second-opinion turns, deterministic notebooks, per-drop budgets, weekly memory score, per-card change log. | Lucas |

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

**Feature 004 open questions** (`specs/004-monarch-run-only/spec.md`; none blocks the spec, the plan
or the offline implementation; all three are Monarch-side improvements, not blockers):

- **Naming a workflow inside Monarch.** No rename route exists: `PATCH /api/workflows/:id` accepts
  status, trigger kind, schedule, overlap policy and approval only (read in `workflows.controller.ts`,
  4 Sep). The benchmark's `bench:<task_id>` name therefore lives in the recipes file. Would a `name`
  field on that route be acceptable, so a person opening Monarch can tell the benchmark's workflows
  apart? Owner: Deyton.
- **Pinning a recipe version.** Feature 004 deliberately does not use `POST /api/workflows/:id/versions`
  (unverified, refuses v1 recipes, 409s on a stale base version) and verifies the recorded
  `recipeVersion` instead. Confirmation that a recipe cannot change under an org without an explicit
  save would close the drift question for good. Owner: Deyton.
- **Cancelling a run in flight.** There is no run-cancel route today, so a timed-out run-only attempt
  leaves the engine working and the next attempt waits it out (bounded, 60 s). A cancel route would
  replace the wait. Owner: Deyton.

Note: Monarch attempts are named `monarch@<version>`. The audience allowlist that once had to name
them is retired (11 Sep 2026), so no pattern needs adding before publication.

**Feature 005 open questions** (`specs/005-task-tiers/spec.md`; only the first blocks committing the drawn task sets; none blocks the code or its tests):

- **Confirm the difficulty measure** (services seeded + expected changes + tools needed, terciles at 9 and 12) before the drawn sets are frozen. Measured 4 Sep: the lower tercile is nearly all `simple`-domain tasks and the upper nearly all scored-domain tasks, so tier and domain overlap; if a clean difficulty variable is wanted, the simple tier must also draw from the scored domains' easy end (a different cut rule). Alternative on the table: domain as the proxy. Owner: Carlos + Lucas.
- **Lucas's AutomationBench patches** (`1.0.6+evalrepair.10`) may change scored-domain tasks; applied after a draw they change hashes and force a redraw. Owner: Lucas.
- **Unmapped assertion types in the six scored domains**: how many, and whether `declare.py`'s map needs extending before the draw; an unmapped task is excluded from the pool either way. Owner: Carlos to measure, Lucas to sign off.

**Feature 006 open questions** (`specs/006-html-report/spec.md`; none blocks the work):

- Should the median wall-clock exclude attempts with no phase timing, or show `n/a` for the whole column? Proposed: exclude, stating how many attempts contributed. Also: the phase sum omits queueing and snapshot time; a separate column from `started_at`/`finished_at` would show real elapsed time. (Carlos)
- Where is the summary page filed when `--out` is omitted? Proposed `out/summary-<date>.html`. (Carlos)
- Are sortable columns worth their twelve lines of inline JavaScript, or should the page be pure markup? Proposed: keep them, with `--no-sort` to drop them. (Carlos)
- Monarch's cost per model comes from the per-family breakdown the competitor writes to `turns.jsonl` (`{"cost": ...}`), not from phase keys; the report reads it from there. (Carlos)

## Decision D10 — Monarch phase telemetry, satisfied 11 September 2026

D10 asked for per-phase telemetry from Monarch so a round could say what authoring
cost against what execution cost. It is satisfied, and mostly was already: the
contract's span table in `wb_arms/langfuse_cost.py` maps `recipe.*` spans to
`authoring`, `engine.*` to `execution` and `discovery.run` to `discovery`, and
`CostSummary.by_phase` has carried the split since feature 002. The Monarch arm has
written it onto `EpisodeRow.phases`, with a wall clock per phase, since the same
feature.

What was missing was a reader, and feature 024 supplied it. The Studio's result row
dropped the phase block entirely, so no measure or report could see it; `measures`
now exposes `cost_by_phase`, `time_by_phase`, `per_execution` and `curve`, and the
round report opens with the break-even point they compute.

Two facts worth keeping with the decision, because both were defects found in
satisfying it:

- Anything the named phases do not claim is reported as `unattributed`, not dropped.
  The arm pre-creates only `authoring` and `execution`, so discovery spend genuinely
  falls outside them.
- An unpriced phase stays unknown and never becomes zero. An attempt whose cost
  cannot be read holds its whole ceiling against the week instead of settling, so a
  zero tells a reader the round was cheap while the ledger is still holding the money.

Frente C is closed for the simulated product. Nothing here changes §1.


## 11 September 2026 — Genesis report authoring (feature 027)

Lucas requested a concise decision-focused opening with full analysis, stronger
explanations of Monarch's winning/losing behavior, explicit error buckets and
percentage slices. Genesis now owns a local report workflow: complete analysis
in bounded native subagent turns, authored synthesis, separate review, one repair
and re-review, then internal Studio publication. Role tools, source coverage,
exact review hashes, spending admission and interrupted-work recovery are enforced.
Code supplies chart counts/denominators and exact attempt drilldowns; writing
procedures adapt Humanizer and statistical-reporting guidance.

Local validation: 176 focused offline checks passed, including a 106-attempt
native-loop fixture with provider doubles; run/round browser checks passed at
desktop/narrow widths and both themes. Live model writing quality and completion
cost remain unmeasured. The existing automatic ceiling is unchanged; insufficient
startup allocations are refused before spending. No deployment or paid model
call was made for this implementation. Evidence: specs/027-genesis-report-authoring/validation.md.


## 11 September 2026 — Live workflows and performance (feature 028)

Lucas requested streamed node workflows, visible outputs and stronger per-model
metrics, then an Impeccable UI/UX review and polish. Activity now has persistent
model lanes, structured previews, finite delivery animation, active-task navigation
and inspectable evidence. Shared live/permanent metrics cover successful and failed
completion time, median/p90, cost per success, reliability, tool activity, phase
timing and unintended-change coverage. Unknowns remain explicit.

Impeccable independent reviews informed a workflow-first responsive layout,
44px main controls, clearer preview labels, status announcements and stable focus.
87 focused Python checks, projection checks and the full offline browser scenario
passed. Desktop, phone and dark screenshots were inspected. No paid execution,
deployment, frozen task change or historical regrading occurred. Evidence and
limits: specs/028-live-workflow-metrics/implementation.md.
